"""Download the top-down market datasets (Ken French / AQR / Shiller): save each file to a
dated raw archive + a `latest/` mirror, and write a manifest. Polite (real UA + contact,
inter-request delay, retry/backoff); 404s are recorded, not fatal.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from .sources import DATASETS

_ROOT = Path(__file__).parent / "data"
_UA = "macro_monitor/market research mirror (contact: jroypeterson@gmail.com)"


def _get(session: requests.Session, url: str, retries: int = 3, timeout: float = 45.0):
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 * (2 ** attempt))
    raise requests.RequestException(f"{url}: failed after {retries} attempts: {last}")


def download(records: list[dict] | None = None, out_root: Path = _ROOT,
             delay: float = 0.5, relevance: set[str] | None = None) -> dict:
    records = records if records is not None else DATASETS
    if relevance:
        records = [r for r in records if r["relevance"] in relevance]

    today = date.today().isoformat()
    raw_dir = out_root / "raw" / today
    latest_dir = out_root / "latest"
    raw_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": today, "requested": len(records), "ok": [], "missing": [], "error": [],
    }
    session = requests.Session()
    session.headers["User-Agent"] = _UA

    for rec in records:
        try:
            r = _get(session, rec["url"])
            if r.status_code == 404:
                manifest["missing"].append({"id": rec["id"], "url": rec["url"]})
                print(f"  [404] {rec['id']}")
            else:
                (raw_dir / rec["file"]).write_bytes(r.content)
                (latest_dir / rec["file"]).write_bytes(r.content)
                manifest["ok"].append({"id": rec["id"], "source": rec["source"],
                                       "file": rec["file"], "bytes": len(r.content)})
                print(f"  [ok]  {rec['source']:14} {rec['id']} ({len(r.content)//1024}KB)")
        except Exception as exc:  # noqa: BLE001
            manifest["error"].append({"id": rec["id"], "url": rec["url"], "error": str(exc)})
            print(f"  [ERR] {rec['id']}: {exc}")
        time.sleep(delay)

    payload = json.dumps(manifest, indent=2)
    (raw_dir / "manifest.json").write_text(payload, encoding="utf-8")
    (out_root / "manifest_latest.json").write_text(payload, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = download()
    print(f"\nok={len(m['ok'])} missing={len(m['missing'])} error={len(m['error'])}")
