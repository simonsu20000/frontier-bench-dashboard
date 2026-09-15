"""Source contract, failure isolation and last-good caching."""
from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from ..http import NOT_MODIFIED, Http, NotModified
from ..records import ScoreRecord
from ..util import now_iso


@dataclass
class SourceStatus:
    id: str
    name: str
    url: str = ""
    license: str = ""
    status: str = "ok"                 # ok | cached | failed
    fetched_at: str = ""               # last successful fetch (UTC)
    upstream_updated_at: str = ""      # newest date seen in the upstream data
    records: int = 0
    consecutive_failures: int = 0
    error: str = ""
    stale: bool = False
    stale_after_days: int = 7
    not_modified: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceResult:
    records: list[ScoreRecord]
    status: SourceStatus
    extras: dict = field(default_factory=dict)


class Source:
    id = "base"
    name = "Base"
    url = ""
    license = ""
    stale_after_days = 7

    def fetch(self, http: Http):
        raise NotImplementedError

    def parse(self, raw) -> tuple[list[ScoreRecord], dict]:
        raise NotImplementedError


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _load_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _compute_stale(status: SourceStatus, today: date):
    if not status.upstream_updated_at:
        status.stale = False
        return
    try:
        seen = date.fromisoformat(status.upstream_updated_at[:10])
    except ValueError:
        status.stale = False
        return
    status.stale = (today - seen).days > status.stale_after_days


def run_source(src: Source, http: Http | None, cache_dir: Path, offline: bool = False,
               today: date | None = None) -> SourceResult:
    """Fetch+parse with isolation: any failure falls back to the last good cache."""
    today = today or datetime.now(timezone.utc).date()
    cache_path = Path(cache_dir) / f"{src.id}.json"
    prev = _load_cache(cache_path)
    prev_status = SourceStatus(**{k: v for k, v in (prev or {}).get("status", {}).items() if k in SourceStatus.__dataclass_fields__}) \
        if prev else SourceStatus(id=src.id, name=src.name, url=src.url, license=src.license)
    prev_records = [ScoreRecord.from_dict(d) for d in (prev or {}).get("records", [])]
    prev_extras = (prev or {}).get("extras", {})

    def cached_result(status_value: str, error: str = "") -> SourceResult:
        st = prev_status
        st.id, st.name, st.url, st.license = src.id, src.name, src.url, src.license
        st.status = status_value
        st.error = error
        st.records = len(prev_records)
        st.stale_after_days = src.stale_after_days
        st.not_modified = False
        _compute_stale(st, today)
        return SourceResult(prev_records, st, prev_extras)

    if offline or http is None:
        if prev is None:
            st = SourceStatus(id=src.id, name=src.name, url=src.url, license=src.license, status="failed",
                              error="offline and no cache", stale_after_days=src.stale_after_days)
            return SourceResult([], st, {})
        # an offline rebuild reuses the last parse without changing its health status
        res = cached_result(prev_status.status or "ok", prev_status.error)
        res.status.consecutive_failures = prev_status.consecutive_failures or 0
        res.status.note = "offline rebuild"
        return res

    try:
        raw = src.fetch(http)
        if raw is NOT_MODIFIED or isinstance(raw, NotModified):
            if prev is None:
                raise RuntimeError("upstream returned 304 but no cache exists; clear data/raw/etags.json")
            res = cached_result("ok")
            res.status.not_modified = True
            res.status.consecutive_failures = 0
            res.status.fetched_at = now_iso()
            return res
        records, extras = src.parse(raw)
        status = SourceStatus(
            id=src.id, name=src.name, url=src.url, license=src.license, status="ok",
            fetched_at=now_iso(), upstream_updated_at=str(extras.get("upstream_updated_at", "") or ""),
            records=len(records), consecutive_failures=0, stale_after_days=src.stale_after_days,
            note=str(extras.get("note", "") or ""),
        )
        _compute_stale(status, today)
        payload = {"status": status.to_dict(), "records": [r.to_dict() for r in records],
                   "extras": {k: v for k, v in extras.items()}}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n",
                              encoding="utf-8")
        return SourceResult(records, status, extras)
    except Exception as e:  # noqa: BLE001 - isolation is the point
        err = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc(limit=3)
        if prev is None:
            st = SourceStatus(id=src.id, name=src.name, url=src.url, license=src.license, status="failed",
                              error=err, consecutive_failures=1, stale_after_days=src.stale_after_days, note=tb[-600:])
            return SourceResult([], st, {})
        res = cached_result("cached", err)
        res.status.consecutive_failures = (prev_status.consecutive_failures or 0) + 1
        res.status.note = tb[-600:]
        # persist the failure count so the next run can escalate
        prev["status"] = res.status.to_dict()
        cache_path.write_text(json.dumps(prev, ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n",
                              encoding="utf-8")
        return res
