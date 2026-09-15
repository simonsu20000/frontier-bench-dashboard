# Data licenses and attribution

The code in this repository is MIT-licensed (see `LICENSE`). The benchmark data
under `site/data/` and `data/` is **redistributed from upstream sources under
their own terms**, listed below. This is a personal, non-commercial project:
no advertising, no paid access.

| Source | What we use | License / terms | Attribution |
|---|---|---|---|
| [Epoch AI Benchmarking Hub](https://epoch.ai/benchmarks) | `benchmark_data.zip`: Epoch's own evaluation runs, curated external results, model metadata, Epoch Capabilities Index | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Epoch AI, "Capabilities & Benchmarking". Published online at epoch.ai. Retrieved from https://epoch.ai/benchmarks. Data is filtered (vendor self-reports removed) and reprocessed. External rows keep their original upstream license; each row links to its source. |
| [LMArena](https://lmarena.ai) | `lmarena-ai/leaderboard-dataset` on Hugging Face (text, style control) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | LMArena text leaderboard |
| [SWE-bench](https://www.swebench.com/) | `data/leaderboards.json` (Verified) | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — non-commercial use only | SWE-bench leaderboard |
| [ARC Prize](https://arcprize.org/leaderboard) | leaderboard JSON (ARC-AGI-1/2/3) | ARC Prize Foundation; used with attribution and links back to each result | ARC Prize Foundation |
| [LiveBench](https://livebench.ai) | latest `table_*.csv` + category map | LiveBench (Apache-2.0 code; data used with attribution) | LiveBench |
| [Aider](https://aider.chat/docs/leaderboards/) | `polyglot_leaderboard.yml` | Apache-2.0 (aider repository) | Aider polyglot leaderboard |
| [Artificial Analysis](https://artificialanalysis.ai) (optional) | Data API, only when `AA_API_KEY` is configured | Artificial Analysis API terms | Artificial Analysis |

Terminal-Bench, Humanity's Last Exam, METR time horizons, OSWorld and the other
"external" benchmarks are taken from Epoch's curated files; each row links to the
maintainer's page (tbench.ai, scale.com, metr.org, os-world.github.io, ...).

Charts are rendered with [Apache ECharts](https://echarts.apache.org/) (Apache-2.0,
vendored in `site/vendor/`).

If you maintain one of these sources and want something changed or removed,
open an issue in this repository.
