"""Small shared helpers: slugs, number/date parsing, timestamps."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """ASCII, lowercase, dash-separated identifier."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "").replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "-", "n/a"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y-%m",
)


def to_date(value) -> str:
    """Best-effort ISO date (YYYY-MM-DD) or '' when unparseable."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return ""
    if len(s) >= 10 and re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    for pat in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, pat).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return "-".join(m.groups())
    return ""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def is_url(text: str) -> bool:
    return bool(text) and text.strip().lower().startswith(("http://", "https://"))


def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/?#\s]+)", (url or "").strip(), re.I)
    if not m:
        return ""
    host = m.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    return host
