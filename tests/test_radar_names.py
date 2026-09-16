from pathlib import Path

import yaml

from pipeline.radar.names import NameIndex, norm_cell
from pipeline.radar.vendors import md_table_cells

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "radar"
CATALOG = {"benchmarks": [
    {"id": "swe-bench-verified", "name": "SWE-bench Verified", "category": "coding", "official_url": "https://www.swebench.com/", "release_date": "2024-08-13"},
    {"id": "gpqa-diamond", "name": "GPQA Diamond", "category": "reasoning"},
    {"id": "hle", "name": "Humanity's Last Exam", "category": "reasoning"},
    {"id": "terminal-bench", "name": "Terminal-Bench 2.0", "category": "agentic"},
    {"id": "lmarena-text", "name": "LMArena Text (style control)", "category": "arena"},
]}


def build():
    aliases = yaml.safe_load((ROOT / "config" / "benchmark_aliases.yml").read_text())
    radar = yaml.safe_load((FIX / "model_cards.yml").read_text())
    return NameIndex.build(CATALOG, aliases, radar, learned=[{"key": "arxiv:2609.99999", "name": "AgentBench-2", "domain": "agentic", "date": "2026-09-15"}])


def test_norm_cell():
    assert norm_cell("**SWE-bench Verified** (Resolved %)") == "swe-bench-verified"
    assert norm_cell("τ²-bench") == "tau2-bench"


def test_deepseek_readme_table_matches_expected_benchmarks():
    idx = build()
    cells = md_table_cells((FIX / "readme_deepseek.md").read_text())
    keys = idx.match_cells(cells)
    for k in ("mmlu-pro", "gpqa-diamond", "hle", "livecodebench", "aime-2025", "hmmt", "codeforces", "aider-polyglot", "browsecomp", "simpleqa-verified", "swe-bench-verified", "swe-bench-multilingual", "terminal-bench"):
        assert k in keys, k
    assert idx.entries["swe-bench-verified"].bid == "swe-bench-verified"


def test_strict_tokens_and_prose():
    idx = build()
    assert idx.match_cells(["Arena"]) == {"lmarena-text"}          # exact strict cell is fine
    assert idx.match_cells(["arena"]) == set()                      # case matters for strict tokens
    assert "lmarena-text" not in idx.match_prose("the arena is crowded and swe agents are everywhere; HLE improves")
    prose = idx.match_prose("We report SWE-bench Verified, tau2-bench, AgentBench-2 and Terminal-Bench 2.0 results.")
    assert {"swe-bench-verified", "tau2-bench", "terminal-bench", "arxiv:2609.99999"} <= prose
    # radar registry aliases were merged, not duplicated
    assert idx.lookup_name("swe_bench_verified".replace("_", " ")) == "swe-bench-verified"
