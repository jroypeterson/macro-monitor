"""⛑ REFUSE a non-loopback connection BEFORE it is made.

**What was measured.** 2026-09-11, `scripts/pytest_fleet_guard.py` (fleet board
#368 Phase 2) ran this suite with `socket.socket.connect` /
`socket.create_connection` patched to refuse a non-loopback address, and caught
`tests/test_predmarkets.py::test_discovery_seeds_first_run_then_surfaces_new`
(10 connections) and `::test_discovery_skips_low_volume` (5) opening real HTTPS
sessions to `104.18.29.246:443` and `13.33.82.32:443` -- PredictIt and Kalshi.

**Both tests believed they were offline.** Each monkeypatches
`DISC.client.search_events` and `DISC.client.fetch_event`, and the module
docstring says *"Network-free: the Polymarket client is exercised via
monkeypatched search/fetch"*. That was true of Polymarket and of nothing else:
`discovery.discover_new` gathers from THREE sources, and `_gather_predictit`
(`predictit.fetch_all`, three retries with sleeps) and `_gather_kalshi`
(`_kget` -> `requests.get`) each wrap their call in `except Exception: continue`.
So the live calls were invisible twice over -- absent from the stub list, and
absent from the result, because a failure is swallowed by design. The tests
passed identically online and offline; on a plane they would have passed too.

**Whose fault that is matters less than the shape:** a test is offline only if
something refuses the wire, not if the author listed the collaborators they
thought of. That is root `CLAUDE.md`'s *"assert the negative, at runtime, before
the call"*, and the fleet guard's own write-up records that **no `conftest.py` in
58 repos refused a socket** before 2026-09-11. This is the second, copied
deliberately from `notion_watchlist/conftest.py` (`hooks.slack.com` on every run)
rather than invented again.

**One thing this fixture cannot do** is make a swallowed refusal visible: the
`RuntimeError` below is caught by those same `except Exception` handlers, so a
test that reaches for the wire goes quiet rather than red. The wire is still shut,
which is the point -- but it means the two tests above ALSO stub their other two
sources explicitly, so the coverage they claim is coverage they have.

Opt out with `@pytest.mark.allow_network` for a test that genuinely needs the
wire. Nothing in this suite does.
"""
from __future__ import annotations

import socket

import pytest

_LOOPBACK_PREFIXES = ("127.", "::1", "localhost", "0.0.0.0")


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) and address else address
    return isinstance(host, str) and host.startswith(_LOOPBACK_PREFIXES)


@pytest.fixture(autouse=True)
def _no_live_network(request, monkeypatch):
    if request.node.get_closest_marker("allow_network"):
        return
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def _refuse(address):
        raise RuntimeError(
            f"live network refused in tests: {address!r}. A unit test must not "
            f"reach the wire -- stub the collaborator (predmarkets: "
            f"`client.search_events`/`client.fetch_event`, "
            f"`predictit.fetch_all`, `discovery._kget`; collectors: the `fetch` "
            f"argument), or mark the test `@pytest.mark.allow_network` if it "
            f"truly needs it.")

    def guarded_connect(self, address, *a, **kw):
        if not _is_loopback(address):
            _refuse(address)
        return real_connect(self, address, *a, **kw)

    def guarded_create(address, *a, **kw):
        if not _is_loopback(address):
            _refuse(address)
        return real_create(address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "allow_network: this test may open a non-loopback socket")
