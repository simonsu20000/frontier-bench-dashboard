import json
import sys
import types
from datetime import date

from pipeline.radar import llm
from pipeline.radar.state import RadarState


def test_state_roundtrip_and_dedupe(tmp_path):
    st = RadarState(tmp_path)
    assert st.append_release({"key": "arxiv:1", "first_seen": "2026-09-16", "name": "A"})
    assert not st.append_release({"key": "arxiv:1", "first_seen": "2026-09-16", "name": "A"})
    assert st.append_mention({"vendor": "openai", "doc_url": "u", "benchmarks": ["hle"], "doc_date": "2026-09-10"})
    assert not st.append_mention({"vendor": "openai", "doc_url": "u", "benchmarks": ["hle"], "doc_date": "2026-09-10"})
    st.append_weekly({"week_of": "2026-09-14", "rows": []})
    st.seen["docs"]["old"] = "2025-01-01"
    st.seen["docs"]["new"] = "2026-09-01"
    st.llm_cache["k"] = {"v": "1", "at": "2026-01-01", "out": {}}
    st.prune(date(2026, 9, 16))
    assert "old" not in st.seen["docs"] and "new" in st.seen["docs"] and "k" not in st.llm_cache
    st.save()
    st2 = RadarState(tmp_path)
    assert st2.has_release("arxiv:1") and st2.has_mention("openai", "u") and st2.weekly_for("2026-09-14")
    assert (tmp_path / "releases-2026.jsonl").exists()
    st2.save()  # nothing new: no duplicate lines
    assert len((tmp_path / "releases-2026.jsonl").read_text().splitlines()) == 1


def test_llm_judge_uses_cache_and_fake_client(monkeypatch):
    cfg = {"llm": {"model": "claude-haiku-4-5", "batch": 8, "max_requests": 2, "max_tokens": 1024}}
    cache = {"arxiv:cached": {"v": llm.PROMPT_VERSION, "at": "2026-09-15", "out": {"is_llm_benchmark": True, "confidence": 0.9}}}
    calls = []

    class FakeMessages:
        def parse(self, **kw):
            calls.append(kw)
            items = [{"key": "arxiv:new", "is_llm_benchmark": True, "confidence": 0.8, "canonical_name": "NewBench", "domain": "coding",
                      "has_leaderboard": True, "reported_best_score": 41.0, "summary_en": "A coding benchmark.", "summary_zh": "一个编程基准。"},
                     {"key": "arxiv:stranger", "is_llm_benchmark": False, "confidence": 0.9, "canonical_name": "x", "domain": "weird",
                      "has_leaderboard": False, "reported_best_score": 250.0, "summary_en": "", "summary_zh": ""}]
            Batch = kw["output_format"]
            return types.SimpleNamespace(parsed_output=Batch(items=items))

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=FakeMessages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.delenv("RADAR_LLM_MODEL", raising=False)
    out = llm.judge([{"key": "arxiv:cached", "title": "c"}, {"key": "arxiv:new", "title": "n", "abstract": "a"}], cache, cfg, "2026-09-16", log=lambda *a: None)
    assert out["arxiv:cached"]["confidence"] == 0.9 and len(calls) == 1
    assert out["arxiv:new"]["canonical_name"] == "NewBench" and cache["arxiv:new"]["v"] == llm.PROMPT_VERSION
    assert "arxiv:stranger" not in out                                # keys we did not ask about are ignored
    assert calls[0]["model"] == "claude-haiku-4-5"


def test_llm_judge_survives_client_failure(monkeypatch):
    class Boom:
        def parse(self, **kw):
            raise RuntimeError("rate limited")
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=Boom())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    out = llm.judge([{"key": "arxiv:x", "title": "t"}], {}, {"llm": {"model": "m", "batch": 8, "max_requests": 2}}, "2026-09-16", log=lambda *a: None)
    assert out == {}
