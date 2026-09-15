"""CLI entry point: python -m pipeline.run [--out site/data] [--sources a,b] [--offline]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .build import build, load_yaml
from .catalog import Catalog
from .http import Http
from .sources import run_source
from .sources.aider import AiderSource
from .sources.arcprize import ArcPrizeSource
from .sources.epoch import EpochSource
from .sources.livebench import LiveBenchSource
from .sources.lmarena import LMArenaSource
from .sources.swebench import SWEBenchSource

ROOT = Path(__file__).resolve().parent.parent
ALL_SOURCES = ("epoch", "lmarena", "swebench", "arcprize", "livebench", "aider", "artificial_analysis")


def make_sources(root: Path, wanted: list[str]):
    catalog = Catalog.load(root / "config" / "benchmarks.yml")
    epoch_cfg = load_yaml(root / "config" / "epoch_files.yml")
    overrides = load_yaml(root / "config" / "benchmarks.yml").get("epoch_overrides") or {}
    table = {
        "epoch": lambda: EpochSource(catalog, epoch_cfg, overrides),
        "lmarena": LMArenaSource,
        "swebench": SWEBenchSource,
        "arcprize": ArcPrizeSource,
        "livebench": LiveBenchSource,
        "aider": AiderSource,
    }
    if os.environ.get("AA_API_KEY"):
        from .sources.artificial_analysis import ArtificialAnalysisSource
        table["artificial_analysis"] = ArtificialAnalysisSource
    out = []
    for sid in wanted:
        if sid == "artificial_analysis" and sid not in table:
            print("artificial_analysis: skipped (AA_API_KEY not set)")
            continue
        if sid not in table:
            raise SystemExit(f"unknown source {sid}; known: {', '.join(table)}")
        out.append(table[sid]())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch benchmark sources and build site data")
    ap.add_argument("--out", default=str(ROOT / "site" / "data"))
    ap.add_argument("--cache", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--offline", action="store_true", help="build from cached parses only (no network)")
    ap.add_argument("--no-etag", action="store_true", help="ignore stored ETags and re-download everything")
    args = ap.parse_args(argv)

    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    if "epoch" not in wanted:
        wanted.insert(0, "epoch")  # the registry comes from Epoch
    cache_dir = Path(args.cache)
    http = None if args.offline else Http(cache_dir)
    if http is not None and args.no_etag:
        http.etags = {}
    results = {}
    for src in make_sources(ROOT, wanted):
        res = run_source(src, http, cache_dir, offline=args.offline)
        st = res.status
        flag = "304" if st.not_modified else st.status
        print(f"[{src.id:10s}] {flag:6s} records={st.records:5d} upstream={st.upstream_updated_at or '-':10s} "
              f"stale={st.stale} failures={st.consecutive_failures} {('ERROR ' + st.error) if st.error else ''}")
        results[src.id] = res

    epoch_status = results["epoch"].status
    all_failed = all(r.status.status == "failed" for r in results.values())
    if epoch_status.status == "failed" or all_failed:
        print(f"FATAL: Epoch backbone unavailable and no cache: {epoch_status.error}", file=sys.stderr)
        return 2

    summary = build(ROOT, Path(args.out), results, http.log if http else [])
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    if epoch_status.consecutive_failures >= 3:
        print(f"FATAL: Epoch fetch failed {epoch_status.consecutive_failures} runs in a row", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
