"""LiveBench: date-stamped CSV published on livebench.ai; newest file discovered via GitHub."""
from __future__ import annotations

import csv
import io
import re

from ..records import ScoreRecord
from ..util import to_float
from .base import Source

CONTENTS_API = "https://api.github.com/repos/LiveBench/livebench.github.io/contents/public"
SITE = "https://livebench.ai"
TABLE_RE = re.compile(r"^table_(\d{4})_(\d{2})_(\d{2})\.csv$")


class LiveBenchSource(Source):
    id = "livebench"
    name = "LiveBench leaderboard"
    url = "https://livebench.ai/"
    license = "LiveBench (attribution)"
    stale_after_days = 120
    benchmark_id = "livebench"

    def fetch(self, http):
        listing = http.get(CONTENTS_API, use_etag=False).json()
        tables = sorted(x["name"] for x in listing if isinstance(x, dict) and TABLE_RE.match(x.get("name", "")))
        if not tables:
            raise RuntimeError("no table_*.csv found in LiveBench repo")
        latest = tables[-1]
        m = TABLE_RE.match(latest)
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        table = http.get(f"{SITE}/{latest}", etag_key="livebench_table", use_etag=False).text
        cats_name = latest.replace("table_", "categories_").replace(".csv", ".json")
        try:
            cats = http.get(f"{SITE}/{cats_name}", use_etag=False).json()
        except Exception:  # noqa: BLE001
            cats = None
        return {"date": date, "file": latest, "table": table, "categories": cats}

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        reader = csv.DictReader(io.StringIO(raw["table"]))
        header = [h for h in (reader.fieldnames or []) if h != "model"]
        cats: dict[str, list[str]] = raw.get("categories") or {"All": header}
        out: list[ScoreRecord] = []
        for row in reader:
            name = (row.get("model") or "").strip()
            if not name:
                continue
            cat_avgs: dict[str, float] = {}
            for cat, cols in cats.items():
                vals = [to_float(row.get(c)) for c in cols if c in row]
                vals = [v for v in vals if v is not None]
                if vals:
                    cat_avgs[cat] = sum(vals) / len(vals)
            if not cat_avgs:
                continue
            global_avg = sum(cat_avgs.values()) / len(cat_avgs)
            out.append(ScoreRecord(
                source_id=self.id, benchmark_id=self.benchmark_id, model_raw=name, score=global_avg, unit="pct",
                eval_date=raw["date"], source_type="official_leaderboard",
                source_name=f"LiveBench leaderboard ({raw['date']})", source_url=self.url,
                note="global average = mean of category averages: " + ", ".join(f"{k} {v:.1f}" for k, v in cat_avgs.items()),
                extra={"categories": {k: round(v, 2) for k, v in cat_avgs.items()}, "file": raw["file"]},
            ))
        return out, {"upstream_updated_at": raw["date"], "note": f"{raw['file']}: {len(out)} models"}
