"""Classify where a score came from, so vendor self-reports can be excluded."""
from __future__ import annotations

import re
from collections import Counter

from .records import ScoreRecord
from .util import domain_of, is_url

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\.\-]*")


class Provenance:
    def __init__(self, sources_cfg: dict, epoch_cfg: dict):
        self.benchmark_hosts: dict[str, str] = {k.lower(): v for k, v in (sources_cfg.get("benchmark_hosts") or {}).items()}
        self.third_party_hosts: dict[str, str] = {k.lower(): v for k, v in (sources_cfg.get("third_party_hosts") or {}).items()}
        # domain / github owner -> organisation key in org_brands (the publisher)
        self.vendor_hosts: dict[str, str] = {str(k).lower(): str(v) for k, v in (sources_cfg.get("vendor_hosts") or {}).items()}
        self.vendor_github_owners: dict[str, str] = {str(k).lower(): str(v) for k, v in (sources_cfg.get("vendor_github_owners") or {}).items()}
        self.org_brands = {k.lower(): [str(t).lower() for t in v] for k, v in (sources_cfg.get("org_brands") or {}).items()}
        self.vendor_title_patterns = [p.lower() for p in sources_cfg.get("vendor_title_patterns") or []]
        self.include_vendor = bool(sources_cfg.get("include_vendor_reported", False))
        self.include_unclassified = bool(sources_cfg.get("include_unclassified", False))
        self.file_sources: dict[str, dict] = epoch_cfg.get("file_sources") or {}
        self.default_file_source: dict = epoch_cfg.get("default_file_source") or {
            "type": "third_party", "name": "Epoch AI Benchmarking Hub", "url": "https://epoch.ai/benchmarks"}
        self.unknown_domains: Counter = Counter()
        self.unknown_examples: dict[str, dict] = {}
        self.counts: Counter = Counter()

    # ---------------- helpers ----------------
    @staticmethod
    def _host_match(host: str, table) -> str | None:
        """Exact or parent-domain match; returns the matched key."""
        keys = table.keys() if isinstance(table, dict) else table
        for k in keys:
            if host == k or host.endswith("." + k):
                return k
        return None

    def _brand_tokens(self, org: str) -> set[str]:
        toks: set[str] = set()
        for part in (org or "").split(","):
            part = part.strip().lower()
            if not part:
                continue
            toks.update(self.org_brands.get(part, []))
            # the organisation's own name words are brands too (skip generic words)
            for w in re.findall(r"[a-z0-9\.]+", part):
                if len(w) > 2 and w not in {"ai", "inc", "labs", "lab", "research", "the", "corp", "institute", "technology", "innovation", "systems"}:
                    toks.add(w)
        return toks

    def same_org(self, publisher_org: str, model_org: str) -> bool:
        """True when the publisher (domain owner) is the organisation that built the model."""
        if not publisher_org or not model_org:
            return False
        return bool(self._brand_tokens(publisher_org) & self._brand_tokens(model_org))

    def title_mentions_vendor(self, title: str, org: str) -> bool:
        t = (title or "").lower()
        if not t:
            return False
        if any(p in t for p in self.vendor_title_patterns):
            return True
        words = set(_WORD_RE.findall(t))
        brands = self._brand_tokens(org)
        if words & brands:
            return True
        # brand tokens such as "gpt" also match "gpt-4" style words
        return any(any(w.startswith(b + "-") or w.startswith(b + ".") for w in words) for b in brands if len(b) > 2)

    # ---------------- main entry ----------------
    def classify(self, rec: ScoreRecord) -> str:
        """Fill rec.source_type (and default name/url) and return the type."""
        if rec.source_type:
            self.counts[rec.source_type] += 1
            return rec.source_type
        url = (rec.source_url or "").strip()
        title = (rec.source_name or "").strip()
        if not url and is_url(title):
            url, title = title, ""
            rec.source_url, rec.source_name = url, title
        stype = ""
        if url:
            host = domain_of(url)
            k = self._host_match(host, self.benchmark_hosts)
            vk = self._host_match(host, self.vendor_hosts)
            if k:
                stype = "official_leaderboard"
                rec.source_name = title or self.benchmark_hosts[k]
            elif host in ("github.com", "huggingface.co"):
                # repo/model-card owner decides: a lab's own repo is vendor-reported
                path = url.split(host + "/", 1)[-1]
                parts = [p for p in path.split("/") if p]
                if host == "huggingface.co" and parts and parts[0] in ("datasets", "spaces", "collections", "papers"):
                    parts = parts[1:]
                owner = (parts[0] if parts else "").lower()
                publisher = self.vendor_github_owners.get(owner, "")
                owner_tokens = {w for w in re.findall(r"[a-z0-9]+", owner) if len(w) > 2}
                own_repo = bool(owner_tokens & self._brand_tokens(rec.org))
                if own_repo or (publisher and self.same_org(publisher, rec.org)) or self.title_mentions_vendor(title, rec.org):
                    stype = "vendor_reported"
                else:
                    stype = "third_party"
                    rec.source_name = title or f"{'GitHub' if host == 'github.com' else 'Hugging Face'}: {owner}"
            elif vk:
                publisher = self.vendor_hosts[vk]
                # a lab publishing scores for ITS OWN models is vendor-reported;
                # a lab evaluating other labs' models is a third-party evaluation
                if self.same_org(publisher, rec.org) or self.title_mentions_vendor(title, rec.org):
                    stype = "vendor_reported"
                else:
                    stype = "third_party"
                    rec.source_name = title or f"{publisher} evaluation"
            else:
                k = self._host_match(host, self.third_party_hosts)
                if k:
                    stype = "vendor_reported" if self.title_mentions_vendor(title, rec.org) else "third_party"
                    if stype == "third_party":
                        rec.source_name = title or self.third_party_hosts[k]
                else:
                    stype = "unclassified"
                    self.unknown_domains[host] += 1
                    self.unknown_examples.setdefault(host, {"url": url, "title": title, "source_file": rec.source_file})
        else:
            default = self.file_sources.get(rec.source_file) or self.default_file_source
            if self.title_mentions_vendor(title, rec.org):
                stype = "vendor_reported"
            else:
                stype = default.get("type", "third_party")
                rec.source_name = title or default.get("name", "")
                rec.source_url = default.get("url", "")
        rec.source_type = stype
        self.counts[stype] += 1
        return stype

    def keep(self, rec: ScoreRecord) -> bool:
        if rec.source_type == "vendor_reported":
            return self.include_vendor
        if rec.source_type == "unclassified":
            return self.include_unclassified
        return True

    def report(self) -> list[dict]:
        return [{"domain": d, "count": c, **self.unknown_examples.get(d, {})}
                for d, c in self.unknown_domains.most_common()]
