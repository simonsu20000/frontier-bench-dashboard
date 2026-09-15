"""HTTP fetching with retries, Content-Length verification and ETag caching."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "frontier-bench-dashboard/0.1 (+https://github.com/simonsu20000/frontier-bench-dashboard)"


class NotModified:
    """Sentinel returned when the upstream answered 304 for a cached ETag."""

    def __repr__(self):  # pragma: no cover
        return "NotModified"


NOT_MODIFIED = NotModified()


class Http:
    def __init__(self, cache_dir: Path, timeout: int = 120, attempts: int = 3, trust_env: bool | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.etag_path = self.cache_dir / "etags.json"
        self.etags: dict[str, dict] = {}
        if self.etag_path.exists():
            try:
                self.etags = json.loads(self.etag_path.read_text())
            except json.JSONDecodeError:
                self.etags = {}
        self.timeout = timeout
        self.attempts = attempts
        self.session = requests.Session()
        # macOS system proxies are picked up by requests but not by curl; they have
        # broken CDN fetches locally, so ignore them unless explicitly asked for.
        self.session.trust_env = (os.environ.get("FBD_TRUST_ENV") == "1") if trust_env is None else trust_env
        retry = Retry(total=3, connect=3, read=2, backoff_factor=1.5,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = USER_AGENT
        self.log: list[str] = []

    def _save_etags(self):
        self.etag_path.write_text(json.dumps(self.etags, indent=1, sort_keys=True) + "\n")

    def get(self, url: str, *, etag_key: str | None = None, headers: dict | None = None,
            use_etag: bool = True) -> requests.Response | NotModified:
        """GET with conditional request support. Returns NOT_MODIFIED on 304."""
        hdrs = dict(headers or {})
        cached = self.etags.get(etag_key) if etag_key else None
        if cached and use_etag and cached.get("etag"):
            hdrs["If-None-Match"] = cached["etag"]
        last_err: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                r = self.session.get(url, headers=hdrs, timeout=self.timeout, allow_redirects=True)
                if r.status_code == 304:
                    self.log.append(f"304 {url}")
                    return NOT_MODIFIED
                r.raise_for_status()
                clen = r.headers.get("Content-Length")
                if clen and not r.headers.get("Content-Encoding") and int(clen) != len(r.content):
                    raise IOError(f"short read: got {len(r.content)} of {clen} bytes")
                self.log.append(f"{r.status_code} {url} ({len(r.content)} bytes)")
                if etag_key and (r.headers.get("ETag") or r.headers.get("Last-Modified")):
                    self.etags[etag_key] = {
                        "etag": r.headers.get("ETag", ""),
                        "last_modified": r.headers.get("Last-Modified", ""),
                        "url": url,
                    }
                    self._save_etags()
                return r
            except (requests.RequestException, IOError) as e:  # includes ChunkedEncodingError / IncompleteRead
                last_err = e
                self.log.append(f"attempt {attempt} failed for {url}: {e}")
                if attempt < self.attempts:
                    time.sleep(2 * attempt)
        assert last_err is not None
        raise last_err

    def get_json(self, url: str, **kw):
        r = self.get(url, **kw)
        if r is NOT_MODIFIED:
            return NOT_MODIFIED
        return r.json()

    def get_text(self, url: str, **kw):
        r = self.get(url, **kw)
        if r is NOT_MODIFIED:
            return NOT_MODIFIED
        r.encoding = r.encoding or "utf-8"
        return r.text
