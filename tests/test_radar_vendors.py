from datetime import date
from pathlib import Path

from pipeline.radar.vendors import RadarModelCards, VendorSitemap, _rss_items, html_to_text, looks_like_launch, md_table_cells

FIX = Path(__file__).resolve().parent / "fixtures" / "radar"


def test_html_to_text_emits_table_rows_and_skips_chrome():
    text, title = html_to_text((FIX / "vendor_page.html").read_text())
    assert title.startswith("Introducing Claude Fable 5.1")
    assert "var x" not in text and "Home Products" not in text and "Legal" not in text
    cells = md_table_cells(text)
    assert "GPQA Diamond" in cells and "HLE" in cells and "τ²-bench" in cells
    assert "SWE-bench Verified" in text


def test_rss_items_and_launch_gate():
    xml = """<rss><channel><item><title><![CDATA[Introducing Gemini 3.8 Live]]></title><link>https://deepmind.google/blog/x/</link><pubDate>Tue, 15 Sep 2026 17:05:57 +0000</pubDate><description>d</description></item>
    <item><title>How a startup uses our API</title><link>https://example.com/y</link><pubDate>Mon, 14 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    items = _rss_items(xml)
    assert items[0]["date"] == "2026-09-15" and items[0]["title"] == "Introducing Gemini 3.8 Live"
    assert looks_like_launch(items[0]["title"], {"gemini", "google"})
    assert not looks_like_launch(items[1]["title"], {"gemini", "google"})
    assert looks_like_launch("Gemini 3.8 Flash is here", {"gemini"})


def test_radar_model_cards_parse():
    docs, extras = RadarModelCards().parse((FIX / "model_cards.yml").read_text())
    assert docs and docs[0]["source"] == "radar" and docs[0]["radar_benchmarks"]
    assert docs[0]["vendor_label"] in {"OpenAI", "Anthropic", "Google", "DeepSeek", "Meta", "Mistral", "Moonshot AI", "Qwen", "Z.ai", "xAI", "Tencent", "Ai2"}
    assert extras["benchmarks"][0]["id"] == "hle" and "HLE" in extras["benchmarks"][0]["aliases"]


class FakeHttp:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        class R:
            pass
        r = R()
        if url not in self.pages:
            raise RuntimeError("404")
        r.text = self.pages[url]
        return r


def test_sitemap_source_fetches_only_launch_pages_in_window():
    sitemap = (FIX / "anthropic_sitemap.xml").read_text()
    page = (FIX / "vendor_page.html").read_text()
    http = FakeHttp({"https://www.anthropic.com/sitemap.xml": sitemap,
                     "https://www.anthropic.com/news/claude-corps": "<html><head><title>Higher education initiatives \\ Company</title></head><body><p>A community program for universities.</p></body></html>",
                     "https://www.anthropic.com/news/introducing-claude-fable-5-1": page})
    vendor = {"id": "anthropic", "name": "Anthropic", "sitemap": "https://www.anthropic.com/sitemap.xml", "sitemap_prefix": "https://www.anthropic.com/news/"}
    seen = set()
    src = VendorSitemap(vendor, date(2026, 9, 16), 60, seen, {"anthropic", "claude"})
    docs, extras = src.parse(src.fetch(http))
    urls = [d["doc_url"] for d in docs]
    assert "https://www.anthropic.com/news/introducing-claude-fable-5-1" in urls
    assert "https://www.anthropic.com/research/something" not in urls        # outside prefix
    assert "https://www.anthropic.com/news/claude-corps" in seen              # non-launch page remembered, not a doc
    assert md_table_cells(docs[0]["text"])
