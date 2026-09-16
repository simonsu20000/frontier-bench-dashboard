"""Benchmark-name dictionary and matching (table cells + prose)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CELL_CLEAN = re.compile(r"(\*\*|__|<[^>]+>|[↑↓▲▼†‡*]|\(\s*%\s*\)|\s*\([^)]{0,40}\)\s*$)")
_NONWORD = re.compile(r"[^a-z0-9]+")


def norm_cell(s: str) -> str:
    """Normalise a table cell / alias to a comparable key: lowercase, dash-joined tokens."""
    s = _CELL_CLEAN.sub(" ", str(s or ""))
    s = s.replace("’", "'").replace("τ", "tau").replace("²", "2")
    s = s.lower()
    s = _NONWORD.sub("-", s).strip("-")
    return s


_DOMAIN_MAP = [("coding", "coding"), ("code", "coding"), ("software", "coding"), ("math", "math"), ("agent", "agentic"), ("tool", "agentic"),
               ("computer", "agentic"), ("web", "agentic"), ("vision", "multimodal"), ("multimodal", "multimodal"), ("video", "multimodal"), ("image", "multimodal"),
               ("safety", "safety"), ("security", "safety"), ("cyber", "safety"), ("science", "science"), ("medical", "science"), ("legal", "science"), ("finance", "science"),
               ("reason", "reasoning"), ("knowledge", "reasoning"), ("qa", "reasoning"), ("arena", "general"), ("chat", "general"), ("general", "general"),
               ("long", "general"), ("instruction", "general"), ("language", "general")]


def norm_domain(d: str) -> str:
    """Map foreign domain labels (e.g. Benchmark Radar's 'coding_agent') onto our domain ids."""
    d = (d or "").lower()
    for needle, ours in _DOMAIN_MAP:
        if needle in d:
            return ours
    return "other" if d else ""


def _alias_regex(alias: str) -> re.Pattern:
    """Word-boundary regex tolerant to space / dash / underscore differences."""
    toks = [re.escape(t) for t in re.split(r"[\s\-_–]+", alias.strip()) if t]
    body = r"[\s\-_–]?".join(toks)
    flags = re.I if (len(toks) >= 2 or re.search(r"\d|-", alias)) else 0
    return re.compile(r"(?<![\w/])" + body + r"(?![\w])", flags)


@dataclass
class NameEntry:
    key: str
    name: str
    aliases: set[str] = field(default_factory=set)
    strict: set[str] = field(default_factory=set)       # aliases matched only as exact table cells
    bid: str | None = None                              # catalog benchmark id when scored
    domain: str = ""
    url: str = ""
    released: str = ""
    source: str = "catalog"                             # catalog | aliases | radar-yml | learned


class NameIndex:
    def __init__(self):
        self.entries: dict[str, NameEntry] = {}
        self._cell: dict[str, str] = {}                 # norm_cell(alias) -> key
        self._strict: dict[str, str] = {}               # exact-case alias -> key
        self._prose: list[tuple[re.Pattern, str]] = []

    # ---------------- build ----------------
    def add(self, key: str, name: str, aliases=(), strict=(), **meta):
        e = self.entries.get(key)
        if e is None:
            e = NameEntry(key=key, name=name, **{k: v for k, v in meta.items() if v})
            self.entries[key] = e
        else:
            for k, v in meta.items():
                if v and not getattr(e, k, None):
                    setattr(e, k, v)
        for a in list(aliases) + [name]:
            if a and a not in e.strict:
                e.aliases.add(str(a))
        for a in strict:
            e.strict.add(str(a))
            e.aliases.discard(str(a))
        return e

    def finalize(self):
        self._cell.clear(); self._strict.clear(); self._prose = []
        for e in self.entries.values():
            for a in e.aliases:
                nc = norm_cell(a)
                if nc and len(nc) >= 3:
                    self._cell.setdefault(nc, e.key)
                if len(a.strip()) >= 3:
                    self._prose.append((_alias_regex(a), e.key))
            for a in e.strict:
                self._strict[a.strip()] = e.key
        # longer aliases first so "SWE-bench Verified" wins over "SWE-bench" when both present
        self._prose.sort(key=lambda p: -len(p[0].pattern))

    @classmethod
    def build(cls, catalog: dict, aliases_cfg: dict, radar_yml: dict | None = None, learned: list[dict] = ()) -> "NameIndex":
        idx = cls()
        for b in catalog.get("benchmarks", []):
            idx.add(b["id"], b["name"], aliases=[b["name"], b.get("name_zh", "")], bid=b["id"],
                    domain=b.get("category", ""), url=b.get("official_url", ""), released=b.get("release_date", ""), source="catalog")
        for a in aliases_cfg.get("aliases", []):
            key = a["id"]
            bid = key if key in idx.entries else None
            idx.add(key, a.get("name") or key, aliases=a.get("aliases", []), strict=a.get("strict_aliases", []),
                    bid=bid, domain=a.get("domain", ""), url=a.get("url", ""), released=str(a.get("released") or ""), source="aliases")
        idx.finalize()  # so registry names below resolve through our aliases (Terminal-Bench -> terminal-bench)
        if radar_yml:
            for b in radar_yml.get("benchmarks", []) or []:
                name = b.get("name") or b.get("id")
                key = idx.lookup_name(name) or idx.lookup_name(b.get("id", "").replace("_", " ")) or f"radar:{b.get('id')}"
                idx.add(key, name, aliases=[x for x in (b.get("aliases") or []) if len(str(x)) >= 4],
                        domain=norm_domain(b.get("domain", "")), url=b.get("url", ""), released=str(b.get("released") or ""), source="radar-yml")
        for r in learned:
            nm = r.get("name") or ""
            if len(norm_cell(nm)) >= 5 or re.search(r"\d|-", nm):
                idx.add(r["key"], nm, aliases=[nm], domain=r.get("domain", ""), url=r.get("url", ""), released=r.get("date", ""), source="learned")
        idx.finalize()
        return idx

    # ---------------- lookups ----------------
    def lookup_name(self, name: str) -> str | None:
        if not name:
            return None
        nc = norm_cell(name)
        if nc in self._cell:
            return self._cell[nc]
        for e in self.entries.values():
            if norm_cell(e.name) == nc:
                return e.key
        return None

    def match_cells(self, cells) -> set[str]:
        out: set[str] = set()
        for c in cells:
            raw = str(c).strip()
            if not raw:
                continue
            if raw in self._strict:
                out.add(self._strict[raw]); continue
            nc = norm_cell(raw)
            if nc in self._cell:
                out.add(self._cell[nc]); continue
            # cells like "SWE-bench Verified (Resolved %)" or "AIME 2025 (no tools)"
            base = norm_cell(re.split(r"[(\[:]", raw)[0])
            if base in self._cell:
                out.add(self._cell[base])
        return out

    def match_prose(self, text: str) -> set[str]:
        out: set[str] = set()
        if not text:
            return out
        for rx, key in self._prose:
            if rx.search(text):
                out.add(key)
        return out

    def display(self, key: str) -> str:
        e = self.entries.get(key)
        return e.name if e else key
