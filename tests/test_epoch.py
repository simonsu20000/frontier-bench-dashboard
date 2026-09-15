import csv
import io
import zipfile
from pathlib import Path

import yaml

from pipeline.catalog import Catalog
from pipeline.sources.epoch import EpochSource

ROOT = Path(__file__).resolve().parent.parent


def _csv(header, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def make_bundle():
    spine = ["Model version", "Release date", "Organization", "Country", "Training compute (FLOP)", "Training compute notes"]
    run_hdr = ["Model version", "mean_score", "Best score (across scorers)", "Release date", "Organization", "Country",
               "Training compute (FLOP)", "Training compute notes", "stderr", "Log viewer", "Logs", "Started at", "id"]
    files = {
        "benchmark_metadata.csv": _csv(
            ["benchmark", "in_eci", "source_file", "score_column", "scale", "random_baseline", "score_ceiling", "release_date", "superseded_by"],
            [{"benchmark": "GPQA diamond", "in_eci": "True", "source_file": "gpqa_diamond.csv", "score_column": "Best score (across scorers)", "scale": "1.0", "random_baseline": "0.25", "score_ceiling": "1.0", "release_date": "2023-11-20", "superseded_by": ""},
             {"benchmark": "Terminal Bench", "in_eci": "True", "source_file": "terminalbench_external.csv", "score_column": "Accuracy mean", "scale": "1.0", "random_baseline": "0", "score_ceiling": "1.0", "release_date": "2025-05-19", "superseded_by": ""},
             {"benchmark": "Old FrontierMath", "in_eci": "True", "source_file": "frontiermath.csv", "score_column": "Best score (across scorers)", "scale": "1.0", "random_baseline": "0", "score_ceiling": "0.57", "release_date": "2025-02-28", "superseded_by": "FrontierMath v2"},
             {"benchmark": "LiveBench", "in_eci": "False", "source_file": "", "score_column": "", "scale": "1.0", "random_baseline": "0", "score_ceiling": "1.0", "release_date": "2024-06-27", "superseded_by": ""}]),
        "model_metadata.csv": _csv(
            ["model_version", "model_group", "date", "display_name", "organization", "country", "accessibility", "training_compute_flop"],
            [{"model_version": "gpt-5.2-2025-12-11_high", "model_group": "GPT-5.2", "date": "2025-12-11", "display_name": "GPT-5.2 (high)", "organization": "OpenAI", "country": "United States of America", "accessibility": "API access", "training_compute_flop": ""},
             {"model_version": "", "model_group": "", "date": "", "display_name": "", "organization": "", "country": "", "accessibility": "", "training_compute_flop": ""}]),
        "gpqa_diamond.csv": _csv(run_hdr, [
            {"Model version": "gpt-5.2-2025-12-11_high", "mean_score": "0.90", "Best score (across scorers)": "0.912", "Release date": "2025-12-11", "Organization": "OpenAI",
             "Country": "United States of America", "Training compute (FLOP)": "", "Training compute notes": "", "stderr": "0.02", "Log viewer": "", "Logs": "", "Started at": "2025-12-12T10:00:00.000Z", "id": "a"}]),
        "frontiermath.csv": _csv(run_hdr, [
            {"Model version": "gpt-5.2-2025-12-11_high", "mean_score": "0.30", "Best score (across scorers)": "0.30", "Release date": "2025-12-11", "Organization": "OpenAI",
             "Country": "United States of America", "Training compute (FLOP)": "", "Training compute notes": "", "stderr": "0.02", "Log viewer": "", "Logs": "", "Started at": "2025-12-12T10:00:00.000Z", "id": "b"}]),
        "terminalbench_external.csv": _csv(spine + ["Agent", "Accuracy mean", "Accuracy SE", "Run date", "Notes", "Source", "Source Link", "Name", "id"], [
            {"Model version": "gpt-5.2-2025-12-11_high", "Release date": "2025-12-11", "Organization": "OpenAI", "Country": "United States of America", "Training compute (FLOP)": "", "Training compute notes": "",
             "Agent": "Terminus 2", "Accuracy mean": "0.62", "Accuracy SE": "0.02", "Run date": "2026-01-05", "Notes": "", "Source": "https://www.tbench.ai/leaderboard/terminal-bench/2.0", "Source Link": "", "Name": "GPT-5.2", "id": "c"},
            {"Model version": "", "Release date": "", "Organization": "", "Country": "", "Training compute (FLOP)": "", "Training compute notes": "",
             "Agent": "x", "Accuracy mean": "0.5", "Accuracy SE": "", "Run date": "", "Notes": "", "Source": "", "Source Link": "", "Name": "", "id": "d"}]),
        "live_bench_external.csv": _csv(spine + ["Global average", "Source", "Source link", "Notes", "id"], [
            {"Model version": "gpt-5.2-2025-12-11_high", "Release date": "2025-12-11", "Organization": "OpenAI", "Country": "United States of America", "Training compute (FLOP)": "", "Training compute notes": "",
             "Global average": "78.5", "Source": "LiveBench Leaderboard", "Source link": "https://livebench.ai/#/", "Notes": "", "id": "e"}]),
        "epoch_capabilities_index/eci_scores.csv": _csv(
            ["Model", "Display name", "eci", "eci_ci_low", "eci_ci_high", "date", "Organization", "Country (of organization)", "Model accessibility", "Accessibility group", "model_versions"],
            [{"Model": "GPT-5.2", "Display name": "GPT-5.2", "eci": "155", "eci_ci_low": "153", "eci_ci_high": "158", "date": "2025-12-11", "Organization": "OpenAI", "Country (of organization)": "United States of America", "Model accessibility": "API access", "Accessibility group": "Closed weights", "model_versions": ""}]),
        "README.md": "license",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_epoch_parse_end_to_end():
    catalog = Catalog.load(ROOT / "config" / "benchmarks.yml")
    cfg = yaml.safe_load((ROOT / "config" / "epoch_files.yml").read_text())
    overrides = yaml.safe_load((ROOT / "config" / "benchmarks.yml").read_text()).get("epoch_overrides") or {}
    src = EpochSource(catalog, cfg, overrides)
    records, extras = src.parse(make_bundle())
    by = {(r.benchmark_id, r.source_type or "external"): r for r in records}

    gpqa = by[("gpqa-diamond", "epoch_run")]
    assert abs(gpqa.score - 91.2) < 1e-9          # fraction -> percent
    assert abs(gpqa.ci_low - (91.2 - 1.96 * 2)) < 1e-6 and abs(gpqa.ci_high - (91.2 + 1.96 * 2)) < 1e-6
    assert gpqa.eval_date == "2025-12-12"
    assert gpqa.source_url.startswith("https://epoch.ai/benchmarks/gpqa-diamond")

    tb = by[("terminal-bench", "external")]
    assert tb.source_url == "https://www.tbench.ai/leaderboard/terminal-bench/2.0" and tb.source_name == ""
    assert tb.scaffold == "Terminus 2" and tb.eval_date == "2026-01-05" and tb.model_name == "GPT-5.2"
    assert abs(tb.score - 62.0) < 1e-9
    assert not any(r.model_raw == "" for r in records)   # rows without a model are skipped

    lb = by[("livebench", "external")]
    assert abs(lb.score - 78.5) < 1e-9                    # percent-stored file scaled by 0.01 then x100
    assert lb.source_name == "LiveBench Leaderboard"

    old = [r for r in records if r.benchmark_id == "old-frontiermath"]
    assert old and catalog.get("old-frontiermath").superseded_by == "FrontierMath v2"
    assert extras["benchmarks"]["old-frontiermath"]["superseded_by"] == "FrontierMath v2"

    assert extras["model_metadata"][0]["model_group"] == "GPT-5.2" and len(extras["model_metadata"]) == 1
    assert extras["eci"][0]["Model"] == "GPT-5.2"
    assert extras["upstream_updated_at"] >= "2026-01-05"
