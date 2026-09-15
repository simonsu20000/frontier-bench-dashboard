"""Epoch AI Benchmarking Hub bundle (https://epoch.ai/data/benchmark_data.zip)."""
from __future__ import annotations

import csv
import io
import re
import zipfile

from ..catalog import Catalog
from ..records import ScoreRecord
from ..util import is_url, to_date, to_float
from .base import Source

ZIP_URL = "https://epoch.ai/data/benchmark_data.zip"
SPINE = {"Model version", "Release date", "Organization", "Country", "Training compute (FLOP)", "Training compute notes"}
DATE_COLUMNS = ("Started at", "Date of evaluation", "Evaluation date", "Run date", "Date added",
                "Graded at", "Last updated", "Date", "Created")
LINK_COLUMNS = ("Source link", "Source Link", "Source link (site from table)")
SCAFFOLD_COLUMNS = ("Agent", "Scaffold", "Harness")
VARIANT_COLUMNS = ("Reasoning effort", "Reasoning level", "Reasoning")
NOTE_COLUMNS = ("Notes", "Notes (details)")
CI_LOW_COLUMNS = ("CI_low", "CI low", "CI Lower Bound", "95% CI Low", "Overall 95% CI low", "Pooled 95% CI low", "rating_lower")
CI_HIGH_COLUMNS = ("CI_high", "CI high", "CI Upper Bound", "95% CI High", "Overall 95% CI high", "Pooled 95% CI high", "rating_upper")
CI_HALF_COLUMNS = ("95% CI half-width", "Score 95% CI (±)", "Score 95% CI", "CRI-rescaled score 95% CI (±)")


def _read_csv(zf: zipfile.ZipFile, name: str) -> tuple[list[str], list[dict]]:
    text = zf.read(name).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [r for r in reader]
    return list(reader.fieldnames or []), rows


def _first(row: dict, names) -> str:
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _se_column(header: list[str], score_col: str) -> str | None:
    cands = [c for c in header if "standard error" in c.lower() or c.lower().endswith(" se") or c.lower() == "stderr"]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    first = score_col.split(" ")[0].lower()
    for c in cands:
        if c.lower().startswith(first):
            return c
    return None


