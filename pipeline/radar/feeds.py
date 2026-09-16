"""Sources of new-benchmark candidates. Each returns plain candidate dicts."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

from ..sources.base import Source
from ..util import to_date
from .filter import arxiv_id

NS = {"dc": "http://purl.org/dc/elements/1.1/", "arxiv": "http://arxiv.org/schemas/atom"}
ARXIV_DESC = re.compile(r"arXiv:(\d{4}\.\d{4,5})(?:v\d+)?\s+Announce Type:\s*([\w-]+)\s*Abstract:\s*(.*)", re.S)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


class ArxivRss(Source):
    license = "arXiv RSS (metadata, attribution)"
    stale_after_days = 5

    def __init__(self, category: str, today: date):
        self.category = category
        self.id = f"arxiv-{category.replace('.', '-').lower()}"
        self.name = f"arXiv RSS {category}"
        self.url = f"https://rss.arxiv.org/rss/{category}"
        self.today = today

    def fetch(self, http):
        return http.get(self.url, use_etag=False).text

    def parse(self, raw: str):
        root = ET.fromstring(raw.encode("utf-8") if isinstance(raw, str) else raw)
        out = []
        chan_date = to_date(_clean(root.findtext("./channel/lastBuildDate") or root.findtext("./channel/pubDate")))
        for item in root.iter("item"):
            title = _clean(item.findtext("title"))
            link = _clean(item.findtext("link"))
            desc = item.findtext("description") or ""
            m = ARXIV_DESC.search(desc)
            aid = m.group(1) if m else arxiv_id(link)
            announce = (m.group(2).lower() if m else (_clean(item.findtext("arxiv:announce_type", namespaces=NS)) or "new")).lower()
            abstract = _clean(m.group(3) if m else desc)
            authors = [_clean(a.text) for a in item.findall("dc:creator", NS)] or [_clean(item.findtext("dc:creator", namespaces=NS))]
            d = to_date(_clean(item.findtext("pubDate"))) or chan_date or self.today.isoformat()
            out.append({"title": title, "url": link or (f"https://arxiv.org/abs/{aid}" if aid else ""), "date": d,
                        "source": self.id, "kind": "paper", "abstract": abstract[:2500], "authors": [a for a in authors if a][:8],
                        "arxiv_id": aid, "announce_type": announce})
        return out, {"upstream_updated_at": chan_date or self.today.isoformat(), "note": f"{len(out)} items"}


class HfDailyPapers(Source):
    id = "hf-papers"
    name = "Hugging Face daily papers"
    url = "https://huggingface.co/papers"
    license = "Hugging Face (metadata)"
    stale_after_days = 5

    def __init__(self, today: date, days: int = 3):
        self.today, self.days = today, days

    def fetch(self, http):
        payload = {}
        for i in range(self.days):
            d = (self.today - timedelta(days=i)).isoformat()
            try:
                payload[d] = http.get_json(f"https://huggingface.co/api/daily_papers?date={d}&limit=50", use_etag=False)
            except Exception as e:  # noqa: BLE001 - one missing day is fine
                payload[d] = {"error": str(e)}
        if all(isinstance(v, dict) and "error" in v for v in payload.values()):
            raise RuntimeError(f"all daily_papers requests failed: {payload}")
        return payload

    def parse(self, raw: dict):
        out, latest = [], ""
        for d, items in raw.items():
            if not isinstance(items, list):
                continue
            for it in items:
                p = it.get("paper") or {}
                pid = str(p.get("id") or "")
                if not pid:
                    continue
                org = p.get("organization") or it.get("organization") or {}
                pub = to_date(p.get("publishedAt") or it.get("publishedAt")) or d
                latest = max(latest, pub)
                out.append({"title": _clean(p.get("title") or it.get("title")), "url": f"https://arxiv.org/abs/{pid}",
                            "hf_url": f"https://huggingface.co/papers/{pid}", "date": pub, "source": self.id, "kind": "paper",
                            "abstract": _clean(p.get("summary") or it.get("summary"))[:2500], "upvotes": int(p.get("upvotes") or 0),
                            "code_url": p.get("githubRepo") or "", "org": (org.get("fullname") or org.get("name") or "") if isinstance(org, dict) else str(org or ""),
                            "arxiv_id": pid, "tags": [str(k) for k in (p.get("ai_keywords") or [])][:12],
                            "authors": [a.get("name") for a in (p.get("authors") or []) if isinstance(a, dict) and a.get("name")][:8]})
        return out, {"upstream_updated_at": latest, "note": f"{len(out)} papers over {len(raw)} days"}


class HfDatasets(Source):
    id = "hf-datasets"
    name = "Hugging Face new datasets"
    url = "https://huggingface.co/datasets?search=benchmark&sort=created"
    license = "Hugging Face (metadata)"
    stale_after_days = 5

    def __init__(self, today: date, days: int = 3):
        self.today, self.days = today, days

    def fetch(self, http):
        return http.get_json("https://huggingface.co/api/datasets?sort=createdAt&direction=-1&limit=50&search=benchmark&full=true", use_etag=False)

    def parse(self, raw: list):
        cutoff = (self.today - timedelta(days=self.days)).isoformat()
        out = []
        for it in raw or []:
            created = to_date(it.get("createdAt"))
            if not created or created < cutoff:
                continue
            card = it.get("cardData") or {}
            tags = [str(t) for t in (it.get("tags") or []) if not str(t).startswith(("size_categories", "format:", "modality:", "library:", "region:"))]
            tags += [str(t) for t in (card.get("tags") or [])]
            desc = _clean(it.get("description") or card.get("pretty_name") or "")
            out.append({"title": it["id"], "name": it["id"].split("/")[-1], "url": f"https://huggingface.co/datasets/{it['id']}", "repo": it["id"],
                        "date": created, "source": self.id, "kind": "dataset", "abstract": desc[:1500], "tags": tags[:20],
                        "org": it.get("author") or "", "upvotes": int(it.get("likes") or 0)})
        return out, {"upstream_updated_at": max((c["date"] for c in out), default=""), "note": f"{len(out)} datasets in window"}


class HfSpaces(Source):
    id = "hf-spaces"
    name = "Hugging Face new leaderboard spaces"
    url = "https://huggingface.co/spaces?search=leaderboard&sort=created"
    license = "Hugging Face (metadata)"
    stale_after_days = 5

    def __init__(self, today: date, days: int = 3):
        self.today, self.days = today, days

    def fetch(self, http):
        return http.get_json("https://huggingface.co/api/spaces?search=leaderboard&sort=createdAt&direction=-1&limit=30", use_etag=False)

    def parse(self, raw: list):
        cutoff = (self.today - timedelta(days=self.days)).isoformat()
        out = []
        for it in raw or []:
            created = to_date(it.get("createdAt"))
            if not created or created < cutoff:
                continue
            tags = [str(t) for t in (it.get("tags") or [])]
            out.append({"title": it["id"], "name": it["id"].split("/")[-1], "url": f"https://huggingface.co/spaces/{it['id']}", "repo": it["id"],
                        "date": created, "source": self.id, "kind": "space", "abstract": "", "tags": tags,
                        "org": it["id"].split("/")[0], "upvotes": int(it.get("likes") or 0)})
        return out, {"upstream_updated_at": max((c["date"] for c in out), default=""), "note": f"{len(out)} spaces in window"}


RADAR_SOURCES_OK = {"arXiv", "Hugging Face Papers", "Hugging Face", "GitHub", "GitHub Release", "First-party feed"}


class RadarSnapshot(Source):
    id = "radar"
    name = "Benchmark Radar daily snapshot"
    url = "https://benchmark-radar.org/"
    license = "Benchmark Radar (mixed upstream terms; metadata only)"
    stale_after_days = 5

    def __init__(self, today: date, days: int = 3):
        self.today, self.days = today, days

    def fetch(self, http):
        payload, ok = {}, 0
        for i in range(self.days):
            d = (self.today - timedelta(days=i)).isoformat()
            try:
                payload[d] = http.get_json(f"https://raw.githubusercontent.com/ktwu01/benchmark-radar/main/data/snapshots/{d}.json", use_etag=False)
                ok += 1
            except Exception as e:  # noqa: BLE001
                payload[d] = {"error": str(e)[:200]}
        if not ok:
            raise RuntimeError("no Benchmark Radar snapshot reachable")
        return payload

    def parse(self, raw: dict):
        out, latest = [], ""
        for d, snap in raw.items():
            if not isinstance(snap, dict) or "evidence_items" not in snap:
                continue
            for e in snap.get("evidence_items") or []:
                cats = set(e.get("categories") or [])
                if not (cats & {"benchmark", "evaluation"}) or e.get("source") not in RADAR_SOURCES_OK:
                    continue
                if e.get("event_kind") not in ("released", "discovered"):
                    continue
                url = e.get("url") or ""
                arts = [a for a in (e.get("artifact_urls") or []) if isinstance(a, str)]
                aid = arxiv_id(url, *arts)
                code = next((a for a in arts if "github.com" in a), "")
                pub = to_date(e.get("published_at")) or d
                latest = max(latest, pub)
                out.append({"title": _clean(e.get("title")), "url": (f"https://arxiv.org/abs/{aid}" if aid else url), "date": pub,
                            "source": self.id, "kind": "paper" if aid else "radar", "abstract": _clean(e.get("summary"))[:2500],
                            "authors": [str(a) for a in (e.get("authors") or [])][:8], "org": ", ".join(str(o) for o in (e.get("organizations") or [])[:2]),
                            "arxiv_id": aid, "code_url": code, "tags": sorted(cats),
                            "extra": {"radar_score": e.get("total_score"), "recommended": e.get("recommended"), "radar_source": e.get("source")}})
        return out, {"upstream_updated_at": latest, "note": f"{len(out)} benchmark/eval items over {sum(1 for v in raw.values() if isinstance(v, dict) and 'evidence_items' in v)} snapshots"}


def epoch_new_benchmarks(root: Path, seen_epoch: list[str], today: date) -> tuple[list[dict], list[str]]:
    """Benchmarks newly tracked by Epoch since the last run. Bootstraps silently on first run."""
    cat_path = root / "site" / "data" / "catalog.json"
    if not cat_path.exists():
        return [], seen_epoch
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    ids = sorted(b["id"] for b in cat.get("benchmarks", []))
    if not seen_epoch:
        return [], ids
    known = set(seen_epoch)
    out = []
    for b in cat.get("benchmarks", []):
        if b["id"] in known:
            continue
        out.append({"title": b["name"], "name": b["name"], "url": b.get("official_url") or "https://epoch.ai/benchmarks", "slug": b["id"],
                    "date": b.get("release_date") or today.isoformat(), "source": "epoch", "kind": "epoch",
                    "abstract": b.get("description_en") or "", "org": "Epoch AI", "tags": [b.get("category", "")],
                    "extra": {"category": b.get("category")}})
    return out, sorted(known | set(ids))
