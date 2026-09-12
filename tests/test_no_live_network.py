"""The suite must not reach the wire. Asserted, not assumed.

Fleet board #368 Phase 2. `scripts/pytest_fleet_guard.py` measured this suite on
2026-09-11 and caught `test_predmarkets.py::test_discovery_seeds_first_run_then_
surfaces_new` (10 connections) and `::test_discovery_skips_low_volume` (5) opening
live HTTPS sessions to PredictIt and Kalshi while their module docstring said
"Network-free". `tests/conftest.py::_no_live_network` refuses a non-loopback
address before the connect; these tests are what stops that fixture from being
removed or narrowed with nothing going red.

Both directions are pinned (`validate-BOTH-sides-of-a-classifier`): a fixture
that refused everything would pass the first three tests and break every
legitimate local socket, and `test_research_digest.py::test_fetch_source_returns_
empty_with_error_on_bad_url` depends on loopback still connecting for real.
"""
from __future__ import annotations

import socket

import pytest
import requests


def test_create_connection_to_a_real_host_is_refused():
    with pytest.raises(RuntimeError, match="live network refused"):
        socket.create_connection(("example.com", 443), timeout=5)


def test_a_raw_socket_connect_is_refused():
    s = socket.socket()
    try:
        with pytest.raises(RuntimeError, match="live network refused"):
            s.connect(("1.1.1.1", 443))
    finally:
        s.close()


def test_requests_surfaces_the_refusal_rather_than_a_retry_loop():
    """`requests`/`urllib3` only wrap `OSError`, so the guard's `RuntimeError`
    propagates verbatim instead of becoming a generic ConnectionError --
    which is what makes the message tell the next author what to stub."""
    with pytest.raises(RuntimeError, match="live network refused"):
        requests.get("https://example.com", timeout=5)


def test_loopback_still_connects_for_real():
    """Not "is not refused" -- actually reaches the OS. A listener on 127.0.0.1
    must be reachable, because `test_research_digest.py` uses a closed loopback
    port to exercise `fetch_source`'s transport-failure path."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=5)
        client.close()
    finally:
        server.close()


@pytest.mark.allow_network
def test_the_marker_opts_a_test_out(monkeypatch):
    """The escape hatch has to work, or the next author who needs the wire
    deletes the fixture instead of marking their test. Checked by observing that
    the guard is not installed -- this test does not itself open a connection."""
    assert "guarded_create" not in getattr(socket.create_connection, "__name__", "")
