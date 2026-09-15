"""The normalized score record shared by every source."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

SOURCE_TYPES = ("epoch_run", "official_leaderboard", "third_party", "vendor_reported", "unclassified")
# Lower rank wins when choosing the authoritative record for a (model, benchmark).
SOURCE_TYPE_RANK = {"epoch_run": 0, "official_leaderboard": 1, "third_party": 2, "vendor_reported": 3, "unclassified": 4}


@dataclass
class ScoreRecord:
    source_id: str                 # adapter id: epoch, lmarena, swebench, ...
    benchmark_id: str              # catalog id
    model_raw: str                 # model name exactly as the source spells it
    score: float                   # in `unit` (pct is 0-100)
    unit: str = "pct"              # pct | elo | hours | score
    model_name: str = ""           # display name from the source, if any
    model_id: str | None = None    # canonical id, filled by build.resolve
    matched_by: str = ""           # epoch | exact | alias | '' (unmatched)
    variant: str = ""              # reasoning effort / thinking variant
    org: str = ""
    country: str = ""
    release_date: str = ""
    accessibility: str = ""
    ci_low: float | None = None
    ci_high: float | None = None
    eval_date: str = ""
    source_type: str = ""          # one of SOURCE_TYPES, filled by provenance.classify when empty
    source_name: str = ""
    source_url: str = ""
    source_file: str = ""          # epoch: originating csv (for per-file provenance defaults)
    scaffold: str = ""             # agent / harness on agentic benchmarks
    note: str = ""
    authoritative: bool = False    # filled by build.choose_authoritative
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreRecord":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})
