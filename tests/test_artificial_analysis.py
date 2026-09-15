import pytest

from pipeline.sources.artificial_analysis import ArtificialAnalysisSource


def test_parse_documented_shape():
    raw = {"generated_at": "2026-09-15T00:00:00Z", "data": [
        {"name": "GPT-5.2 (high)", "slug": "gpt-5-2-high", "model_creator": {"name": "OpenAI", "slug": "openai"}, "release_date": "2025-12-11",
         "evaluations": {"artificial_analysis_intelligence_index": 71.2, "gpqa": 0.912, "hle": 0.31, "livecodebench": 0.86, "unknown_metric": 0.5}},
        {"name": "no-evals", "slug": "x", "evaluations": None},
        "garbage",
    ]}
    recs, extras = ArtificialAnalysisSource().parse(raw)
    by = {r.benchmark_id: r for r in recs}
    assert set(by) == {"aa-intelligence-index", "gpqa-diamond", "hle", "livecodebench"}
    assert by["aa-intelligence-index"].score == 71.2 and by["aa-intelligence-index"].unit == "score"
    assert abs(by["gpqa-diamond"].score - 91.2) < 1e-9 and by["gpqa-diamond"].unit == "pct"
    assert by["hle"].org == "OpenAI" and by["hle"].release_date == "2025-12-11"
    assert by["hle"].source_type == "third_party" and by["hle"].source_url.endswith("/models/gpt-5-2-high")
    assert extras["upstream_updated_at"] == "2026-09-15"


def test_parse_rejects_unexpected_payload():
    with pytest.raises(RuntimeError):
        ArtificialAnalysisSource().parse({"error": "unauthorized"})
