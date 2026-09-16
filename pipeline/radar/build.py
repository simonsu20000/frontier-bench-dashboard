"""Assemble site/data/radar.json from radar state + the scored dashboard data."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .names import NameIndex
from .rank import attention_rows, hard_new, headroom, week_of, weekly_snapshot
from .state import RadarState


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def frontier_coverage(scores: dict | None, catalog: dict | None) -> dict[str, int]:
    if not scores or not catalog:
        return {}
    frontier = {m["id"] for m in catalog.get("models", []) if m.get("frontier")}
    idx = {c: i for i, c in enumerate(scores["cols"])}
    seen: dict[str, set] = defaultdict(set)
    for r in scores["rows"]:
        if r[idx["a"]] == 1 and r[idx["m"]] in frontier:
            seen[r[idx["b"]]].add(r[idx["m"]])
    return {b: len(ms) for b, ms in seen.items()}


def build_radar(root: Path, out_dir: Path, state: RadarState, names: NameIndex, statuses: list[dict], cfg: dict,
                today: date, llm_info: dict, force_weekly: bool = False) -> dict:
    root, out_dir = Path(root), Path(out_dir)
    catalog = _load(root / "site" / "data" / "catalog.json") or {"benchmarks": [], "models": []}
    scores = _load(root / "site" / "data" / "scores.json")
    summary = _load(root / "site" / "data" / "summary.json") or {"sota": {}}
    bench_by_id = {b["id"]: b for b in catalog.get("benchmarks", [])}
    cov_by_bid = frontier_coverage(scores, catalog)
    releases_by_key = {r["key"]: r for r in state.releases}

    def bid_of(key: str) -> str | None:
        e = names.entries.get(key)
        if e and e.bid and e.bid in bench_by_id:
            return e.bid
        if key in bench_by_id:
            return key
        if key.startswith("epoch:") and key[6:] in bench_by_id:
            return key[6:]
        return None

    def has_leaderboard(key: str) -> bool:
        e = names.entries.get(key)
        b = bench_by_id.get(bid_of(key) or "")
        return bool((e and e.url) or (b and b.get("official_url")))

    def sota_for(key: str):
        b = bid_of(key)
        return summary.get("sota", {}).get(b) if b else None

    cov_by_key = {k: cov_by_bid.get(bid_of(k) or "", 0) for k in {*names.entries.keys(), *bench_by_id.keys()}}
    rows = attention_rows(state.mentions, today, cfg, cov_by_key, has_leaderboard, releases_by_key, sota_for)

    # release dates + headroom per key
    release_dates: dict[str, str] = {}
    headrooms: dict[str, tuple] = {}
    for r in rows:
        k = r["key"]
        e = names.entries.get(k)
        b = bench_by_id.get(bid_of(k) or "")
        rel = releases_by_key.get(k)
        release_dates[k] = (e.released if e and e.released else "") or (b.get("release_date") if b else "") or (rel.get("date") if rel else "") or ""
        best = (rel or {}).get("best_reported")
        headrooms[k] = headroom(b, sota_for(k), best)
        r["bid"] = bid_of(k)
        r["name"] = names.display(k) if k in names.entries else (b["name"] if b else (rel or {}).get("name", k))
        r["sota"] = sota_for(k)
        r["headroom"], r["headroom_src"] = headrooms[k]
        r["release_date"] = release_dates[k]
        r["url"] = (e.url if e else "") or (b.get("official_url") if b else "") or ((rel or {}).get("url") or "")
        r["domain"] = (b.get("category") if b else "") or (e.domain if e else "") or ((rel or {}).get("domain") or "other")

    # weekly frozen snapshot
    wk = week_of(today)
    snap = state.weekly_for(wk)
    if snap is None or force_weekly:
        prev = state.latest_weekly(before=wk)
        snap = weekly_snapshot(rows, today, prev)
        if force_weekly and state.weekly_for(wk):
            state.weekly = [w for w in state.weekly if w["week_of"] != wk]
        state.append_weekly(snap)
    by_key = {r["key"]: r for r in rows}
    attention = []
    for s in snap["rows"][:30]:
        r = by_key.get(s["key"])
        if not r:
            continue
        attention.append({**r, "rank": s["rank"], "prev_rank": s.get("prev_rank"), "is_new": s.get("is_new", False), "docs": r["docs"][:5]})

    hard, unscored = hard_new(rows, release_dates, headrooms, today, cfg)
    for h in hard:
        rel = releases_by_key.get(h["key"])
        h["best_reported"] = (rel or {}).get("best_reported")
        h["docs"] = h["docs"][:3]
    for u in unscored:
        u["docs"] = u["docs"][:3]

    # releases feed (last N days)
    shown_cut = (today - timedelta(days=int(cfg["windows"]["releases_shown_days"]))).isoformat()
    releases = []
    for r in sorted(state.releases, key=lambda x: (x.get("date") or "", x.get("first_seen") or ""), reverse=True):
        if (r.get("first_seen") or "") < shown_cut and (r.get("date") or "") < shown_cut:
            continue
        b = bench_by_id.get(bid_of(r["key"]) or "")
        releases.append({"key": r["key"], "date": r.get("date"), "first_seen": r.get("first_seen"), "name": r.get("name"), "title": r.get("title"),
                         "url": r.get("url"), "code_url": r.get("code_url"), "hf_url": r.get("hf_url"), "kind": r.get("kind"), "sources": r.get("sources", []),
                         "org": r.get("org", ""), "upvotes": r.get("upvotes", 0), "score": r.get("score"), "conf": r.get("conf", "low"),
                         "domain": r.get("domain", "other"), "summary_en": r.get("summary_en", ""), "summary_zh": r.get("summary_zh", ""),
                         "best_reported": r.get("best_reported"), "bid": b["id"] if b else None,
                         "sota": summary.get("sota", {}).get(b["id"]) if b else None,
                         "vendors": by_key.get(r["key"], {}).get("vendors", [])})
        if len(releases) >= 400:
            break

    # history of weekly ranks
    weeks = sorted({w["week_of"] for w in state.weekly})[-12:]
    hist_keys = {s["key"] for s in snap["rows"][:30]}
    ranks = {k: [] for k in hist_keys}
    for wof in weeks:
        w = state.weekly_for(wof)
        rk = {s["key"]: s["rank"] for s in (w or {}).get("rows", [])}
        for k in hist_keys:
            ranks[k].append(rk.get(k))

    mention_cut = (today - timedelta(days=int(cfg["windows"]["mention_days"]))).isoformat()
    recent_m = [m for m in state.mentions if (m.get("doc_date") or "") >= mention_cut]
    today_s = today.isoformat()
    week_cut = (today - timedelta(days=7)).isoformat()
    vendors_cfg = {v["id"]: {"name": v["name"], "ok": any(s.get("status") == "ok" for s in statuses if s.get("id", "").endswith("-" + v["id"])),
                             "note": v.get("note", "")} for v in cfg["vendors"]}
    out = {
        "generated_at": today_s, "week_of": snap["week_of"], "prev_week_of": snap.get("prev_week_of"),
        "llm": llm_info,
        "domains": {k: {"en": v["en"], "zh": v["zh"]} for k, v in cfg["domains"].items()} | {"other": {"en": "Other", "zh": "其他"}},
        "vendors": vendors_cfg,
        "sources": statuses,
        "kpis": {"new_today": sum(1 for r in state.releases if r.get("first_seen") == today_s),
                 "new_7d": sum(1 for r in state.releases if (r.get("first_seen") or "") >= week_cut),
                 "vendors_active_60d": len({m["vendor"] for m in recent_m}), "docs_60d": len(recent_m),
                 "attention_n": len(rows)},
        "releases": releases, "attention": attention, "hard_new": hard, "unscored_new": unscored,
        "history": {"weeks": weeks, "ranks": ranks},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "radar.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"releases_shown": len(releases), "attention": len(attention), "hard_new": len(hard), "unscored": len(unscored),
            "week_of": snap["week_of"], "kpis": out["kpis"]}
