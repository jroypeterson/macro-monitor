"""Tests for the [ClaudeFin] weekly AoC email alert: the vendored sender's
contract (subject grammar, never-raises, False-on-failure), the pure
(subject, body) builder, and the CLI's non-gating warning path.

No real email is ever sent — SMTP is monkeypatched and the local
Coverage Manager .env fallback is disabled per test.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from macro_monitor import email_alert_client
from macro_monitor.ahead_of_curve.build import GALLERY_URL, build_email_alert


def _no_creds(monkeypatch) -> None:
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.setattr(email_alert_client, "FALLBACK_ENV_PATHS", [])


# ---------------------------------------------------------------- sender


def test_format_subject_grammar():
    assert (
        email_alert_client.format_subject("macro_monitor", "Weekly AoC gallery rebuild — 23 figures")
        == "[ClaudeFin] macro_monitor — Weekly AoC gallery rebuild — 23 figures"
    )


def test_send_alert_no_creds_returns_false_and_warns(monkeypatch, capsys):
    _no_creds(monkeypatch)
    ok = email_alert_client.send_alert("macro_monitor", "test subject", "body")
    assert ok is False
    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "GMAIL_ADDRESS" in err


def test_send_alert_smtp_failure_never_raises(monkeypatch, capsys):
    monkeypatch.setenv("GMAIL_ADDRESS", "x@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise OSError("network down")

    monkeypatch.setattr(email_alert_client.smtplib, "SMTP_SSL", boom)
    ok = email_alert_client.send_alert("macro_monitor", "subj", "body")
    assert ok is False
    assert calls["n"] == email_alert_client.ATTEMPTS  # retried, backoff skipped under pytest
    assert "[WARN]" in capsys.readouterr().err


def test_send_alert_success_sends_prefixed_subject(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "x@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.delenv("EMAIL_ALERT_TO", raising=False)
    sent = {}

    class FakeServer:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, addr, pw):
            sent["login"] = addr

        def send_message(self, msg):
            sent["subject"] = msg["Subject"]
            sent["to"] = msg["To"]

    monkeypatch.setattr(email_alert_client.smtplib, "SMTP_SSL", lambda *a, **k: FakeServer())
    ok = email_alert_client.send_alert("macro_monitor", "Weekly AoC gallery rebuild — 23 figures", "body")
    assert ok is True
    assert sent["subject"] == "[ClaudeFin] macro_monitor — Weekly AoC gallery rebuild — 23 figures"
    assert sent["to"] == email_alert_client.DEFAULT_TO


# ---------------------------------------------------------------- builder


def _fake_rendered(n: int = 23, index: bool = True) -> dict[str, Path]:
    # Anchor under the package dir — cmd_ahead_of_curve prints each PNG
    # relative_to() the package, which raises on foreign paths.
    out_dir = Path(email_alert_client.__file__).parent / "readable" / "ahead_of_curve"
    rendered = {f"fig_{i}": out_dir / f"fig_{i}.png" for i in range(n)}
    if index:
        rendered["index"] = out_dir / "index.html"
    return rendered


def test_build_email_alert_subject_and_body():
    subject, body = build_email_alert(_fake_rendered(23))
    # Subject is ONLY the <what> part — the sender adds the [ClaudeFin] prefix.
    assert subject == "Weekly AoC gallery rebuild — 23 figures"
    assert "[ClaudeFin]" not in subject
    assert "Figures rendered: 23" in body
    assert GALLERY_URL in body
    assert "#macro-and-markets" in body


def test_build_email_alert_missing_index_is_loud():
    subject, body = build_email_alert(_fake_rendered(5, index=False))
    assert subject == "Weekly AoC gallery rebuild — 5 figures"
    assert "NOT rebuilt" in body


# ---------------------------------------------------------------- CLI non-gating


def test_cmd_ahead_of_curve_email_failure_is_non_gating(monkeypatch, capsys):
    """A False from send_alert must produce a warning, NOT a failed run."""
    from macro_monitor import cli
    from macro_monitor.ahead_of_curve import build as build_mod

    monkeypatch.setattr(build_mod, "build", lambda: _fake_rendered(3))
    monkeypatch.setattr(email_alert_client, "send_alert", lambda *a, **k: False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    rc = cli.cmd_ahead_of_curve(argparse.Namespace(email=True))
    assert rc == 0  # non-gating: run still succeeds
    captured = capsys.readouterr()
    assert "[WARN]" in captured.err
    assert "non-gating" in captured.err
    assert "::warning ::" in captured.out  # visible in the Actions run UI


def test_cmd_ahead_of_curve_email_success(monkeypatch, capsys):
    from macro_monitor import cli
    from macro_monitor.ahead_of_curve import build as build_mod

    seen = {}

    def fake_send(project, subject, body_text, **kwargs):
        seen["project"] = project
        seen["subject"] = subject
        return True

    monkeypatch.setattr(build_mod, "build", lambda: _fake_rendered(3))
    monkeypatch.setattr(email_alert_client, "send_alert", fake_send)

    rc = cli.cmd_ahead_of_curve(argparse.Namespace(email=True))
    assert rc == 0
    assert seen["project"] == "macro_monitor"
    assert seen["subject"] == "Weekly AoC gallery rebuild — 3 figures"
    assert "Email alert sent." in capsys.readouterr().err


def test_cmd_ahead_of_curve_no_email_flag_sends_nothing(monkeypatch):
    from macro_monitor import cli
    from macro_monitor.ahead_of_curve import build as build_mod

    monkeypatch.setattr(build_mod, "build", lambda: _fake_rendered(2))

    def explode(*a, **k):  # pragma: no cover - would fail the test if called
        raise AssertionError("send_alert must not be called without --email")

    monkeypatch.setattr(email_alert_client, "send_alert", explode)
    rc = cli.cmd_ahead_of_curve(argparse.Namespace(email=False))
    assert rc == 0
