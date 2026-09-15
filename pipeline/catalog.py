"""Benchmark catalog loaded from config/benchmarks.yml.

Featured benchmarks are curated by hand; every other Epoch benchmark gets an
auto-generated entry (category "other") so nothing is silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .util import slug

UNITS = ("pct", "elo", "hours", "score")


@dataclass
class Benchmark:
    id: str
    name: str
    name_zh: str = ""
    category: str = "other"
    unit: str = "pct"
    direction: str = "higher"        # higher | lower
    featured: bool = False
    official_url: str = ""
    description_en: str = ""
    description_zh: str = ""
    epoch_file: str = ""             # csv inside the Epoch bundle, if any
    epoch_name: str = ""             # Epoch's benchmark name (benchmark_metadata.benchmark)
    epoch_score_column: str = ""     # override for the score column
    epoch_scale: float | None = None # override: multiplier that maps raw value to a 0-1 fraction
    epoch_url: str = ""              # Epoch's page for this benchmark (link target for Epoch-run rows)
    release_date: str = ""
    superseded_by: str = ""
    random_baseline: float | None = None
    score_ceiling: float | None = None
    auto: bool = False               # generated from Epoch metadata rather than curated
    sources: list[str] = field(default_factory=list)  # adapter ids contributing rows (filled at build)

    def to_public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "name_zh": self.name_zh or self.name,
            "category": self.category, "unit": self.unit, "direction": self.direction,
            "featured": self.featured, "official_url": self.official_url,
            "description_en": self.description_en, "description_zh": self.description_zh,
            "release_date": self.release_date, "superseded_by": self.superseded_by,
            "random_baseline": self.random_baseline, "sources": sorted(self.sources),
        }


class Catalog:
    def __init__(self, benchmarks: list[Benchmark], categories: dict, candidates: list[str]):
        self.benchmarks: dict[str, Benchmark] = {b.id: b for b in benchmarks}
        self.categories = categories
        self.candidates = candidates
        self._by_epoch_file = {b.epoch_file: b for b in benchmarks if b.epoch_file}
        self._by_epoch_name = {b.epoch_name: b for b in benchmarks if b.epoch_name}

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        benches = []
        for raw in cfg.get("benchmarks", []):
            epoch = raw.get("epoch") or {}
            benches.append(Benchmark(
                id=raw["id"], name=raw["name"], name_zh=raw.get("name_zh", ""),
                category=raw.get("category", "other"), unit=raw.get("unit", "pct"),
                direction=raw.get("direction", "higher"), featured=bool(raw.get("featured", False)),
                official_url=raw.get("official_url", ""),
                description_en=raw.get("description_en", ""), description_zh=raw.get("description_zh", ""),
                epoch_file=epoch.get("file", ""), epoch_name=epoch.get("name", ""),
                epoch_score_column=epoch.get("score_column", ""), epoch_scale=epoch.get("scale"),
                epoch_url=epoch.get("url", ""),
            ))
        for b in benches:
            if b.unit not in UNITS:
                raise ValueError(f"benchmark {b.id}: unknown unit {b.unit}")
        return cls(benches, cfg.get("categories", {}), cfg.get("candidates", []))

    def by_epoch_file(self, filename: str) -> Benchmark | None:
        return self._by_epoch_file.get(filename)

    def by_epoch_name(self, name: str) -> Benchmark | None:
        return self._by_epoch_name.get(name)

    def ensure_auto(self, epoch_name: str, filename: str, **meta) -> Benchmark:
        """Return the catalog entry for an Epoch benchmark, creating an auto entry if needed."""
        b = self.by_epoch_file(filename) or self.by_epoch_name(epoch_name)
        if b is None:
            bid = slug(epoch_name)
            if bid in self.benchmarks:
                b = self.benchmarks[bid]
            else:
                b = Benchmark(id=bid, name=epoch_name, name_zh=epoch_name, category=meta.pop("category", "other"),
                              unit=meta.pop("unit", "pct"), auto=True)
                self.benchmarks[bid] = b
        b.epoch_file = b.epoch_file or filename
        b.epoch_name = b.epoch_name or epoch_name
        self._by_epoch_file[filename] = b
        self._by_epoch_name[epoch_name] = b
        for k, v in meta.items():
            if v not in (None, "") and not getattr(b, k, None):
                setattr(b, k, v)
        return b

    def featured(self) -> list[Benchmark]:
        return [b for b in self.benchmarks.values() if b.featured]

    def get(self, bid: str) -> Benchmark | None:
        return self.benchmarks.get(bid)
