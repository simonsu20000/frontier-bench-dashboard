from pathlib import Path

import yaml

from pipeline.provenance import Provenance
from pipeline.records import ScoreRecord

ROOT = Path(__file__).resolve().parent.parent


def make():
    return Provenance(yaml.safe_load((ROOT / "config" / "sources.yml").read_text()),
                      yaml.safe_load((ROOT / "config" / "epoch_files.yml").read_text()))


def rec(**kw):
    base = dict(source_id="epoch", benchmark_id="x", model_raw="m", score=1.0, org="Anthropic", source_file="hle_external.csv")
    base.update(kw)
    return ScoreRecord(**base)


def test_official_leaderboard_by_domain():
    p = make()
    r = rec(source_url="https://www.tbench.ai/leaderboard/terminal-bench/2.0", source_name="")
    assert p.classify(r) == "official_leaderboard"
    assert r.source_name == "Terminal-Bench leaderboard"
    assert p.keep(r)


def test_vendor_domain_is_vendor_only_for_own_models():
    p = make()
    own = rec(source_url="https://www.anthropic.com/news/claude-opus-4-5", source_name="Announcement", org="Anthropic")
    assert p.classify(own) == "vendor_reported"
    assert not p.keep(own)
    other = rec(source_url="https://cursor.com/blog/cursorbench", source_name="", org="Anthropic")
    assert p.classify(other) == "third_party"
    assert other.source_name == "Cursor evaluation"


def test_arxiv_title_mentioning_vendor_is_vendor():
    p = make()
    r = rec(source_url="https://arxiv.org/abs/2403.05530", source_name="Gemini 1.5 Report", org="Google DeepMind")
    assert p.classify(r) == "vendor_reported"
    paper = rec(source_url="https://arxiv.org/abs/2311.12022", source_name="GPQA: A Graduate-Level Benchmark", org="Anthropic")
    assert p.classify(paper) == "third_party"
    tr = rec(source_url="https://arxiv.org/abs/1", source_name="Qwen Technical Report", org="MosaicML")
    assert p.classify(tr) == "vendor_reported"  # generic "technical report" cue


def test_github_and_huggingface_owner_rule():
    p = make()
    assert p.classify(rec(source_url="https://github.com/deepseek-ai/DeepSeek-V3", source_name="", org="DeepSeek")) == "vendor_reported"
    assert p.classify(rec(source_url="https://github.com/lechmazur/writing", source_name="", org="DeepSeek")) == "third_party"
    assert p.classify(rec(source_url="https://huggingface.co/Qwen/Qwen3-235B-A22B", source_name="", org="Alibaba")) == "vendor_reported"


def test_no_link_uses_file_default_and_unknown_domain_is_excluded():
    p = make()
    r = rec(source_url="", source_name="", source_file="hle_external.csv")
    assert p.classify(r) == "official_leaderboard"
    assert "scale.com" in r.source_url
    unknown = rec(source_url="https://example.org/leaderboard", source_name="")
    assert p.classify(unknown) == "unclassified"
    assert not p.keep(unknown)
    assert p.report()[0]["domain"] == "example.org"
    url_in_source = rec(source_url="", source_name="https://arcprize.org/leaderboard")
    assert p.classify(url_in_source) == "official_leaderboard"
    assert url_in_source.source_url == "https://arcprize.org/leaderboard"
