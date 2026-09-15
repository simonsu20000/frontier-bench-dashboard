"""ARC Prize leaderboards (arcprize.org JSON used by their own leaderboard page)."""
from __future__ import annotations

from ..records import ScoreRecord
from ..util import to_date, to_float
from .base import Source

VERSIONS = {"v1": "arc-agi-1", "v2": "arc-agi-2", "v3": "arc-agi-3"}
BASE = "https://arcprize.org/media/data"


class ArcPrizeSource(Source):
    id = "arcprize"
    name = "ARC Prize leaderboard"
    url = "https://arcprize.org/leaderboard"
    license = "ARC Prize Foundation (attribution)"
    stale_after_days = 60

    def fetch(self, http):
        payload = {"boards": {}, "models": None, "errors": {}}
        for v in VERSIONS:
            try:
                r = http.get(f"{BASE}/leaderboard/{v}.json", etag_key=f"arc_{v}", use_etag=False)
                payload["boards"][v] = r.json()
            except Exception as e:  # noqa: BLE001 - one version missing must not kill the others
                payload["errors"][v] = f"{type(e).__name__}: {e}"
        if not payload["boards"]:
            raise RuntimeError(f"no ARC leaderboard reachable: {payload['errors']}")
        try:
            payload["models"] = http.get(f"{BASE}/models.json", use_etag=False).json()
        except Exception as e:  # noqa: BLE001
            payload["errors"]["models"] = f"{type(e).__name__}: {e}"
        return payload

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        models = {m.get("id"): m for m in (raw.get("models") or []) if isinstance(m, dict)}
        out: list[ScoreRecord] = []
        latest = ""
        counts = {}
        for v, board in raw["boards"].items():
            bid = VERSIONS[v]
            gen = to_date(board.get("generatedAt"))
            latest = max(latest, gen)
            n = 0
            for e in board.get("evaluations", []):
                if e.get("display") is False:
                    continue
                if (e.get("providerId") or "").lower() == "human":
                    continue
                score = to_float(e.get("score"))
                name = (e.get("modelDisplayName") or "").strip()
                if score is None or not name:
                    continue
                meta = models.get(e.get("modelId"), {})
                cost = to_float(e.get("costPerTask"))
                mtype = (e.get("modelType") or meta.get("modelType") or "")
                note_parts = [f"{e.get('datasetDisplayName') or bid}"]
                if mtype:
                    note_parts.append(str(mtype))
                if cost is not None:
                    note_parts.append(f"${cost:g}/task")
                out.append(ScoreRecord(
                    source_id=self.id, benchmark_id=bid, model_raw=name, score=score * 100.0, unit="pct",
                    org=(e.get("providerDisplayName") or e.get("providerId") or "").strip(),
                    release_date=to_date(e.get("modelReleaseDate") or meta.get("modelReleaseDate")),
                    eval_date=gen, source_type="official_leaderboard",
                    source_name=f"ARC Prize leaderboard ({e.get('datasetDisplayName') or bid})",
                    source_url=(e.get("resultsUrl") or "").strip() or self.url,
                    note=" · ".join(note_parts)[:240],
                    extra={"model_id": e.get("modelId"), "model_group": e.get("modelGroup"), "dataset": e.get("datasetId")},
                ))
                n += 1
            counts[bid] = n
        note = ", ".join(f"{k}: {v}" for k, v in counts.items())
        if raw.get("errors"):
            note += f"; errors: {raw['errors']}"
        return out, {"upstream_updated_at": latest, "note": note[:300]}
