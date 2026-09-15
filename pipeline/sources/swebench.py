"""SWE-bench official leaderboards (swebench.com data file)."""
from __future__ import annotations

from ..records import ScoreRecord
from ..util import to_date, to_float
from .base import Source

DATA_URL = "https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json"


class SWEBenchSource(Source):
    id = "swebench"
    name = "SWE-bench leaderboard"
    url = "https://www.swebench.com/"
    license = "CC BY-NC 4.0"
    stale_after_days = 60
    benchmark_id = "swe-bench-verified"

    def fetch(self, http):
        r = http.get(DATA_URL, etag_key="swebench_leaderboards")
        return r if not hasattr(r, "json") else r.json()

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        boards = raw["leaderboards"] if isinstance(raw, dict) else raw
        verified = next((b for b in boards if b.get("name") == "Verified"), None)
        if verified is None:
            raise RuntimeError("Verified leaderboard missing from leaderboards.json")
        out: list[ScoreRecord] = []
        latest = ""
        for e in verified.get("results", []):
            model = (e.get("model_display") or "").strip()
            score = to_float(e.get("resolved"))
            if not model or score is None or e.get("warning"):
                continue
            d = to_date(e.get("date"))
            latest = max(latest, d)
            agent = (e.get("agent") or "").strip()
            scaffold = agent + (" (bash-only)" if agent == "mini-SWE-agent" else "")
            checked = e.get("checked") is True
            note = (e.get("name") or "").strip() + (" · verified by maintainers" if checked else "")
            out.append(ScoreRecord(
                source_id=self.id, benchmark_id=self.benchmark_id, model_raw=model, score=score, unit="pct",
                org=(e.get("model_org") or "").strip(), release_date=to_date(e.get("model_release_date")),
                variant=(e.get("reasoning_effort") or "").strip().lower(), eval_date=d,
                source_type="official_leaderboard", source_name="SWE-bench Verified leaderboard", source_url=self.url,
                scaffold=scaffold, note=note[:240],
                extra={"checked": checked, "os_model": bool(e.get("os_model")), "os_system": bool(e.get("os_system")),
                       "cost": e.get("cost")},
            ))
        return out, {"upstream_updated_at": latest, "note": f"Verified: {len(out)} entries"}