class EpochSource(Source):
    id = "epoch"
    name = "Epoch AI Benchmarking Hub"
    url = "https://epoch.ai/benchmarks"
    license = "CC BY 4.0"
    stale_after_days = 10

    def __init__(self, catalog: Catalog, epoch_cfg: dict, epoch_overrides: dict | None = None):
        self.catalog = catalog
        self.cfg = epoch_cfg or {}
        self.overrides = epoch_overrides or {}
        self.unmapped: dict = self.cfg.get("unmapped_files") or {}
        self.run_url = self.cfg.get("epoch_run_url", "https://epoch.ai/benchmarks")

    def fetch(self, http):
        r = http.get(ZIP_URL, etag_key="epoch_zip")
        if r is None or not hasattr(r, "content"):
            return r
        return r.content

    # ------------------------------------------------------------------
    def parse(self, raw: bytes) -> tuple[list[ScoreRecord], dict]:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = set(zf.namelist())
        _, meta_rows = _read_csv(zf, "benchmark_metadata.csv")
        _, model_rows = _read_csv(zf, "model_metadata.csv")
        eci_rows: list[dict] = []
        if "epoch_capabilities_index/eci_scores.csv" in names:
            _, eci_rows = _read_csv(zf, "epoch_capabilities_index/eci_scores.csv")

        meta_by_file = {r["source_file"]: r for r in meta_rows if r.get("source_file")}
        meta_by_name = {r["benchmark"]: r for r in meta_rows}
        records: list[ScoreRecord] = []
        skipped: list[str] = []
        latest_date = ""
        bench_meta: dict[str, dict] = {}

        csv_files = sorted(n for n in names if n.endswith(".csv") and "/" not in n
                           and n not in {"benchmark_metadata.csv", "model_metadata.csv"})
        for fname in csv_files:
            meta = meta_by_file.get(fname)
            um = self.unmapped.get(fname)
            if meta is None and um is None:
                skipped.append(fname)
                continue
            epoch_name = (meta or {}).get("benchmark") or um.get("benchmark")
            score_col = (meta or {}).get("score_column") or (um or {}).get("score_column")
            if meta is None:
                meta = meta_by_name.get(epoch_name, {})
            scale_meta = to_float((meta or {}).get("scale"))
            if um and um.get("scale") is not None:
                scale_meta = float(um["scale"])
            ov = self.overrides.get(epoch_name) or {}
            bench = self.catalog.ensure_auto(
                epoch_name, fname, category=ov.get("category", "other"), unit=ov.get("unit", "pct"),
                release_date=to_date((meta or {}).get("release_date")),
                superseded_by=(meta or {}).get("superseded_by", "") or "",
                random_baseline=to_float((meta or {}).get("random_baseline")),
                score_ceiling=to_float((meta or {}).get("score_ceiling")),
            )
            if bench.epoch_score_column:
                score_col = bench.epoch_score_column
            header, rows = _read_csv(zf, fname)
            if score_col not in header:
                skipped.append(f"{fname} (score column {score_col!r} missing)")
                continue
            is_external = fname.endswith("_external.csv")
            scale = bench.epoch_scale if bench.epoch_scale is not None else scale_meta
            if scale is None:
                vals = [to_float(r.get(score_col)) for r in rows]
                vals = [v for v in vals if v is not None]
                scale = 0.01 if (bench.unit == "pct" and vals and max(vals) > 1.5) else 1.0
            mult = scale * (100.0 if bench.unit == "pct" else 1.0)
            se_col = _se_column(header, score_col)
            lo_col = next((c for c in CI_LOW_COLUMNS if c in header), None)
            hi_col = next((c for c in CI_HIGH_COLUMNS if c in header), None)
            half_col = next((c for c in CI_HALF_COLUMNS if c in header), None)
            bench_meta[bench.id] = {
                "epoch_name": epoch_name, "file": fname, "in_eci": (meta or {}).get("in_eci", ""),
                "scale": scale, "score_column": score_col, "rows": len(rows), "external": is_external,
                "category": bench.category, "unit": bench.unit, "release_date": bench.release_date,
                "superseded_by": bench.superseded_by, "random_baseline": bench.random_baseline,
                "score_ceiling": bench.score_ceiling,
            }
            for row in rows:
                mv = (row.get("Model version") or "").strip()
                if not mv:
                    continue
                raw_v = to_float(row.get(score_col))
                if raw_v is None:
                    continue
                score = raw_v * mult
                ci_lo = ci_hi = None
                if lo_col and hi_col:
                    lo, hi = to_float(row.get(lo_col)), to_float(row.get(hi_col))
                    if lo is not None and hi is not None:
                        ci_lo, ci_hi = lo * mult, hi * mult
                elif half_col:
                    h = to_float(row.get(half_col))
                    if h is not None:
                        ci_lo, ci_hi = score - h * mult, score + h * mult
                elif se_col:
                    se = to_float(row.get(se_col))
                    if se is not None:
                        ci_lo, ci_hi = score - 1.96 * se * mult, score + 1.96 * se * mult
                # some files report the SE in percent while the score is a fraction; drop absurd intervals
                if ci_lo is not None and bench.unit == "pct" and (ci_hi - ci_lo > 60 or ci_lo < -5 or ci_hi > 105):
                    ci_lo = ci_hi = None
                eval_date = ""
                for c in DATE_COLUMNS:
                    if row.get(c):
                        eval_date = to_date(row[c])
                        if eval_date:
                            break
                if eval_date and eval_date > latest_date:
                    latest_date = eval_date
                link = _first(row, LINK_COLUMNS)
                src_text = (row.get("Source") or "").strip()
                if is_url(src_text):
                    link, src_text = (link or src_text), ""
                if is_external:
                    stype, sname, surl = "", src_text, link
                else:
                    stype = "epoch_run"
                    sname = "Epoch AI independent evaluation"
                    surl = (row.get("Log viewer") or "").strip() or bench.epoch_url or self.run_url
                note = _first(row, NOTE_COLUMNS)[:240]
                extra = {}
                for k in ("Cost per task", "Cost", "Total cost (USD)", "Mean cost (USD)", "Estimated cost (USD)", "Votes"):
                    if row.get(k):
                        extra[k] = row[k]
                        break
                records.append(ScoreRecord(
                    source_id=self.id, benchmark_id=bench.id, model_raw=mv, score=score, unit=bench.unit,
                    model_name=(row.get("Name") or "").strip(), variant=_first(row, VARIANT_COLUMNS).lower(),
                    org=(row.get("Organization") or "").strip(), country=(row.get("Country") or "").strip(),
                    release_date=to_date(row.get("Release date")), ci_low=ci_lo, ci_high=ci_hi, eval_date=eval_date,
                    source_type=stype, source_name=sname, source_url=surl, source_file=fname,
                    scaffold=_first(row, SCAFFOLD_COLUMNS), note=note, extra=extra,
                ))
        model_meta = [{k: (r.get(k) or "") for k in ("model_version", "model_group", "date", "display_name",
                                                       "organization", "country", "accessibility")}
                      for r in model_rows if (r.get("model_version") or "").strip()]
        eci = [{k: (r.get(k) or "") for k in ("Model", "eci", "eci_ci_low", "eci_ci_high", "date", "Organization",
                                              "Model accessibility")} for r in eci_rows]
        # bundle timestamp: newest file mtime inside the zip
        zip_dates = [f"{i.date_time[0]:04d}-{i.date_time[1]:02d}-{i.date_time[2]:02d}" for i in zf.infolist()]
        upstream = max([latest_date] + zip_dates) if zip_dates else latest_date
        extras = {
            "model_metadata": model_meta, "eci": eci, "benchmarks": bench_meta,
            "skipped_files": skipped, "upstream_updated_at": upstream, "latest_eval_date": latest_date,
            "files": len(csv_files), "note": f"{len(csv_files)} csv files; newest eval {latest_date}",
        }
        return records, extras
