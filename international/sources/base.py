"""Shared HTTP helpers for source clients."""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT = 30  # seconds — international endpoints can be slow


class SourceError(RuntimeError):
    """Raised by any source fetcher on a non-recoverable fetch/parse error.
    The collector catches this per-series so one dead source is isolated."""


def make_session() -> requests.Session:
    s = requests.Session()
    # Some national stat sites (notably ONS/BoE) 403 a default python UA.
    s.headers.update(
        {
            "User-Agent": "macro-monitor/1.0 (+https://github.com/jroypeterson/macro-monitor)",
            "Accept": "application/json, text/csv, */*",
        }
    )
    return s


def get(session: requests.Session, url: str, *, params=None, headers=None,
        timeout: int = DEFAULT_TIMEOUT) -> requests.Response:
    try:
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        raise SourceError(f"GET {url} failed: {exc}") from exc
