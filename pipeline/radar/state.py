"""Append-only radar state under data/radar/ (committed to git, kept small)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class RadarState:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.releases: list[dict] = []
        for p in sorted(self.root.glob("releases-*.jsonl")):
            self.releases.extend(_read_jsonl(p))
        self.mentions: list[dict] = _read_jsonl(self.root / "mentions.jsonl")
        self.weekly: list[dict] = _read_jsonl(self.root / "weekly.jsonl")
        seen_path = self.root / "seen.json"
        self.seen: dict = json.loads(seen_path.read_text()) if seen_path.exists() else {}
        self.seen.setdefault("docs", {})
        self.seen.setdefault("cands", {})
        self.seen.setdefault("epoch", [])
        cache_path = self.root / "llm_cache.json"
        self.llm_cache: dict = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        self._new_releases: list[dict] = []
        self._new_mentions: list[dict] = []
        self._new_weekly: list[dict] = []
        self._release_keys = {r["key"] for r in self.releases}
        self._mention_keys = {(m["vendor"], m["doc_url"]) for m in self.mentions}

    # ---------------- appends ----------------
    def has_release(self, key: str) -> bool:
        return key in self._release_keys

    def append_release(self, rec: dict) -> bool:
        if rec["key"] in self._release_keys:
            return False
        self._release_keys.add(rec["key"])
        self.releases.append(rec)
        self._new_releases.append(rec)
        return True

    def has_mention(self, vendor: str, doc_url: str) -> bool:
        return (vendor, doc_url) in self._mention_keys

    def append_mention(self, rec: dict) -> bool:
        k = (rec["vendor"], rec["doc_url"])
        if k in self._mention_keys:
            return False
        self._mention_keys.add(k)
        self.mentions.append(rec)
        self._new_mentions.append(rec)
        return True

    def append_weekly(self, snap: dict):
        self.weekly.append(snap)
        self._new_weekly.append(snap)

    def latest_weekly(self, before: str | None = None) -> dict | None:
        cands = [w for w in self.weekly if before is None or w["week_of"] < before]
        return max(cands, key=lambda w: w["week_of"]) if cands else None

    def weekly_for(self, week_of: str) -> dict | None:
        return next((w for w in self.weekly if w["week_of"] == week_of), None)

    # ---------------- housekeeping ----------------
    def prune(self, today: date):
        cutoff_docs = (today - timedelta(days=180)).isoformat()
        self.seen["docs"] = {u: d for u, d in self.seen["docs"].items() if d >= cutoff_docs}
        self.seen["cands"] = {k: d for k, d in self.seen["cands"].items() if d >= cutoff_docs}
        cutoff_llm = (today - timedelta(days=90)).isoformat()
        self.llm_cache = {k: v for k, v in self.llm_cache.items() if (v.get("at") or "") >= cutoff_llm}

    def save(self):
        by_year: dict[str, list[dict]] = {}
        for r in self._new_releases:
            by_year.setdefault((r.get("first_seen") or "1970")[:4], []).append(r)
        for year, recs in by_year.items():
            with (self.root / f"releases-{year}.jsonl").open("a", encoding="utf-8") as fh:
                for r in recs:
                    fh.write(_dump(r) + "\n")
        if self._new_mentions:
            with (self.root / "mentions.jsonl").open("a", encoding="utf-8") as fh:
                for m in self._new_mentions:
                    fh.write(_dump(m) + "\n")
        if self._new_weekly:
            with (self.root / "weekly.jsonl").open("a", encoding="utf-8") as fh:
                for w in self._new_weekly:
                    fh.write(_dump(w) + "\n")
        (self.root / "seen.json").write_text(json.dumps(self.seen, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
        (self.root / "llm_cache.json").write_text(json.dumps(self.llm_cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
        self._new_releases, self._new_mentions, self._new_weekly = [], [], []
