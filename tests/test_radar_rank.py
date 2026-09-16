from datetime import date
from pathlib import Path

import yaml

from pipeline.radar.rank import attention_rows, hard_new, headroom, week_of, weekly_snapshot

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "radar.yml").read_text())
TODAY = date(2026, 9, 16)


def mention(vendor, url, d, keys, source="hf"):
    return {"vendor": vendor, "doc_url": url, "doc_title": url, "doc_date": d, "first_seen": d, "source": source, "benchmarks": keys}


def test_attention_rows_weights_and_window():
    ms = [mention("openai", "u1", "2026-09-10", ["swe-bench-verified", "hle"]),
          mention("anthropic", "u2", "2026-09-12", ["swe-bench-verified"]),
          mention("deepseek", "u3", "2026-09-01", ["swe-bench-verified"], source="radar"),
          mention("qwen", "u4", "2026-05-01", ["hle"])]  # outside 60-day window
    rows = attention_rows(ms, TODAY, CFG, {"swe-bench-verified": 10, "hle": 2}, lambda k: k == "swe-bench-verified", {}, lambda k: None)
    by = {r["key"]: r for r in rows}
    swe, hle = by["swe-bench-verified"], by["hle"]
    assert swe["v"] == 3 and swe["d"] == 2.5 and swe["rank"] == 1 and swe["importance_norm"] == 1.0
    assert hle["v"] == 1 and hle["n_docs"] == 1                     # qwen mention too old
    assert swe["importance"] > hle["importance"] and rows[0]["key"] == "swe-bench-verified"


def test_headroom_cases():
    assert headroom({"unit": "pct", "direction": "higher"}, {"score": 46.5}, None) == (0.535, "sota")
    assert headroom({"unit": "elo", "direction": "higher"}, {"score": 1500}, None) == (None, None)
    assert headroom(None, None, {"score": 23.4}) == (0.766, "paper")
    assert headroom(None, None, None) == (None, None)


def test_weekly_snapshot_and_hard_new():
    rows = [{"key": "a", "rank": 1, "importance": 0.9, "importance_norm": 1.0, "v": 3, "d": 3.0},
            {"key": "b", "rank": 2, "importance": 0.5, "importance_norm": 0.55, "v": 1, "d": 1.0},
            {"key": "c", "rank": 3, "importance": 0.3, "importance_norm": 0.33, "v": 1, "d": 1.0}]
    prev = {"week_of": "2026-09-07", "rows": [{"key": "b", "rank": 1}, {"key": "a", "rank": 2}]}
    snap = weekly_snapshot(rows, TODAY, prev)
    assert snap["week_of"] == "2026-09-14" == week_of(TODAY)
    by = {r["key"]: r for r in snap["rows"]}
    assert by["a"]["prev_rank"] == 2 and by["b"]["prev_rank"] == 1 and by["c"]["is_new"] is True and by["a"]["is_new"] is False
    hard, unscored = hard_new(rows, {"a": "2025-06-01", "b": "2026-08-01", "c": "2023-01-01"}, {"a": (0.2, "sota"), "b": (0.8, "paper"), "c": (0.9, "sota")}, TODAY, CFG)
    assert [h["key"] for h in hard] == ["b", "a"]                   # c too old; b: 0.55*0.8 > a: 1.0*0.2
    assert hard[0]["hard_score"] == 0.44 and unscored == []
