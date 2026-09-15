"""Model registry and cross-source name resolution.

Canonical model ids are slugs of Epoch's `model_group` (which already merges
reasoning-effort variants). Other sources are matched only by exact normalized
keys or explicit aliases; fuzzy candidates are reported, never applied.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .util import slug, to_date

EFFORT_TOKENS = {"none", "minimal", "low", "medium", "high", "xhigh", "unknown", "effort"}
# "max" is an effort level for some vendors but part of the name for others (Qwen3.8 Max);
# it only counts as a variant in an Epoch "_max" suffix, inside parentheses, or as a
# last-resort retry in ModelRegistry.resolve.
SOFT_EFFORT_TOKENS = {"max"}
THINK_TOKENS = {"thinking", "nonthinking", "non-thinking", "no-thinking", "nothinking", "think"}
BUDGET_RE = re.compile(r"^\d{1,3}k$")
DROP_TOKENS = {"latest", "exp", "experimental", "chat", "instruct", "it", "hf", "fp8"}
_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _is_variant_token(t: str, soft: bool) -> bool:
    return t in EFFORT_TOKENS or bool(BUDGET_RE.match(t)) or (soft and t in SOFT_EFFORT_TOKENS)


def _is_date_token(t: str) -> bool:
    if not t.isdigit():
        return False
    if len(t) == 8:
        return True
    if len(t) == 4:
        year = 1990 <= int(t) <= 2039
        mmdd = 1 <= int(t[:2]) <= 12 and 1 <= int(t[2:]) <= 31
        return year or mmdd
    return len(t) == 2


def normalize_name(name: str, soft_max: bool = False) -> tuple[str, str, str]:
    """Return (full_key, stripped_key, variant).

    full_key keeps date tokens, stripped_key drops trailing date tokens. Effort
    levels, thinking budgets and parenthesised qualifiers become the variant.
    With soft_max=True a bare "max" token is also treated as an effort level.
    """
    s = str(name or "").strip().lower()
    variant: list[str] = []
    # Epoch-style "_suffix" (gpt-5.2-2025-12-11_none, claude-fable-5-1_xhigh, qwen3.8-max_unknown)
    if "_" in s:
        head, _, tail = s.rpartition("_")
        if _is_variant_token(tail, True) or tail in THINK_TOKENS:
            variant.append(tail)
            s = head
    parens = _PAREN_RE.findall(s)
    s = _PAREN_RE.sub(" ", s)
    s = s.split("/")[-1]
    s = s.replace("_", "-")
    s = re.sub(r"[\s\.\+:,@]+", "-", s)
    tokens = [t for t in s.split("-") if t]
    kept: list[str] = []
    for t in tokens:
        if _is_variant_token(t, soft_max):
            variant.append(t)
        elif t in DROP_TOKENS:
            continue
        else:
            kept.append(t)
    for p in parens:
        ptoks = [t for t in re.split(r"[\s\-_,]+", p.lower()) if t]
        for t in ptoks:
            if _is_variant_token(t, True) or t in THINK_TOKENS:
                variant.append(t)
    full = "-".join(kept)
    stripped_tokens = list(kept)
    while stripped_tokens and _is_date_token(stripped_tokens[-1]):
        stripped_tokens.pop()
    stripped = "-".join(stripped_tokens) or full
    var = "-".join(t for t in variant if t not in {"none", "unknown", "effort"})
    return full, stripped, var


def _strip_dates(key: str) -> str:
    toks = [t for t in key.split("-") if t]
    while toks and _is_date_token(toks[-1]):
        toks.pop()
    return "-".join(toks) or key


def _nothink(key: str) -> str:
    """Drop thinking tokens, then trailing dates (handles '...-20250805-thinking')."""
    toks = [t for t in key.split("-") if t not in THINK_TOKENS]
    return _strip_dates("-".join(toks))


def _token_key(key: str) -> str:
    return "|".join(sorted(t for t in key.split("-") if t))


def _days_between(a: str, b: str) -> int | None:
    try:
        from datetime import date
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


@dataclass
class Model:
    id: str
    name: str
    org: str = ""
    country: str = ""
    release_date: str = ""
    accessibility: str = ""
    versions: list[str] = field(default_factory=list)
    eci: float | None = None
    eci_lo: float | None = None
    eci_hi: float | None = None
    eci_date: str = ""

    def to_public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "org": self.org, "country": self.country,
            "release_date": self.release_date, "accessibility": self.accessibility,
            "eci": self.eci, "eci_lo": self.eci_lo, "eci_hi": self.eci_hi,
        }


@dataclass
class Resolved:
    model_id: str | None
    variant: str
    matched_by: str
    suggestions: list[tuple[str, float]] = field(default_factory=list)


class ModelRegistry:
    def __init__(self, aliases: dict[str, str] | None = None):
        self.models: dict[str, Model] = {}
        self.aliases = {k.strip(): v for k, v in (aliases or {}).items()}
        self._idx: dict[str, dict[str, set[str]]] = {
            "full": defaultdict(set), "stripped": defaultdict(set),
            "nothink": defaultdict(set), "tokens": defaultdict(set),
        }
        self.unmatched: dict[tuple[str, str], dict] = {}
        self.ambiguous: dict[tuple[str, str], list[str]] = {}

    # ---------------- construction ----------------
    @classmethod
    def from_epoch(cls, metadata_rows: list[dict], eci_rows: list[dict], aliases: dict[str, str] | None = None):
        reg = cls(aliases)
        for row in metadata_rows:
            mv = (row.get("model_version") or "").strip()
            if not mv:
                continue
            group = (row.get("model_group") or "").strip()
            display = (row.get("display_name") or "").strip()
            if not group:
                base, _, _ = normalize_name(display or mv)
                group = display.split("(")[0].strip() if display else base
            mid = slug(group)
            if not mid:
                continue
            m = reg.models.get(mid)
            if m is None:
                m = Model(id=mid, name=group)
                reg.models[mid] = m
            m.versions.append(mv)
            org = (row.get("organization") or "").strip()
            if org and not m.org:
                m.org = org.split(",")[0].strip()
            country = (row.get("country") or "").strip()
            if country and not m.country:
                m.country = country.split(",")[0].strip()
            acc = (row.get("accessibility") or "").strip()
            if acc and not m.accessibility:
                m.accessibility = acc
            d = to_date(row.get("date"))
            if d and (not m.release_date or d < m.release_date):
                m.release_date = d
            reg._index(mv, mid)
            if display:
                reg._index(display, mid)
            reg._index(group, mid)
        for row in eci_rows:
            mid = slug((row.get("Model") or "").strip())
            m = reg.models.get(mid)
            if m is None:
                continue
            try:
                m.eci = float(row.get("eci"))
                m.eci_lo = float(row.get("eci_ci_low")) if row.get("eci_ci_low") else None
                m.eci_hi = float(row.get("eci_ci_high")) if row.get("eci_ci_high") else None
            except (TypeError, ValueError):
                continue
            m.eci_date = to_date(row.get("date"))
            if not m.org and row.get("Organization"):
                m.org = str(row["Organization"]).split(",")[0].strip()
            if not m.accessibility and row.get("Model accessibility"):
                m.accessibility = row["Model accessibility"]
        return reg

    def _index(self, name: str, mid: str):
        full, stripped, _ = normalize_name(name)
        if not full:
            return
        self._idx["full"][full].add(mid)
        self._idx["stripped"][stripped].add(mid)
        self._idx["nothink"][_nothink(full)].add(mid)
        self._idx["tokens"][_token_key(_nothink(full))].add(mid)

    # ---------------- resolution ----------------
    def resolve(self, name: str, source: str, org_hint: str = "", date_hint: str = "") -> Resolved:
        raw = (name or "").strip()
        full, stripped, variant = normalize_name(raw)
        alias = self.aliases.get(f"{source}:{raw}") or self.aliases.get(raw)
        if alias:
            if alias in self.models:
                return Resolved(alias, variant, "alias")
        if not full:
            return Resolved(None, variant, "")
        attempts = [(full, stripped, variant)]
        if full.split("-")[-1] in SOFT_EFFORT_TOKENS:
            attempts.append(normalize_name(raw, soft_max=True))
        matched_by = "epoch" if source == "epoch" else "exact"
        for full_k, stripped_k, var in attempts:
            for level, key in (("full", full_k), ("stripped", stripped_k), ("nothink", _nothink(full_k)),
                               ("tokens", _token_key(_nothink(full_k)))):
                ids = self._idx[level].get(key)
                if not ids:
                    continue
                if len(ids) == 1:
                    return Resolved(next(iter(ids)), var, matched_by)
                # ambiguous at this level: try the org hint, then the release-date hint
                if org_hint:
                    narrowed = [i for i in ids if self.models[i].org.lower() == org_hint.lower()]
                    if len(narrowed) == 1:
                        return Resolved(narrowed[0], var, matched_by)
                if date_hint:
                    dated = []
                    for i in ids:
                        d = _days_between(date_hint, self.models[i].release_date)
                        if d is not None and d <= 45:
                            dated.append((d, i))
                    dated.sort()
                    if len(dated) == 1 or (len(dated) > 1 and dated[0][0] < dated[1][0]):
                        return Resolved(dated[0][1], var, "date")
                self.ambiguous[(source, raw)] = sorted(ids)
                return Resolved(None, var, "")
        return Resolved(None, variant, "")

    def suggest(self, name: str, limit: int = 3) -> list[tuple[str, float]]:
        _, stripped, _ = normalize_name(name)
        toks = set(stripped.split("-"))
        if not toks:
            return []
        best: dict[str, float] = {}
        for key, ids in self._idx["stripped"].items():
            ktoks = set(key.split("-"))
            inter = len(toks & ktoks)
            if not inter:
                continue
            score = inter / len(toks | ktoks)
            if score < 0.5:
                continue
            for mid in ids:
                if score > best.get(mid, 0):
                    best[mid] = score
        return sorted(best.items(), key=lambda kv: -kv[1])[:limit]

    def note_unmatched(self, name: str, source: str, score: float, benchmark_id: str):
        key = (source, name)
        entry = self.unmatched.get(key)
        if entry is None:
            entry = {"source": source, "name": name, "count": 0, "best_score": score,
                     "benchmarks": [], "suggestions": []}
            self.unmatched[key] = entry
            entry["suggestions"] = [{"model_id": mid, "similarity": round(s, 3)} for mid, s in self.suggest(name)]
        entry["count"] += 1
        entry["best_score"] = max(entry["best_score"], score)
        if benchmark_id not in entry["benchmarks"]:
            entry["benchmarks"].append(benchmark_id)

    def get(self, mid: str) -> Model | None:
        return self.models.get(mid)
