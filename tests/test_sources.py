from pipeline.sources.aider import AiderSource
from pipeline.sources.arcprize import ArcPrizeSource
from pipeline.sources.livebench import LiveBenchSource
from pipeline.sources.swebench import SWEBenchSource


def test_swebench_parse_marks_bash_only_and_skips_warnings():
    raw = {"leaderboards": [{"name": "Verified", "results": [
        {"model_display": "Claude 4.5 Opus", "model_org": "Anthropic", "resolved": 79.2, "date": "2025-12-05", "agent": "Sonar Foundation Agent", "name": "Sonar + Opus", "checked": True},
        {"model_display": "GPT-5", "model_org": "OpenAI", "resolved": 65.0, "date": "2025-08-10", "agent": "mini-SWE-agent", "name": "mini + GPT-5", "checked": False, "reasoning_effort": "high"},
        {"model_display": "Broken", "resolved": 10.0, "date": "2025-01-01", "agent": "x", "name": "bad", "warning": "not reproducible"},
        {"model_display": "", "resolved": 50.0, "date": "2025-01-01", "agent": "x", "name": "anonymous"},
    ]}]}
    recs, extras = SWEBenchSource().parse(raw)
    assert [r.model_raw for r in recs] == ["Claude 4.5 Opus", "GPT-5"]
    assert recs[0].extra["checked"] is True and "verified by maintainers" in recs[0].note
    assert recs[1].scaffold == "mini-SWE-agent (bash-only)" and recs[1].variant == "high"
    assert all(r.source_type == "official_leaderboard" and r.benchmark_id == "swe-bench-verified" for r in recs)
    assert extras["upstream_updated_at"] == "2025-12-05"


def test_arcprize_parse_filters_humans_and_scales():
    raw = {"boards": {"v2": {"generatedAt": "2026-09-04T14:38:06.319Z", "evaluations": [
        {"datasetId": "v2_Semi_Private", "datasetDisplayName": "ARC-AGI-2", "modelId": "human", "modelDisplayName": "Human Panel", "providerId": "Human", "score": 1, "display": True},
        {"datasetId": "v2_Semi_Private", "datasetDisplayName": "ARC-AGI-2", "modelId": "gpt-6-astra-max", "modelDisplayName": "GPT-6 Astra (Max)", "providerId": "openai",
         "providerDisplayName": "OpenAI", "modelReleaseDate": "2026-09-03", "score": 0.95, "costPerTask": 1.4, "display": True, "modelType": "CoT"},
        {"datasetId": "v2_Semi_Private", "modelId": "hidden", "modelDisplayName": "Hidden", "providerId": "x", "score": 0.5, "display": False},
    ]}}, "models": [{"id": "gpt-6-astra-max", "modelReleaseDate": "2026-09-03"}], "errors": {}}
    recs, extras = ArcPrizeSource().parse(raw)
    assert len(recs) == 1
    r = recs[0]
    assert r.benchmark_id == "arc-agi-2" and abs(r.score - 95.0) < 1e-9 and r.org == "OpenAI"
    assert r.release_date == "2026-09-03" and r.eval_date == "2026-09-04" and "$1.4/task" in r.note
    assert extras["upstream_updated_at"] == "2026-09-04"


def test_livebench_global_average_is_mean_of_category_means():
    table = "model,a1,a2,b1\nmodel-x,80,60,90\nmodel-y,50,,70\n"
    cats = {"A": ["a1", "a2"], "B": ["b1"]}
    recs, extras = LiveBenchSource().parse({"date": "2026-06-25", "file": "table_2026_06_25.csv", "table": table, "categories": cats})
    by = {r.model_raw: r for r in recs}
    assert abs(by["model-x"].score - 80.0) < 1e-9   # (70 + 90) / 2
    assert abs(by["model-y"].score - 60.0) < 1e-9   # (50 + 70) / 2, missing a2 ignored
    assert by["model-x"].eval_date == "2026-06-25" and by["model-x"].benchmark_id == "livebench"


def test_aider_parse():
    yml = """
- model: gpt-5 (high)
  pass_rate_2: 88.0
  pass_rate_1: 52.0
  edit_format: diff
  percent_cases_well_formed: 91.6
  date: 2025-08-23
  versions: 0.86.2.dev
  total_cost: 29.08
  reasoning_effort: high
- model: broken
  edit_format: diff
"""
    recs, extras = AiderSource().parse(yml)
    assert len(recs) == 1
    r = recs[0]
    assert r.model_raw == "gpt-5 (high)" and r.score == 88.0 and r.variant == "high" and r.eval_date == "2025-08-23"
    assert r.scaffold == "aider 0.86.2.dev" and "$29.08" in r.note
