"""Artificial Analysis Data API (optional; needs AA_API_KEY).

Docs: https://artificialanalysis.ai/api-reference. The free tier allows ~1,000
requests/day; we make exactly one call per run. The payload shape below follows
the documented v2 `llms/models` endpoint; anything unexpected is skipped, and a
failed parse only marks this source as failed (run_source isolates it).
"""
from __future__ import annotations

import os

from ..records import ScoreRecord
from ..util import to_date, to_float
from .base import Source

ENDPOINT = "https://artificialanalysis.ai/api/v2/data/llms/models"

# AA evaluation key -> (catalog benchmark id, treat as percent)
EVAL_MAP = {
    "artificial_analysis_intelligence_index": ("aa-intelligence-index", False),
    "gpqa": ("gpqa-diamond", True),
    "hle": ("hle", True),
    "livecodebench": ("livecodebench", True),
    "scicode": ("scicode", True),
    "mmlu_pro": ("mmlu-pro", True),
}


class ArtificialAnalysisSource(Source):
    id = "artificial_analysis"
    name = "Artificial Analysis"
    url = "https://artificialanalysis.ai/leaderboards/models"
    license = "Artificial Analysis API terms (attribution)"
    stale_after_days = 14

    def fetch(self, http):
        key = os.environ.get("AA_API_KEY", "").strip()
        if not key:
            raise RuntimeError("AA_API_KEY not set")
        r = http.get(ENDPOINT, headers={"x-api-key": key}, use_etag=False)
        return r.json()

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        data = raw.get("data") if isinstance(raw, dict) else raw
        if not isinstance(data, list):
            raise RuntimeError("unexpected payload: no data list")
        out: list[ScoreRecord] = []
        for m in data:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or m.get("slug") or "").strip()
            evals = m.get("evaluations") or {}
            if not name or not isinstance(evals, dict):
                continue
            creator = m.get("model_creator") or {}
            org = str(creator.get("name") or "") if isinstance(creator, dict) else str(creator or "")
            release = to_date(m.get("release_date"))
            for key, (bid, is_pct) in EVAL_MAP.items():
                v = to_float(evals.get(key))
                if v is None:
                    continue
                score = v * 100.0 if (is_pct and v <= 1.0) else v
                out.append(ScoreRecord(
                    source_id=self.id, benchmark_id=bid, model_raw=name, score=score, unit="pct" if is_pct else "score",
                    org=org, release_date=release, source_type="third_party", source_name="Artificial Analysis",
                    source_url=f"https://artificialanalysis.ai/models/{m.get('slug')}" if m.get("slug") else self.url,
                    note=f"AA evaluation key: {key}", extra={"slug": m.get("slug")},
                ))
        return out, {"upstream_updated_at": to_date(raw.get("generated_at")) if isinstance(raw, dict) else "",
                     "note": f"{len(data)} models, {len(out)} scores"}
