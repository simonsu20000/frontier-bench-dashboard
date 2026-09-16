import json
from datetime import date
from pathlib import Path

from pipeline.radar.feeds import ArxivRss, HfDailyPapers, HfDatasets, HfSpaces, RadarSnapshot, epoch_new_benchmarks

FIX = Path(__file__).resolve().parent / "fixtures" / "radar"
TODAY = date(2026, 9, 16)


def test_arxiv_rss_parse():
    recs, extras = ArxivRss("cs.CL", TODAY).parse((FIX / "arxiv_cs_cl.xml").read_text())
    assert len(recs) == 6
    r = recs[0]
    assert r["arxiv_id"] and r["url"].startswith("https://arxiv.org/abs/") and r["announce_type"] in ("new", "cross", "replace")
    assert r["abstract"] and r["source"] == "arxiv-cs-cl"
    assert all("Announce Type" not in x["abstract"] for x in recs)


def test_hf_daily_papers_parse():
    raw = {"2026-09-15": json.loads((FIX / "hf_daily.json").read_text())}
    recs, extras = HfDailyPapers(TODAY).parse(raw)
    assert len(recs) == 5 and all(r["arxiv_id"] for r in recs) and recs[0]["upvotes"] >= 0
    assert recs[0]["hf_url"].startswith("https://huggingface.co/papers/") and extras["upstream_updated_at"]


def test_hf_datasets_and_spaces_window():
    ds = json.loads((FIX / "hf_datasets.json").read_text())
    recs, _ = HfDatasets(TODAY, days=3).parse(ds)
    assert all(r["kind"] == "dataset" and r["repo"] for r in recs)
    old, _ = HfDatasets(date(2027, 1, 1), days=3).parse(ds)
    assert old == []
    sp = json.loads((FIX / "hf_spaces.json").read_text())
    recs, _ = HfSpaces(TODAY, days=3).parse(sp)
    assert all(r["kind"] == "space" for r in recs)


def test_radar_snapshot_parse_filters_categories_and_sources():
    snap = json.loads((FIX / "radar_snapshot.json").read_text())
    recs, extras = RadarSnapshot(TODAY).parse({"2026-09-15": snap, "2026-09-14": {"error": "404"}})
    assert recs and all(set(r["tags"]) & {"benchmark", "evaluation"} for r in recs)
    assert all(r["source"] == "radar" for r in recs)


def test_epoch_new_benchmarks_bootstraps_then_diffs(tmp_path):
    (tmp_path / "site" / "data").mkdir(parents=True)
    cat = {"benchmarks": [{"id": "a", "name": "A", "official_url": "https://a"}, {"id": "b", "name": "B", "release_date": "2026-09-01", "category": "coding"}]}
    (tmp_path / "site" / "data" / "catalog.json").write_text(json.dumps(cat))
    cands, seen = epoch_new_benchmarks(tmp_path, [], TODAY)
    assert cands == [] and seen == ["a", "b"]                       # first run: seed silently
    cands, seen = epoch_new_benchmarks(tmp_path, ["a"], TODAY)
    assert [c["slug"] for c in cands] == ["b"] and cands[0]["kind"] == "epoch" and seen == ["a", "b"]
