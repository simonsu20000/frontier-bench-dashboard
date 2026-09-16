"""Optional Claude second pass over borderline candidates (needs ANTHROPIC_API_KEY)."""
from __future__ import annotations

import json
import os

PROMPT_VERSION = "1"
DOMAINS = ["coding", "math", "agentic", "multimodal", "safety", "science", "reasoning", "general", "other"]

SYSTEM = """You classify newly published items (arXiv papers, Hugging Face datasets/spaces) for a dashboard of AI benchmarks.
A "benchmark" here means a dataset, task suite, leaderboard or evaluation protocol whose PURPOSE is to measure the capability of
LLMs, multimodal models or AI agents. Not benchmarks: surveys, position papers, new methods/models that merely report results on
existing benchmarks, hardware/systems benchmarks, datasets built only for training.
For each item return: whether it is such a benchmark, a confidence in [0,1], a short canonical name (as the authors call it),
a domain from {coding, math, agentic, multimodal, safety, science, reasoning, general, other}, whether a public leaderboard or
official eval harness exists, the best score reported for the strongest evaluated model as a percentage (only if the text states
it explicitly; otherwise null - never guess), a one-sentence English summary (<=120 chars) and a one-sentence Simplified Chinese
summary (<=60 characters). Keep benchmark and model names in English inside the Chinese summary."""


def enabled(cli_flag: bool) -> bool:
    return cli_flag and bool(os.environ.get("ANTHROPIC_API_KEY"))


def judge(cands: list[dict], cache: dict, cfg: dict, today: str, log=print) -> dict[str, dict]:
    """Return {key: verdict}. Uses the cache first; makes at most cfg['llm']['max_requests'] API calls."""
    out: dict[str, dict] = {}
    todo = []
    for c in cands:
        hit = cache.get(c["key"])
        if hit and hit.get("v") == PROMPT_VERSION:
            out[c["key"]] = hit["out"]
        else:
            todo.append(c)
    if not todo:
        return out
    try:
        import anthropic
        from pydantic import BaseModel
    except ImportError as e:  # SDK not installed: silently fall back to heuristics
        log(f"[llm] anthropic SDK unavailable ({e}); heuristics only")
        return out

    class Item(BaseModel):
        key: str
        is_llm_benchmark: bool
        confidence: float
        canonical_name: str
        domain: str
        has_leaderboard: bool
        reported_best_score: float | None
        summary_en: str
        summary_zh: str

    class Batch(BaseModel):
        items: list[Item]

    model = os.environ.get("RADAR_LLM_MODEL") or cfg["llm"].get("model", "claude-haiku-4-5")
    batch_size = int(cfg["llm"].get("batch", 8))
    max_requests = int(cfg["llm"].get("max_requests", 20))
    client = anthropic.Anthropic()
    requests_made = 0
    for i in range(0, len(todo), batch_size):
        if requests_made >= max_requests:
            log(f"[llm] request cap {max_requests} reached; {len(todo) - i} candidates left to heuristics")
            break
        batch = todo[i:i + batch_size]
        payload = [{"key": c["key"], "title": c.get("title", ""), "sources": c.get("sources", []), "kind": c.get("kind", ""),
                    "abstract": (c.get("abstract") or "")[:1500], "tags": (c.get("tags") or [])[:10]} for c in batch]
        try:
            resp = client.messages.parse(
                model=model, max_tokens=int(cfg["llm"].get("max_tokens", 4096)), system=SYSTEM,
                messages=[{"role": "user", "content": "Classify these items. Return one entry per key, same keys:\n" + json.dumps(payload, ensure_ascii=False)}],
                output_format=Batch,
            )
            requests_made += 1
            items = resp.parsed_output.items if resp.parsed_output else []
        except Exception as e:  # noqa: BLE001 - never let the LLM pass break the build
            log(f"[llm] request failed ({type(e).__name__}: {str(e)[:120]}); stopping LLM pass")
            break
        wanted = {c["key"] for c in batch}
        for it in items:
            if it.key not in wanted:
                continue
            d = it.model_dump()
            if d["domain"] not in DOMAINS:
                d["domain"] = "other"
            d["confidence"] = max(0.0, min(1.0, float(d.get("confidence") or 0)))
            if d.get("reported_best_score") is not None and not (0 < float(d["reported_best_score"]) < 100):
                d["reported_best_score"] = None
            out[it.key] = d
            cache[it.key] = {"v": PROMPT_VERSION, "at": today, "out": d}
    log(f"[llm] model={model} requests={requests_made} judged={len(out)}")
    return out
