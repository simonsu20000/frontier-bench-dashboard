import json
from pathlib import Path

from pipeline.build import build
from pipeline.records import ScoreRecord
from pipeline.sources.base import SourceResult, SourceStatus


def result(sid, records, extras=None):
    return SourceResult(records, SourceStatus(id=sid, name=sid, status="ok", records=len(records), upstream_updated_at="2026-09-10"), extras or {})


def make_results(metadata, score_official=80.0):
    meta, eci = metadata
    epoch_recs = [
        ScoreRecord(source_id="epoch", benchmark_id="gpqa-diamond", model_raw="gpt-5.2-2025-12-11_high", score=91.2, source_type="epoch_run",
                    source_name="Epoch AI independent evaluation", source_url="https://epoch.ai/benchmarks/gpqa-diamond", eval_date="2025-12-12", org="OpenAI", release_date="2025-12-11"),
        ScoreRecord(source_id="epoch", benchmark_id="gpqa-diamond", model_raw="claude-fable-5-1_xhigh", score=94.0, source_type="epoch_run",
                    source_name="Epoch AI independent evaluation", source_url="https://epoch.ai/benchmarks/gpqa-diamond", eval_date="2026-09-02", org="Anthropic", release_date="2026-09-01"),
        ScoreRecord(source_id="epoch", benchmark_id="swe-bench-verified", model_raw="gpt-5.2-2025-12-11_high", score=70.0, source_type="epoch_run",
                    source_name="Epoch AI independent evaluation", source_url="https://epoch.ai/benchmarks/swe-bench-verified", eval_date="2025-12-20", org="OpenAI", release_date="2025-12-11"),
        # vendor self-report: must be dropped
        ScoreRecord(source_id="epoch", benchmark_id="hle", model_raw="gpt-5.2-2025-12-11_high", score=40.0, source_file="hle_external.csv",
                    source_name="GPT-5.2 System Card", source_url="https://openai.com/index/gpt-5-2-system-card", org="OpenAI"),
        # unknown domain: dropped and reported
        ScoreRecord(source_id="epoch", benchmark_id="hle", model_raw="claude-fable-5-1_xhigh", score=46.0, source_file="hle_external.csv",
                    source_name="", source_url="https://mystery.example/x", org="Anthropic"),
    ]
    official = [
        ScoreRecord(source_id="swebench", benchmark_id="swe-bench-verified", model_raw="GPT-5.2 (high)", score=score_official, source_type="official_leaderboard",
                    source_name="SWE-bench Verified leaderboard", source_url="https://www.swebench.com/", eval_date="2026-01-10", scaffold="OpenHands", org="OpenAI"),
        ScoreRecord(source_id="swebench", benchmark_id="swe-bench-verified", model_raw="Custom Ensemble", score=99.0, source_type="official_leaderboard",
                    source_name="SWE-bench Verified leaderboard", source_url="https://www.swebench.com/", eval_date="2026-01-10", scaffold="TTS", org=""),
    ]
    return {
        "epoch": result("epoch", epoch_recs, {"model_metadata": meta, "eci": eci, "benchmarks": {}}),
        "swebench": result("swebench", official),
    }


def load(out: Path, name: str):
    return json.loads((out / name).read_text())


def test_build_outputs_and_authoritative_choice(project, metadata):
    out = project / "site" / "data"
    summary = build(project, out, make_results(metadata))
    assert summary["kept"] == 5 and summary["dropped"] == {"vendor_reported": 1, "unclassified": 1}
    assert summary["unknown_domains"] == {"mystery.example": 1}
    for f in ("catalog.json", "scores.json", "summary.json", "status.json"):
        assert (out / f).exists()
    scores = load(out, "scores.json")
    cols = scores["cols"]
    rows = [dict(zip(cols, r)) for r in scores["rows"]]
    swe = {r["m"]: r for r in rows if r["b"] == "swe-bench-verified" and r["a"] == 1}
    # Epoch's controlled run beats the higher official score for the same model
    assert swe["gpt-5-2"]["t"] == "epoch_run" and swe["gpt-5-2"]["s"] == 70.0
    alt = [r for r in rows if r["b"] == "swe-bench-verified" and r["m"] == "gpt-5-2" and r["a"] == 0]
    assert len(alt) == 1 and alt[0]["sc"] == "OpenHands" and alt[0]["mb"] == "exact"
    # unmatched official entry survives as an ext pseudo-model and never wins SOTA
    assert any(m.startswith("ext:swebench:") for m in swe)
    s = load(out, "summary.json")
    assert s["sota"]["swe-bench-verified"]["model_id"] == "gpt-5-2"
    assert s["sota"]["gpqa-diamond"]["model_id"] == "claude-fable-5-1"
    catalog = load(out, "catalog.json")
    ids = {m["id"] for m in catalog["models"]}
    assert {"gpt-5-2", "claude-fable-5-1"} <= ids
    fable = next(m for m in catalog["models"] if m["id"] == "claude-fable-5-1")
    assert fable["eci"] == 164.5 and fable["frontier"] is True
    report = json.loads((project / "data" / "unmatched_report.json").read_text())
    assert report["models"][0]["name"] == "Custom Ensemble"
    assert report["sources"][0]["domain"] == "mystery.example"


def test_changelog_records_new_sota_and_changes(project, metadata):
    out = project / "site" / "data"
    build(project, out, make_results(metadata))
    assert not (project / "data" / "changelog.jsonl").exists()
    # second build: GPT-5.2 official score changes (alternate only -> no change), Epoch GPQA for GPT-5.2 improves past Fable
    results = make_results(metadata, score_official=85.0)
    results["epoch"].records[0].score = 96.0
    summary = build(project, out, results)
    assert summary["changelog_entry"] is True
    lines = (project / "data" / "changelog.jsonl").read_text().splitlines()
    entry = json.loads(lines[-1])
    assert entry["changed"][0]["model_id"] == "gpt-5-2" and entry["changed"][0]["score"] == 96.0
    assert entry["new_sota"][0]["benchmark_id"] == "gpqa-diamond" and entry["new_sota"][0]["prev_model_id"] == "claude-fable-5-1"
    s = load(out, "summary.json")
    assert s["changelog"][0]["date"] == entry["date"]
