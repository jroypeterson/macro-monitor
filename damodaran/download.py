"""Download Damodaran's datasets: save each file to a dated raw archive AND a `latest/`
mirror, and write a manifest of what succeeded / 404'd / errored.

Polite by design: a real User-Agent with contact, a small inter-request delay, and
retry-with-backoff on transient network errors. 404s are expected (not every family
exists for every region) and recorded, not fatal.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from .datasets import all_datasets

_ROOT = Path(__file__).parent / "data"
_UA = "macro_monitor/damodaran research mirror (contact: jroypeterson@gmail.com)"


def _get(session: requests.Session, url: str, retries: int = 3, timeout: float = 30.0):
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 404:
                return r  # definitive miss; don't retry
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 * (2 ** attempt))
    raise requests.RequestException(f"{url}: failed after {retries} attempts: {last}")


def download(records: list[dict] | None = None, out_root: Path = _ROOT,
             delay: float = 0.4, relevance: set[str] | None = None) -> dict:
    """Fetch each record. `relevance` optionally filters to e.g. {'high','medium'}.
    Returns the manifest dict (also written to disk)."""
    records = records if records is not None else all_datasets()
    if relevance:
        records = [r for r in records if r["relevance"] in relevance]

    today = date.today().isoformat()
    raw_dir = out_root / "raw" / today
    latest_dir = out_root / "latest"
    raw_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": today, "requested": len(records),
        "ok": [], "missing": [], "error": [],
    }
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    for i, rec in enumerate(records, 1):
        try:
            r = _get(session, rec["url"])
            if r.status_code == 404:
                manifest["missing"].append({"id": rec["id"], "url": rec["url"]})
            else:
                (raw_dir / rec["file"]).write_bytes(r.content)
                (latest_dir / rec["file"]).write_bytes(r.content)
                manifest["ok"].append({"id": rec["id"], "file": rec["file"],
                                       "bytes": len(r.content), "category": rec["category"],
                                       "region": rec["region"]})
        except Exception as exc:  # noqa: BLE001 — record + continue, never abort the run
            manifest["error"].append({"id": rec["id"], "url": rec["url"], "error": str(exc)})
        if i % 25 == 0:
            print(f"  ...{i}/{len(records)} ({len(manifest['ok'])} ok, "
                  f"{len(manifest['missing'])} missing, {len(manifest['error'])} err)")
        time.sleep(delay)

    payload = json.dumps(manifest, indent=2)
    (raw_dir / "manifest.json").write_text(payload, encoding="utf-8")
    (out_root / "manifest_latest.json").write_text(payload, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = download()
    print(f"\nok={len(m['ok'])} missing={len(m['missing'])} error={len(m['error'])}")
