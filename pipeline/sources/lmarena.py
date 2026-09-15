"""LMArena text leaderboard from the public HF dataset lmarena-ai/leaderboard-dataset."""
from __future__ import annotations

import io

from ..records import ScoreRecord
from ..util import to_date, to_float
from .base import Source

BASE = "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main"
CONFIGS = ("text_style_control", "text")


class LMArenaSource(Source):
    id = "lmarena"
    name = "LMArena Text Arena"
    url = "https://lmarena.ai/leaderboard/text"
    license = "CC BY 4.0"
    stale_after_days = 7
    benchmark_id = "lmarena-text"

    def fetch(self, http):
        last_err = None
        for cfg in CONFIGS:
            url = f"{BASE}/{cfg}/latest-00000-of-00001.parquet"
            try:
                r = http.get(url, etag_key=f"lmarena_{cfg}")
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
            if not hasattr(r, "content"):
                return r  # NotModified
            return {"config": cfg, "bytes": r.content}
        raise RuntimeError(f"no LMArena parquet reachable: {last_err}")

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        import pyarrow.parquet as pq

        table = pq.read_table(io.BytesIO(raw["bytes"]))
        rows = table.to_pylist()
        cats = {str(r.get("category")) for r in rows}
        target = "overall" if "overall" in cats else sorted(cats)[0]
        style = "style control" if raw["config"].endswith("style_control") else "no style control"
        out: list[ScoreRecord] = []
        latest = ""
        for r in rows:
            if str(r.get("category")) != target:
                continue
            rating = to_float(r.get("rating"))
            name = (r.get("model_name") or "").strip()
            if rating is None or not name:
                continue
            pub = to_date(r.get("leaderboard_publish_date"))
            latest = max(latest, pub)
            lic = (r.get("license") or "").strip()
            votes = to_float(r.get("vote_count"))
            rank = to_float(r.get("rank"))
            out.append(ScoreRecord(
                source_id=self.id, benchmark_id=self.benchmark_id, model_raw=name, score=rating, unit="elo",
                org=(r.get("organization") or "").strip(), ci_low=to_float(r.get("rating_lower")),
                ci_high=to_float(r.get("rating_upper")), eval_date=pub, source_type="official_leaderboard",
                source_name=f"LMArena text leaderboard ({style})", source_url=self.url,
                accessibility="API access" if lic.lower() == "proprietary" else ("Open weights" if lic else ""),
                note=f"{int(votes):,} votes" + (f", rank {int(rank)}" if rank else ""),
                extra={"license": lic, "category": target, "config": raw["config"]},
            ))
        return out, {"upstream_updated_at": latest, "note": f"{raw['config']}/{target}: {len(out)} models"}
