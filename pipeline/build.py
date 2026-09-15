"""Turn source results into the JSON files the site reads."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from .catalog import Catalog
from .models import ModelRegistry, normalize_name
from .provenance import Provenance
from .records import SOURCE_TYPE_RANK, ScoreRecord
from .sources.base import SourceResult
from .util import now_iso, slug, today_iso

SCORE_COLS = ["m", "b", "v", "s", "lo", "hi", "d", "t", "src", "url", "sc", "n", "a", "mb", "sid", "raw"]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


class StringTable:
    def __init__(self):
        self.items: list[str] = []
        self._idx: dict[str, int] = {}

    def add(self, s: str) -> int:
        s = s or ""
        i = self._idx.get(s)
        if i is None:
            i = len(self.items)
            self.items.append(s)
            self._idx[s] = i
        return i


def _better(a: float, b: float, direction: str) -> bool:
    return a < b if direction == "lower" else a > b


def choose_authoritative(records: list[ScoreRecord], catalog: Catalog) -> None:
    """Mark exactly one record per (model_id, benchmark_id) as authoritative."""
    groups: dict[tuple[str, str], list[ScoreRecord]] = defaultdict(list)
    for r in records:
        r.authoritative = False
        if r.model_id:
            groups[(r.model_id, r.benchmark_id)].append(r)
    for (mid, bid), recs in groups.items():
        direction = (catalog.get(bid).direction if catalog.get(bid) else "higher")
        sign = 1 if direction == "lower" else -1
        recs.sort(key=lambda r: (SOURCE_TYPE_RANK.get(r.source_type, 9), sign * r.score, r.eval_date or ""), )
        recs[0].authoritative = True


def frontier_models(registry: ModelRegistry, records: list[ScoreRecord], catalog: Catalog, cfg: dict) -> set[str]:
    window = int(cfg.get("window_months", 18))
    top_n = int(cfg.get("eci_top_n", 25))
    cutoff = (date.today() - timedelta(days=30 * window)).isoformat()
    recent = [m for m in registry.models.values() if m.eci is not None and m.release_date and m.release_date >= cutoff]
    recent.sort(key=lambda m: -m.eci)
    chosen = {m.id for m in recent[:top_n]}
    # SOTA holders on featured benchmarks
    best: dict[str, tuple[float, str]] = {}
    for r in records:
        if not (r.authoritative and r.model_id and r.model_id in registry.models):
            continue
        b = catalog.get(r.benchmark_id)
        if not b or not b.featured:
            continue
        cur = best.get(r.benchmark_id)
        if cur is None or _better(r.score, cur[0], b.direction):
            best[r.benchmark_id] = (r.score, r.model_id)
    chosen |= {mid for _, mid in best.values()}
    chosen |= {m for m in cfg.get("include") or [] if m in registry.models}
    chosen -= set(cfg.get("exclude") or [])
    return chosen


def build(root: Path, out_dir: Path, results: dict[str, SourceResult], http_log: list[str] | None = None) -> dict:
    root = Path(root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = root / "data"
    catalog = Catalog.load(root / "config" / "benchmarks.yml")
    aliases = (load_yaml(root / "config" / "model_aliases.yml").get("aliases") or {})
    frontier_cfg = load_yaml(root / "config" / "frontier.yml")
    sources_cfg = load_yaml(root / "config" / "sources.yml")
    epoch_cfg = load_yaml(root / "config" / "epoch_files.yml")
    overrides = load_yaml(root / "config" / "benchmarks.yml").get("epoch_overrides") or {}

    epoch = results.get("epoch")
    if epoch is None or not epoch.extras.get("model_metadata"):
        raise RuntimeError("Epoch result with model metadata is required to build (run epoch first)")
    registry = ModelRegistry.from_epoch(epoch.extras["model_metadata"], epoch.extras.get("eci", []), aliases)
    # make sure auto benchmarks from the (possibly cached) Epoch parse exist in the catalog
    for bid, meta in (epoch.extras.get("benchmarks") or {}).items():
        ov = overrides.get(meta.get("epoch_name"), {})
        catalog.ensure_auto(meta.get("epoch_name", bid), meta.get("file", ""),
                            category=ov.get("category", meta.get("category", "other")),
                            unit=ov.get("unit", meta.get("unit", "pct")),
                            release_date=meta.get("release_date", ""), superseded_by=meta.get("superseded_by", ""),
                            random_baseline=meta.get("random_baseline"), score_ceiling=meta.get("score_ceiling"))
    prov = Provenance(sources_cfg, epoch_cfg)

    # ---------------- resolve + classify + filter ----------------
    kept: list[ScoreRecord] = []
    dropped = defaultdict(int)
    include_superseded = bool(frontier_cfg.get("include_superseded_benchmarks", False))
    for sid, res in results.items():
        for r in res.records:
            b = catalog.get(r.benchmark_id)
            if b is None:
                dropped["unknown_benchmark"] += 1
                continue
            if b.superseded_by and not include_superseded:
                dropped["superseded"] += 1
                continue
            if r.score is None:
                dropped["no_score"] += 1
                continue
            resolved = registry.resolve(r.model_raw, sid, org_hint=r.org, date_hint=r.release_date)
            r.model_id, r.matched_by = resolved.model_id, resolved.matched_by
            if not r.variant:
                r.variant = resolved.variant
            if r.model_id:
                m = registry.models[r.model_id]
                r.org = r.org or m.org
                r.release_date = r.release_date or m.release_date
                r.accessibility = r.accessibility or m.accessibility
            prov.classify(r)
            if not prov.keep(r):
                dropped[r.source_type] += 1
                continue
            if not r.model_id:
                registry.note_unmatched(r.model_raw, sid, r.score, r.benchmark_id)
                r.model_id = f"ext:{sid}:{slug(r.model_raw)}"
            b.sources.append(sid) if sid not in b.sources else None
            kept.append(r)
    choose_authoritative(kept, catalog)

    # ---------------- derived sets ----------------
    frontier = frontier_models(registry, kept, catalog, frontier_cfg)
    used_models: dict[str, dict] = {}
    variants: dict[str, set[str]] = defaultdict(set)
    n_scores: dict[str, int] = defaultdict(int)
    for r in kept:
        variants[r.model_id].add(r.variant or "default")
        if r.authoritative:
            n_scores[r.model_id] += 1
        if r.model_id.startswith("ext:"):
            used_models.setdefault(r.model_id, {"id": r.model_id, "name": r.model_name or r.model_raw, "org": r.org,
                                                 "country": r.country, "release_date": r.release_date,
                                                 "accessibility": r.accessibility, "ext": True, "source": r.source_id})
        else:
            m = registry.models[r.model_id]
            used_models.setdefault(r.model_id, {**m.to_public(), "frontier": r.model_id in frontier})
    for mid, d in used_models.items():
        d["variants"] = sorted(variants[mid])
        d["n_scores"] = n_scores.get(mid, 0)

    # SOTA + frontier series per benchmark (registry models, authoritative records only)
    sota: dict[str, dict] = {}
    series: dict[str, list[dict]] = {}
    per_bench: dict[str, list[ScoreRecord]] = defaultdict(list)
    for r in kept:
        if r.authoritative and not r.model_id.startswith("ext:"):
            per_bench[r.benchmark_id].append(r)
    for bid, recs in per_bench.items():
        b = catalog.get(bid)
        best = None
        for r in recs:
            if best is None or _better(r.score, best.score, b.direction):
                best = r
        sota[bid] = {"model_id": best.model_id, "score": round(best.score, 3), "source_type": best.source_type,
                     "eval_date": best.eval_date, "variant": best.variant, "n_models": len(recs)}
        if b.featured or bid in catalog.candidates:
            pts = sorted((r for r in recs if r.release_date), key=lambda r: (r.release_date, r.score))
            run = None
            out = []
            for r in pts:
                if run is None or _better(r.score, run, b.direction):
                    run = r.score
                    out.append({"date": r.release_date, "model_id": r.model_id, "score": round(r.score, 3)})
            series[bid] = out

    # heatmap matrix: frontier models x featured benchmarks
    feat = [b.id for b in catalog.featured()]
    fm = [m for m in used_models.values() if m.get("frontier")]
    fm.sort(key=lambda m: (-(m.get("eci") or 0), m.get("release_date") or ""))
    fm = fm[: int(frontier_cfg.get("max_models", 30))]
    auth_lookup = {(r.model_id, r.benchmark_id): r for r in kept if r.authoritative}
    matrix = {"models": [m["id"] for m in fm], "benchmarks": feat,
              "values": [[(round(auth_lookup[(m["id"], b)].score, 2) if (m["id"], b) in auth_lookup else None) for b in feat] for m in fm]}

    # ---------------- changelog ----------------
    compact = {"models": sorted(mid for mid in used_models if not mid.startswith("ext:")),
               "scores": {f"{r.model_id}|{r.benchmark_id}": round(r.score, 3) for r in kept
                          if r.authoritative and not r.model_id.startswith("ext:")},
               "sota": {bid: [v["model_id"], v["score"]] for bid, v in sota.items()}}
    prev_path = data_dir / "prev_compact.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    entry = None
    if prev:
        prev_models = set(prev.get("models", []))
        new_models = [m for m in compact["models"] if m not in prev_models]
        new_scores, changed = [], []
        for k, v in compact["scores"].items():
            pv = prev.get("scores", {}).get(k)
            mid, bid = k.split("|", 1)
            if pv is None:
                if mid not in new_models:
                    new_scores.append({"model_id": mid, "benchmark_id": bid, "score": v})
            elif abs(pv - v) >= 0.1:
                changed.append({"model_id": mid, "benchmark_id": bid, "score": v, "prev": pv})
        new_sota = []
        for bid, (mid, sc) in compact["sota"].items():
            p = prev.get("sota", {}).get(bid)
            if p is None:
                continue
            b = catalog.get(bid)
            if mid != p[0] and _better(sc, p[1], b.direction if b else "higher"):
                new_sota.append({"benchmark_id": bid, "model_id": mid, "score": sc, "prev_model_id": p[0], "prev": p[1]})
        if new_models or new_scores or changed or new_sota:
            entry = {"date": today_iso(), "run_at": now_iso(), "new_models": new_models[:100],
                     "new_scores": new_scores[:300], "changed": changed[:300], "new_sota": new_sota}
            with (data_dir / "changelog.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    data_dir.mkdir(parents=True, exist_ok=True)
    prev_path.write_text(json.dumps(compact, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    changelog = []
    cl_path = data_dir / "changelog.jsonl"
    if cl_path.exists():
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        for line in cl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("date", "") >= cutoff:
                changelog.append(e)
        changelog = changelog[-60:][::-1]

    # ---------------- write outputs ----------------
    generated_at = now_iso()
    src_names, urls, notes = StringTable(), StringTable(), StringTable()
    rows = []
    for r in kept:
        rows.append([r.model_id, r.benchmark_id, r.variant, round(r.score, 3),
                     None if r.ci_low is None else round(r.ci_low, 3), None if r.ci_high is None else round(r.ci_high, 3),
                     r.eval_date, r.source_type, src_names.add(r.source_name), urls.add(r.source_url), r.scaffold,
                     notes.add(r.note), 1 if r.authoritative else 0, r.matched_by, r.source_id, r.model_raw])
    statuses = [res.status.to_dict() for res in results.values()]
    for st in statuses:
        st.pop("note", None)
    catalog_json = {
        "generated_at": generated_at,
        "categories": catalog.categories,
        "benchmarks": sorted((b.to_public() for b in catalog.benchmarks.values() if b.sources or b.featured),
                             key=lambda b: (not b["featured"], b["category"], b["name"].lower())),
        "models": sorted(used_models.values(), key=lambda m: (m.get("ext", False), -(m.get("eci") or 0), m["name"].lower())),
        "sources": statuses,
        "frontier_rule": {k: frontier_cfg.get(k) for k in ("window_months", "eci_top_n", "max_models")},
    }
    scores_json = {"generated_at": generated_at, "cols": SCORE_COLS, "srcs": src_names.items, "urls": urls.items,
                   "notes": notes.items, "rows": rows}
    summary_json = {
        "generated_at": generated_at,
        "kpis": {"models": sum(1 for m in used_models.values() if not m.get("ext")),
                 "frontier_models": len(frontier), "benchmarks": len(catalog_json["benchmarks"]),
                 "featured": len(feat), "records": len(rows),
                 "sources_ok": sum(1 for s in statuses if s["status"] == "ok"), "sources_total": len(statuses),
                 "sources_stale": sum(1 for s in statuses if s.get("stale")),
                 "latest_eval_date": max((r.eval_date for r in kept if r.eval_date), default="")},
        "sota": sota, "frontier_series": series, "matrix": matrix, "changelog": changelog,
    }
    status_json = {
        "generated_at": generated_at, "sources": statuses,
        "build": {"records_in": sum(len(r.records) for r in results.values()), "kept": len(rows),
                  "dropped": dict(dropped), "provenance_counts": dict(prov.counts),
                  "unmatched_models": len(registry.unmatched), "ambiguous_models": len(registry.ambiguous),
                  "unknown_domains": len(prov.unknown_domains)},
        "http_log": (http_log or [])[-40:],
    }
    report = {
        "generated_at": generated_at,
        "models": sorted(registry.unmatched.values(), key=lambda e: (-e["best_score"], e["source"], e["name"])),
        "ambiguous": [{"source": s, "name": n, "candidates": c} for (s, n), c in sorted(registry.ambiguous.items())],
        "sources": prov.report(),
    }
    (out_dir / "catalog.json").write_text(json.dumps(catalog_json, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out_dir / "scores.json").write_text(json.dumps(scores_json, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary_json, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out_dir / "status.json").write_text(json.dumps(status_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (data_dir / "unmatched_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"kept": len(rows), "dropped": dict(dropped), "models": len(used_models), "frontier": len(frontier),
            "benchmarks": len(catalog_json["benchmarks"]), "changelog_entry": entry is not None,
            "unmatched": len(registry.unmatched), "unknown_domains": dict(prov.unknown_domains),
            "provenance": dict(prov.counts)}
