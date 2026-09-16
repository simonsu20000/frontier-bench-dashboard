"""Vendor attention: fetch launch posts / model cards, extract benchmark mentions."""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html.parser import HTMLParser

from ..sources.base import Source
from ..util import to_date

LAUNCH_RE = re.compile(r"\b(introduc\w*|announc\w*|launch\w*|releas\w*|model card|system card|technical report|tech report|now available|"
                       r"new model|preview|GA\b|general availability|benchmark|evaluation)", re.I)
MAX_DOCS_PER_RUN = 20       # pages fetched per source per run; the rest wait for the next run
MAX_CONSECUTIVE_ERRORS = 3  # stop fetching pages from a source that keeps failing (e.g. 403 walls)
BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "pre", "blockquote", "tr"}
SKIP_TAGS = {"script", "style", "nav", "footer", "noscript", "svg", "head", "iframe"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in BLOCK_TAGS:
            self.out.append("\n")
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag == "tr":
            self.out.append(" |\n")
        elif tag in BLOCK_TAGS:
            self.out.append("\n")
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if not self.skip and data.strip():
            self.out.append(data)


def html_to_text(html: str, cap: int = 400_000) -> tuple[str, str]:
    p = _Text()
    p.feed(html[:cap])
    text = "".join(p.out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip(), p.title


_SEP_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def md_table_cells(text: str) -> list[str]:
    """All non-numeric cells of markdown-style tables (and html_to_text's '| cell |' rows)."""
    cells: list[str] = []
    for line in (text or "").splitlines():
        if "|" not in line or _SEP_ROW.match(line):
            continue
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        for c in parts:
            c = re.sub(r"\*\*|__|<[^>]+>", "", c).strip()
            if not c or re.fullmatch(r"[\d\.\-\+%,\s/±~xX*]+", c):
                continue
            cells.append(c)
    return cells


def looks_like_launch(title: str, brand_tokens: set[str]) -> bool:
    t = (title or "").lower()
    if LAUNCH_RE.search(t):
        return True
    return any(re.search(r"\b" + re.escape(b) + r"[\w\.\-]*", t) for b in brand_tokens if len(b) > 2)


def _doc(vendor: str, url: str, title: str, d: str, source: str, text: str, **extra) -> dict:
    return {"vendor": vendor, "doc_url": url, "doc_title": title[:200], "doc_date": d, "source": source, "text": text, **extra}


class HfModelCards(Source):
    license = "Hugging Face model cards (per-repo license)"
    stale_after_days = 90

    def __init__(self, vendor: dict, today: date, lookback_days: int, seen: set[str]):
        self.vendor = vendor
        self.id = f"hf-{vendor['id']}"
        self.name = f"HF model cards · {vendor['name']}"
        self.url = f"https://huggingface.co/{(vendor.get('hf_authors') or [''])[0]}"
        self.today, self.lookback, self.seen = today, lookback_days, seen

    def fetch(self, http):
        cutoff = (self.today - timedelta(days=self.lookback)).isoformat()
        hdr = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}
        docs, listed = [], 0
        for author in self.vendor.get("hf_authors") or []:
            models = http.get_json(f"https://huggingface.co/api/models?author={author}&sort=createdAt&direction=-1&limit=12", headers=hdr, use_etag=False)
            for m in models or []:
                listed += 1
                created = to_date(m.get("createdAt"))
                mid = m.get("id") or m.get("modelId")
                if not mid or not created or created < cutoff:
                    continue
                url = f"https://huggingface.co/{mid}"
                if url in self.seen or len(docs) >= MAX_DOCS_PER_RUN:
                    continue
                time.sleep(0.3)
                try:
                    readme = http.get_text(f"https://huggingface.co/{mid}/raw/main/README.md", headers=hdr, use_etag=False)
                except Exception as e:  # noqa: BLE001 - gated / missing card
                    readme = ""
                    err = str(e)[:80]
                else:
                    err = ""
                readme = re.sub(r"^---\n.*?\n---\n", "", readme, count=1, flags=re.S)  # drop YAML front matter
                docs.append(_doc(self.vendor["id"], url, mid, created, "hf", readme[:200_000], tags=[t for t in (m.get("tags") or []) if str(t).startswith(("eval", "arxiv"))], error=err))
        return {"docs": docs, "listed": listed}

    def parse(self, raw):
        return raw["docs"], {"upstream_updated_at": max((d["doc_date"] for d in raw["docs"]), default=""), "note": f"{len(raw['docs'])} new cards of {raw['listed']} listed"}


def _rss_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = []
    for it in root.iter("item"):
        items.append({"title": re.sub(r"\s+", " ", it.findtext("title") or "").strip(), "link": (it.findtext("link") or "").strip(),
                      "date": to_date(it.findtext("pubDate") or ""), "summary": (it.findtext("description") or "")[:1000]})
    if not items:  # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in root.findall("a:entry", ns):
            link = next((l.get("href") for l in e.findall("a:link", ns) if l.get("rel") in (None, "alternate")), "")
            items.append({"title": (e.findtext("a:title", namespaces=ns) or "").strip(), "link": link,
                          "date": to_date(e.findtext("a:published", namespaces=ns) or e.findtext("a:updated", namespaces=ns) or ""), "summary": ""})
    return items


class VendorRss(Source):
    license = "vendor blog (fair use: titles + benchmark mentions)"
    stale_after_days = 120

    def __init__(self, vendor: dict, today: date, lookback_days: int, seen: set[str], brand_tokens: set[str]):
        self.vendor = vendor
        self.id = f"rss-{vendor['id']}"
        self.name = f"Announcements · {vendor['name']}"
        self.url = (vendor.get("rss") or [""])[0]
        self.today, self.lookback, self.seen, self.brands = today, lookback_days, seen, brand_tokens

    def fetch(self, http):
        cutoff = (self.today - timedelta(days=self.lookback)).isoformat()
        docs, n_items, errors = [], 0, 0
        for feed in self.vendor.get("rss") or []:
            items = _rss_items(http.get(feed, use_etag=False).text)
            n_items += len(items)
            for it in items:
                if not it["link"] or (it["date"] and it["date"] < cutoff) or it["link"] in self.seen:
                    continue
                if not looks_like_launch(it["title"], self.brands):
                    continue
                if len(docs) >= MAX_DOCS_PER_RUN:
                    break
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    # site blocks scripted fetches (e.g. openai.com 403): keep title+summary only, no more page fetches
                    docs.append(_doc(self.vendor["id"], it["link"], it["title"], it["date"] or self.today.isoformat(), "rss", it.get("summary", ""), error="blocked"))
                    continue
                time.sleep(0.3)
                try:
                    html = http.get(it["link"], use_etag=False).text
                    text, _ = html_to_text(html)
                    err = ""
                    errors = 0
                except Exception as e:  # noqa: BLE001 - 403/timeouts: keep the title-only doc
                    text, err = it.get("summary", ""), str(e)[:80]
                    errors += 1
                docs.append(_doc(self.vendor["id"], it["link"], it["title"], it["date"] or self.today.isoformat(), "rss", text[:200_000], error=err))
        return {"docs": docs, "items": n_items}

    def parse(self, raw):
        return raw["docs"], {"upstream_updated_at": max((d["doc_date"] for d in raw["docs"]), default=""), "note": f"{len(raw['docs'])} launch posts of {raw['items']} feed items"}


class VendorSitemap(Source):
    license = "vendor site (fair use: titles + benchmark mentions)"
    stale_after_days = 120

    def __init__(self, vendor: dict, today: date, lookback_days: int, seen: set[str], brand_tokens: set[str]):
        self.vendor = vendor
        self.id = f"sitemap-{vendor['id']}"
        self.name = f"Newsroom · {vendor['name']}"
        self.url = vendor.get("sitemap", "")
        self.today, self.lookback, self.seen, self.brands = today, lookback_days, seen, brand_tokens

    def fetch(self, http):
        cutoff = (self.today - timedelta(days=self.lookback)).isoformat()
        xml_text = http.get(self.vendor["sitemap"], use_etag=False).text
        prefix = self.vendor.get("sitemap_prefix", "")
        urls = re.findall(r"<url>\s*<loc>(.*?)</loc>\s*(?:<lastmod>(.*?)</lastmod>)?", xml_text, re.S)
        docs, n, errors = [], 0, 0
        for loc, lastmod in sorted(urls, key=lambda t: t[1] or "", reverse=True):
            if prefix and not loc.startswith(prefix):
                continue
            n += 1
            d = to_date(lastmod)
            if (d and d < cutoff) or loc in self.seen:
                continue
            if len(docs) >= MAX_DOCS_PER_RUN or errors >= MAX_CONSECUTIVE_ERRORS:
                break
            time.sleep(0.3)
            try:
                text, title = html_to_text(http.get(loc, use_etag=False).text)
                err = ""
                errors = 0
            except Exception as e:  # noqa: BLE001
                text, title, err = "", loc.rsplit("/", 1)[-1].replace("-", " "), str(e)[:80]
                errors += 1
            title = title.split("\\")[0].split(" | ")[0].strip() or loc
            if not looks_like_launch(title, self.brands) and not looks_like_launch(text[:400], self.brands):
                self.seen.add(loc)  # remember non-launch pages so we don't refetch
                continue
            docs.append(_doc(self.vendor["id"], loc, title, d or self.today.isoformat(), "sitemap", text[:200_000], error=err))
        return {"docs": docs, "items": n}

    def parse(self, raw):
        return raw["docs"], {"upstream_updated_at": max((d["doc_date"] for d in raw["docs"]), default=""), "note": f"{len(raw['docs'])} launch pages of {raw['items']} news urls"}


class GithubOrgRepos(Source):
    license = "GitHub READMEs (per-repo license)"
    stale_after_days = 120

    def __init__(self, vendor: dict, today: date, lookback_days: int, seen: set[str]):
        self.vendor = vendor
        self.id = f"github-{vendor['id']}"
        self.name = f"GitHub releases · {vendor['name']}"
        self.url = f"https://github.com/{(vendor.get('github_orgs') or [''])[0]}"
        self.today, self.lookback, self.seen = today, lookback_days, seen

    def fetch(self, http):
        cutoff = (self.today - timedelta(days=self.lookback)).isoformat()
        hdr = {"Accept": "application/vnd.github+json"}
        if os.environ.get("GITHUB_TOKEN"):
            hdr["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        docs, n = [], 0
        for org in self.vendor.get("github_orgs") or []:
            repos = http.get_json(f"https://api.github.com/orgs/{org}/repos?sort=created&direction=desc&per_page=15", headers=hdr, use_etag=False)
            for r in repos or []:
                n += 1
                created = to_date(r.get("created_at"))
                url = r.get("html_url") or ""
                if not created or created < cutoff or url in self.seen or r.get("fork") or len(docs) >= MAX_DOCS_PER_RUN:
                    continue
                time.sleep(0.3)
                try:
                    readme = http.get_text(f"https://raw.githubusercontent.com/{r['full_name']}/HEAD/README.md", use_etag=False)
                    err = ""
                except Exception as e:  # noqa: BLE001
                    readme, err = r.get("description") or "", str(e)[:80]
                docs.append(_doc(self.vendor["id"], url, r["full_name"], created, "github", readme[:200_000], error=err))
        return {"docs": docs, "items": n}

    def parse(self, raw):
        return raw["docs"], {"upstream_updated_at": max((d["doc_date"] for d in raw["docs"]), default=""), "note": f"{len(raw['docs'])} new repos of {raw['items']} listed"}


class RadarModelCards(Source):
    id = "radar-cards"
    name = "Benchmark Radar model-card registry"
    url = "https://github.com/ktwu01/benchmark-radar/blob/main/data/model_cards.yml"
    license = "Benchmark Radar (curated registry, attribution)"
    stale_after_days = 45

    def fetch(self, http):
        return http.get("https://raw.githubusercontent.com/ktwu01/benchmark-radar/main/data/model_cards.yml", use_etag=False).text

    def parse(self, raw: str):
        import yaml
        data = yaml.safe_load(raw) or {}
        cards = data.get("model_cards") or []
        docs = []
        for c in cards:
            pub = to_date(c.get("published"))
            docs.append({"vendor_label": str(c.get("organization") or ""), "doc_url": c.get("url") or "", "doc_title": f"{c.get('organization', '')} {c.get('model', '')} ({str(c.get('document_type', '')).replace('_', ' ')})".strip(),
                         "doc_date": pub or to_date(c.get("retrieved_at")) or "", "source": "radar", "text": "",
                         "radar_benchmarks": [str(b) for b in (c.get("benchmarks") or [])]})
        bench = [{"id": b.get("id"), "name": b.get("name"), "aliases": b.get("aliases") or [], "domain": b.get("domain", ""), "url": b.get("url", ""),
                  "released": str(b.get("released") or "")} for b in (data.get("benchmarks") or [])]
        return docs, {"upstream_updated_at": max((d["doc_date"] for d in docs), default=""), "note": f"{len(docs)} cards, {len(bench)} registry benchmarks", "benchmarks": bench}
