"""Importance (vendor attention), headroom and the weekly frozen snapshot."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta


def _days(a: str, b: str) -> int | None:
    try:
        return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days
    except (ValueError, TypeError):
        return None


def attention_rows(mentions: list[dict], today: date, cfg: dict, frontier_cov: dict[str, int],
                   has_leaderboard, releases_by_key: dict[str, dict], sota_for) -> list[dict]:
    """One row per benchmark key with vendor attention over the trailing window."""
    win = int(cfg["windows"]["mention_days"])
    cutoff = (today - timedelta(days=win)).isoformat()
    w, caps, dw = cfg["weights"], cfg["caps"], cfg.get("doc_weights", {})
    per: dict[str, dict] = defaultdict(lambda: {"vendors": set(), "docs": [], "doc_weight": 0.0, "last": ""})
    for m in mentions:
        d = m.get("doc_date") or m.get("first_seen") or ""
        if d < cutoff:
            continue
        for key in m.get("benchmarks", []):
            p = per[key]
            p["vendors"].add(m["vendor"])
            p["docs"].append({"vendor": m["vendor"], "title": m.get("doc_title", ""), "url": m["doc_url"], "date": d, "source": m.get("source", "")})
            p["doc_weight"] += float(dw.get(m.get("source", ""), 1.0))
            p["last"] = max(p["last"], d)
    rows = []
    for key, p in per.items():
        v = min(len(p["vendors"]), caps["vendors"]) / caps["vendors"]
        dsc = min(math.log1p(p["doc_weight"]) / math.log1p(caps["docs"]), 1.0)
        cov = min(frontier_cov.get(key, 0), caps["coverage"]) / caps["coverage"]
        lb = 1.0 if has_leaderboard(key) else 0.0
        age = _days(today.isoformat(), p["last"]) or 0
        rec = math.exp(-max(age, 0) / 30.0)
        imp = w["vendors"] * v + w["docs"] * dsc + w["coverage"] * cov + w["leaderboard"] * lb + w["recency"] * rec
        docs = sorted(p["docs"], key=lambda x: x["date"], reverse=True)
        rows.append({
            "key": key, "importance": round(imp, 4), "v": len(p["vendors"]), "d": round(p["doc_weight"], 1),
            "vendors": sorted(p["vendors"]), "n_docs": len(p["docs"]), "docs": docs[:5], "last_mention": p["last"],
            "coverage": frontier_cov.get(key, 0),
        })
    rows.sort(key=lambda r: (-r["importance"], r["key"]))
    mx = rows[0]["importance"] if rows else 1.0
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["importance_norm"] = round(r["importance"] / mx, 4) if mx else 0.0
    return rows


def headroom(bench: dict | None, sota: dict | None, best_reported: dict | None) -> tuple[float | None, str | None]:
    """Fraction of the scale still unclaimed. (None, None) when not meaningful."""
    if bench and sota and sota.get("score") is not None:
        if bench.get("unit") != "pct" or bench.get("direction", "higher") != "higher":
            return None, None
        ceiling = (bench.get("score_ceiling") or 1.0) * 100.0 if (bench.get("score_ceiling") or 0) <= 1.0 else bench.get("score_ceiling")
        ceiling = ceiling or 100.0
        return round(max(0.0, (ceiling - float(sota["score"])) / ceiling), 4), "sota"
    if best_reported and best_reported.get("score") is not None:
        return round(max(0.0, (100.0 - float(best_reported["score"])) / 100.0), 4), "paper"
    return None, None


def hard_new(rows: list[dict], release_dates: dict[str, str], headrooms: dict[str, tuple], today: date, cfg: dict, limit: int = 10):
    cutoff = (today - timedelta(days=int(cfg["windows"]["release_days"]))).isoformat()
    out, unscored = [], []
    for r in rows:
        rd = release_dates.get(r["key"], "")
        if not rd or rd < cutoff:
            continue
        h, src = headrooms.get(r["key"], (None, None))
        if h is None:
            unscored.append({**r, "release_date": rd})
            continue
        out.append({**r, "release_date": rd, "headroom": h, "headroom_src": src, "hard_score": round(r["importance_norm"] * h, 4)})
    out.sort(key=lambda r: -r["hard_score"])
    unscored.sort(key=lambda r: -r["importance_norm"])
    return out[:limit], unscored[:5]


def week_of(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()


def weekly_snapshot(rows: list[dict], today: date, prev: dict | None) -> dict:
    prev_ranks = {r["key"]: r["rank"] for r in (prev or {}).get("rows", [])}
    snap_rows = []
    for r in rows[:50]:
        snap_rows.append({"key": r["key"], "rank": r["rank"], "importance": r["importance"], "v": r["v"], "d": r["d"],
                          "prev_rank": prev_ranks.get(r["key"]), "is_new": r["key"] not in prev_ranks if prev else False})
    return {"week_of": week_of(today), "computed_at": today.isoformat(), "rows": snap_rows, "prev_week_of": (prev or {}).get("week_of")}
