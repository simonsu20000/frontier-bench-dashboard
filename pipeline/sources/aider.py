"""Aider polyglot leaderboard (YAML in the aider repo)."""
from __future__ import annotations

import yaml

from ..records import ScoreRecord
from ..util import to_date, to_float
from .base import Source

YAML_URL = "https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml"


class AiderSource(Source):
    id = "aider"
    name = "Aider polyglot leaderboard"
    url = "https://aider.chat/docs/leaderboards/"
    license = "Apache-2.0 (aider repo)"
    stale_after_days = 120
    benchmark_id = "aider-polyglot"

    def fetch(self, http):
        r = http.get(YAML_URL, etag_key="aider_polyglot")
        return r if not hasattr(r, "text") else r.text

    def parse(self, raw: str) -> tuple[list[ScoreRecord], dict]:
        entries = yaml.safe_load(raw) or []
        out: list[ScoreRecord] = []
        latest = ""
        for e in entries:
            name = str(e.get("model") or "").strip()
            score = to_float(e.get("pass_rate_2"))
            if not name or score is None:
                continue
            d = to_date(e.get("date"))
            latest = max(latest, d)
            cost = to_float(e.get("total_cost"))
            note = f"edit format {e.get('edit_format', '?')}; well-formed {e.get('percent_cases_well_formed', '?')}%"
            if cost is not None:
                note += f"; ${cost:.2f} total"
            out.append(ScoreRecord(
                source_id=self.id, benchmark_id=self.benchmark_id, model_raw=name, score=score, unit="pct",
                variant=str(e.get("reasoning_effort") or "").lower(), eval_date=d,
                source_type="official_leaderboard", source_name="Aider polyglot leaderboard", source_url=self.url,
                scaffold=f"aider {e.get('versions', '')}".strip(), note=note[:240],
                extra={"pass_rate_1": e.get("pass_rate_1"), "command": e.get("command")},
            ))
        return out, {"upstream_updated_at": latest, "note": f"{len(out)} entries"}
