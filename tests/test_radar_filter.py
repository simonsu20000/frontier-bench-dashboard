from pathlib import Path

import yaml

from pipeline.radar.filter import candidate_key, extract_best, extract_name, merge, norm_name, score, tag_domain

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "radar.yml").read_text())


def cand(title, abstract="", **kw):
    return {"title": title, "abstract": abstract, "kind": "paper", "sources": ["arxiv-cs-cl"], **kw}


def test_scores_benchmark_paper_high_and_noise_low():
    good = cand("AgentBench-2: Evaluating LLM Agents on Long-Horizon Enterprise Tasks",
                "We introduce AgentBench-2, a benchmark of 1,200 tasks for evaluating LLM agents. The best model, GPT-5, achieves only 34.2% success rate. Code and data are publicly available.")
    s, why = score(good, CFG)
    assert s >= 7 and "introduces a benchmark" in why and "frontier models named" in why
    survey = cand("A Survey of Evaluation Benchmarks for Large Language Models", "We survey 200 benchmarks and discuss open problems.")
    assert score(survey, CFG)[0] < 4
    hardware = cand("GPU Kernel Benchmark Suite for Sparse Matrix Multiplication", "We benchmark FPGA and GPU kernel implementations of SpMM.")
    assert score(hardware, CFG)[0] < 4
    method = cand("FastAttention: A Novel Method for Efficient Transformers", "We propose a novel method that outperforms baselines on GLUE by 2 points.")
    assert score(method, CFG)[0] < 4
    replaced = dict(good, announce_type="replace")
    assert score(replaced, CFG)[0] == s - 2


def test_extract_best_reads_best_model_claims_only():
    assert extract_best("The best model, GPT-5, achieves only 34.2% success rate.")["score"] == 34.2
    assert extract_best("Even the strongest frontier models reach just 12% accuracy while humans achieve 89%.")["score"] == 12.0
    assert extract_best("Our method improves accuracy by 12.5% over the baseline.") is None
    assert extract_best("Human experts achieve 92% on this task.") is None
    assert extract_best("Claude Opus 5 solves only 23.4% of the tasks.")["score"] == 23.4


def test_names_keys_and_merge():
    assert extract_name("AgentBench-2: Evaluating LLM Agents") == "AgentBench-2"
    assert extract_name("Towards Robust Evaluation with WebArena-Pro") == "WebArena-Pro"
    assert norm_name("The Agent Company!") == "agent company"
    a = {"title": "X-Bench: y", "url": "https://arxiv.org/abs/2609.12345v2", "source": "arxiv-cs-cl", "kind": "paper", "abstract": "short", "date": "2026-09-15"}
    b = {"title": "X-Bench: y", "url": "https://huggingface.co/papers/2609.12345", "hf_url": "https://huggingface.co/papers/2609.12345", "source": "hf-papers", "kind": "paper", "abstract": "a much longer abstract text", "date": "2026-09-14", "upvotes": 12}
    c = {"title": "Other", "url": "https://example.org/z", "source": "radar", "kind": "radar"}
    merged = merge([a, b, c])
    assert len(merged) == 2
    x = next(m for m in merged if m["key"] == "arxiv:2609.12345")
    assert sorted(x["sources"]) == ["arxiv-cs-cl", "hf-papers"] and x["date"] == "2026-09-14" and x["upvotes"] == 12 and x["abstract"].startswith("a much")
    assert candidate_key({"kind": "dataset", "repo": "org/ds", "url": "https://huggingface.co/datasets/org/ds"}) == "hf-ds:org/ds"


def test_domain_tagging():
    assert tag_domain("a benchmark for repository-level code generation with GitHub issues", CFG["domains"]) == "coding"
    assert tag_domain("olympiad math proofs and theorem proving", CFG["domains"]) == "math"
    assert tag_domain("nothing specific here", CFG["domains"]) == "other"
