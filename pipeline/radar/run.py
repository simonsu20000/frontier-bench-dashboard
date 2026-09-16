"""CLI: python -m pipeline.radar.run [--date YYYY-MM-DD] [--offline] [--no-llm] [--force-weekly]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from ..http import Http
from ..provenance import Provenance
from ..sources.base import run_source
from . import llm as llm_mod
from .build import build_radar
from .feeds import ArxivRss, HfDailyPapers, HfDatasets, HfSpaces, RadarSnapshot, epoch_new_benchmarks
from .filter import extract_best, extract_name, merge, score, tag_domain
from .names import NameIndex
from .state import RadarState
from .vendors import GithubOrgRepos, HfModelCards, RadarModelCards, VendorRss, VendorSitemap, md_table_cells

ROOT = Path(__file__).resolve().parent.parent.parent


def load_yaml(p: Path):
    return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}


def first_sentence(text: str, limit: int = 160) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    import re
    s = re.split(r"(?<=[.!?])\s+", text)[0]
    return (s[: limit - 1] + "…") if len(s) > limit else s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--force-weekly", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "site" / "data"))
    ap.add_argument("--cache", default=str(ROOT / "data" / "raw" / "radar"))
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()

    cfg = load_yaml(ROOT / "config" / "radar.yml")
    aliases_cfg = load_yaml(ROOT / "config" / "benchmark_aliases.yml")
    sources_cfg = load_yaml(ROOT / "config" / "sources.yml")
    epoch_cfg = load_yaml(ROOT / "config" / "epoch_files.yml")
    prov = Provenance(sources_cfg, epoch_cfg)
    state = RadarState(ROOT / "data" / "radar")
    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    http = None if args.offline else Http(cache_dir)
    statuses: list[dict] = []
    fb = int(cfg["windows"]["feed_backfill_days"])

    # ---------------- 1. new-release candidates ----------------
    feeds = [ArxivRss(c, today) for c in ("cs.CL", "cs.AI", "cs.LG", "cs.CV")] + [
        HfDailyPapers(today, fb), HfDatasets(today, fb), HfSpaces(today, fb), RadarSnapshot(today, fb)]
    cands: list[dict] = []
    for src in feeds:
        res = run_source(src, http, cache_dir, offline=args.offline, today=today, codec=dict)
        statuses.append(res.status.to_dict())
        print(f"[{src.id:14s}] {res.status.status:7s} items={len(res.records):4d} {res.status.error or ''}")
        cands.extend(res.records)
    epoch_cands, state.seen["epoch"] = epoch_new_benchmarks(ROOT, state.seen.get("epoch") or [], today)
    cands.extend(epoch_cands)

    merged = merge(cands)
    fcfg = cfg["filter"]
    scored = []
    for c in merged:
        if state.has_release(c["key"]):
            continue
        c["best_reported"] = extract_best(c.get("abstract") or "")
        c["score"], c["reasons"] = score(c, cfg)
        if c["score"] >= int(fcfg["candidate_min"]):
            scored.append(c)
    scored.sort(key=lambda c: (-c["score"], c.get("date") or ""))
    print(f"candidates: {len(cands)} raw -> {len(merged)} merged -> {len(scored)} scored >= {fcfg['candidate_min']}")

    # ---------------- 2. optional LLM second pass ----------------
    verdicts: dict[str, dict] = {}
    use_llm = llm_mod.enabled(not args.no_llm)
    if use_llm:
        borderline = [c for c in scored if c["score"] < int(fcfg["accept_min"]) + 3][: int(fcfg["llm_per_run"])]
        verdicts = llm_mod.judge(borderline, state.llm_cache, cfg, today.isoformat())
    llm_info = {"enabled": use_llm, "model": (os.environ.get("RADAR_LLM_MODEL") or cfg["llm"].get("model")) if use_llm else None,
                "judged_today": len(verdicts)}

    # ---------------- 3. accept releases ----------------
    accepted = 0
    for c in scored:
        v = verdicts.get(c["key"])
        if v and not v.get("is_llm_benchmark") and v.get("confidence", 0) >= 0.6:
            state.seen["cands"][c["key"]] = today.isoformat()
            continue
        ok = c["score"] >= int(fcfg["accept_min"]) or (v and v.get("is_llm_benchmark") and v.get("confidence", 0) >= 0.5)
        if not ok:
            if not use_llm and c["score"] >= int(fcfg["candidate_min"]) + 1 and c.get("kind") in ("paper", "dataset", "space"):
                pass  # published as low-confidence below
            else:
                state.seen["cands"][c["key"]] = today.isoformat()
                continue
        if accepted >= int(fcfg["per_day_publish"]):
            break
        best = c.get("best_reported")
        if v and v.get("reported_best_score") is not None:
            best = {"score": v["reported_best_score"], "metric": "reported", "source": "llm"}
        rec = {
            "key": c["key"], "first_seen": today.isoformat(), "date": c.get("date") or today.isoformat(),
            "name": (v or {}).get("canonical_name") or c.get("name") or extract_name(c.get("title", "")),
            "title": c.get("title", ""), "url": c.get("url", ""), "code_url": c.get("code_url", ""), "hf_url": c.get("hf_url", ""),
            "kind": c.get("kind", "paper"), "sources": c.get("sources", []), "org": c.get("org", ""), "upvotes": c.get("upvotes", 0),
            "score": c["score"], "reasons": c.get("reasons", []),
            "domain": (v or {}).get("domain") or tag_domain(c.get("abstract") or "", cfg["domains"], title=c.get("title", "")),
            "best_reported": best, "llm": ({"is_bench": v.get("is_llm_benchmark"), "conf": v.get("confidence"), "has_leaderboard": v.get("has_leaderboard")} if v else None),
            "summary_en": (v or {}).get("summary_en") or first_sentence(c.get("abstract") or ""),
            "summary_zh": (v or {}).get("summary_zh") or "",
            "conf": "high" if (c["score"] >= int(fcfg["accept_min"]) or (v and v.get("confidence", 0) >= 0.6)) else "low",
            "abstract_600": (c.get("abstract") or "")[:600],
        }
        if state.append_release(rec):
            accepted += 1
        state.seen["cands"][c["key"]] = today.isoformat()
    print(f"releases: +{accepted} accepted (total {len(state.releases)})")

    # ---------------- 4. vendor attention ----------------
    catalog = json.loads((ROOT / "site" / "data" / "catalog.json").read_text()) if (ROOT / "site" / "data" / "catalog.json").exists() else {"benchmarks": []}
    radar_cards = RadarModelCards()
    res_cards = run_source(radar_cards, http, cache_dir, offline=args.offline, today=today, codec=dict)
    statuses.append(res_cards.status.to_dict())
    radar_yml = {"benchmarks": res_cards.extras.get("benchmarks", [])}
    learned = [r for r in state.releases if r.get("conf") == "high" and r.get("score", 0) >= int(fcfg["learned_name_min_score"]) and r.get("kind") in ("paper", "dataset", "space")]
    names = NameIndex.build(catalog, aliases_cfg, radar_yml, learned)
    org_names = cfg.get("vendor_org_names", {})
    seen_docs = set(state.seen["docs"].keys())
    lookback = int(cfg["windows"]["doc_lookback_days"])
    docs: list[dict] = []
    for v in cfg["vendors"]:
        brands = prov._brand_tokens(org_names.get(v["id"], v["name"]))
        srcs = []
        if v.get("hf_authors"):
            srcs.append(HfModelCards(v, today, lookback, seen_docs))
        if v.get("rss"):
            srcs.append(VendorRss(v, today, lookback, seen_docs, brands))
        if v.get("sitemap"):
            srcs.append(VendorSitemap(v, today, lookback, seen_docs, brands))
        if v.get("github_orgs"):
            srcs.append(GithubOrgRepos(v, today, lookback, seen_docs))
        for s in srcs:
            res = run_source(s, http, cache_dir, offline=args.offline, today=today, codec=dict)
            statuses.append(res.status.to_dict())
            print(f"[{s.id:18s}] {res.status.status:7s} docs={len(res.records):3d} {res.status.note or ''} {res.status.error or ''}")
            docs.extend(res.records)
    radar_map = cfg.get("radar_vendor_map", {})
    for d in res_cards.records:
        vid = radar_map.get(d.get("vendor_label", ""))
        if not vid:
            continue
        keys = set()
        for rb in d.get("radar_benchmarks", []):
            k = names.lookup_name(rb.replace("_", " ")) or (f"radar:{rb}" if f"radar:{rb}" in names.entries else None)
            if k:
                keys.add(k)
        docs.append({**d, "vendor": vid, "keys": sorted(keys)})

    new_mentions = 0
    for d in docs:
        url = d.get("doc_url") or ""
        if not url or state.has_mention(d["vendor"], url):
            continue
        if "keys" in d:
            keys = set(d["keys"])
        else:
            text = d.get("text") or ""
            keys = names.match_cells(md_table_cells(text)) | names.match_prose(text) if text else names.match_prose(d.get("doc_title", ""))
        state.seen["docs"][url] = today.isoformat()
        if not keys:
            continue
        if state.append_mention({"vendor": d["vendor"], "doc_url": url, "doc_title": d.get("doc_title", ""), "doc_date": d.get("doc_date") or today.isoformat(),
                                 "first_seen": today.isoformat(), "source": d.get("source", ""), "benchmarks": sorted(keys)}):
            new_mentions += 1
    print(f"mentions: +{new_mentions} docs with benchmark mentions (total {len(state.mentions)})")

    # ---------------- 5. build + save ----------------
    summary = build_radar(ROOT, Path(args.out), state, names, statuses, cfg, today, llm_info, force_weekly=args.force_weekly)
    state.prune(today)
    state.save()
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
