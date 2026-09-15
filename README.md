# Frontier Bench — 前沿 AI Benchmark 看板

Live: **https://simonsu20000.github.io/frontier-bench-dashboard/**

A static dashboard of frontier AI benchmarks that refreshes itself every four
hours from GitHub Actions. Every score shown comes from a **third party** —
Epoch AI's independent runs, the benchmark maintainers' official leaderboards,
or independent evaluators — and links back to where it came from. Vendor
self-reported numbers (model cards, launch blogs, technical reports) are
classified and dropped at build time.

每 4 小时自动抓取一次的前沿 AI benchmark 静态看板。所有分数只来自第三方（Epoch AI 独立复测、
benchmark 官方榜单、独立评测机构），并附来源链接；厂商自报分数在构建阶段剔除。界面中英双语。

## Panels

| Panel | What it shows |
|---|---|
| 概览 / Overview | KPIs, Epoch Capabilities Index of frontier models, current best on the 14 featured benchmarks, changelog of what moved since the last build |
| 榜单 / Leaderboards | Per-benchmark leaderboard (chart + table), best-score-over-time by release date, every record with its provenance badge |
| 模型打分 / Model scorecard | Pick up to three models: ECI, rank percentile by category (radar), every benchmark score with rank, gap to best, source and alternates |
| 分数矩阵 / Matrix | Heatmap of frontier models × featured benchmarks |
| 数据来源 / Sources | Fetch health, staleness, provenance policy, licenses |

## How it works

```
GitHub Actions (every 4 h)                       GitHub Pages
pipeline/run.py ─ fetch 6 sources ─ normalise ─▶ site/data/*.json ─▶ site/ (vanilla JS + ECharts)
                  │ resolve model ids (Epoch registry + aliases)
                  │ classify provenance, drop vendor self-reports
                  └ choose one authoritative record per (model, benchmark)
```

* **Sources** (`pipeline/sources/`): Epoch AI Benchmarking Hub (backbone: 80+ benchmarks, model
  registry, ECI), LMArena text (HF dataset), SWE-bench Verified, ARC Prize (ARC-AGI-1/2/3), LiveBench,
  Aider polyglot. Terminal-Bench, HLE, METR, OSWorld come via Epoch's curated files. Artificial Analysis
  is optional (set the `AA_API_KEY` repository secret).
* **Model identity**: canonical ids are Epoch's `model_group`; other sources are matched only by exact
  normalised name or by `config/model_aliases.yml`. Fuzzy suggestions go to `data/unmatched_report.json`
  for a human to promote — never applied automatically.
* **Provenance**: `config/sources.yml` maps domains to *official leaderboard*, *third party* or *vendor*.
  A vendor domain only counts as vendor-reported for that vendor's own models (Cursor evaluating Claude
  is a third-party evaluation). Unknown domains are excluded and reported.
* **Authoritative record**: Epoch run > official leaderboard > third-party eval; ties broken by the best
  variant. Alternates stay visible in the UI.
* **Failure isolation**: a source that fails keeps its last good parse (Actions cache) and is flagged
  in the Sources panel; the build only fails if Epoch is unreachable three runs in a row.
* **Near-real-time**: runs at 00/04/08/12/16/20:23 UTC, deploys only when data changed (the 12:23 UTC run
  always commits so the schedule never goes inactive); the page polls `status.json` every 10 minutes and
  offers a refresh when a new build landed.

## Run locally

```bash
uv sync
uv run python -m pipeline.run            # fetch everything, write site/data/
uv run python -m pipeline.run --offline  # rebuild from data/raw caches only
uv run pytest -q
python3 -m http.server -d site 8080      # open http://localhost:8080
```

`?theme=light|dark` and `?lang=zh|en` in the URL override the stored preference.

## Configuration

| File | Purpose |
|---|---|
| `config/benchmarks.yml` | Featured benchmarks (names, categories, units, descriptions zh/en), category map for the rest |
| `config/epoch_files.yml` | Epoch files lacking metadata, per-file provenance defaults |
| `config/sources.yml` | Domain → provenance class, vendor domains/owners, brand tokens |
| `config/model_aliases.yml` | Cross-source model aliases (curated) |
| `config/frontier.yml` | Frontier-model rule (18-month window, ECI top 25, SOTA holders) |

## Licenses

Code: MIT. Data: see [DATA_LICENSES.md](DATA_LICENSES.md) — Epoch AI (CC BY 4.0), LMArena (CC BY 4.0),
SWE-bench (CC BY-NC 4.0), ARC Prize, LiveBench, Aider. Non-commercial project.
