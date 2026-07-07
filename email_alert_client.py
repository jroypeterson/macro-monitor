"""[ClaudeFin] email-alert client — self-contained (CI-vendored) copy.

Fleet convention: root ``CONVENTIONS.md`` "Email alerts ([ClaudeFin])". The
canonical implementation lives in ``<workspace>/_shared/email_alert``, but this
project's alerting lane (the weekly Ahead-of-the-Curve rebuild) runs in GitHub
Actions where only the repo is checked out — the workspace-root sibling does
NOT exist. So instead of the usual thin import-shim, this module vendors the
tiny sender itself (same public contract, same subject grammar):

* ``send_alert(project, subject, body_text, body_html=None, attachments=None,
  to=None) -> bool`` — pass ONLY the ``<what>`` part as ``subject``.
* Subject grammar: ``[ClaudeFin] <project> — <what>`` (``format_subject``).
* Creds: env ``GMAIL_ADDRESS`` / ``GMAIL_APP_PASSWORD`` first (GitHub Actions
  secrets), then the local ``Coverage Manager/.env`` fallback (local runs only;
  harmlessly absent in CI).
* Recipient: ``EMAIL_ALERT_TO`` env override, else jroypeterson@gmail.com.
* NEVER raises — any failure returns ``False`` + a ``[WARN]`` on stderr, so a
  report build is never gated on email delivery. 3 attempts with backoff
  (backoff skipped under pytest).

Keep behavior in sync with ``_shared/email_alert/email_alert/sender.py``.
"""
from __future__ import annotations

import os
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

SUBJECT_TAG = "[ClaudeFin]"
DEFAULT_TO = "jroypeterson@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_TIMEOUT = 30
ATTEMPTS = 3

# ``<workspace>/macro_monitor/email_alert_client.py`` -> workspace root is 1 up.
# (In CI the repo is checked out elsewhere and this fallback simply won't exist.)
_WORKSPACE = Path(__file__).resolve().parents[1]

# Known sibling .env files carrying GMAIL_ADDRESS / GMAIL_APP_PASSWORD.
# Checked in order, only when the real environment doesn't have both keys.
# Tests monkeypatch this list to [] to isolate from the local machine.
FALLBACK_ENV_PATHS: list[Path] = [
    _WORKSPACE / "Coverage Manager" / ".env",
]


def _warn(msg: str) -> None:
    print(f"[WARN] email_alert: {msg}", file=sys.stderr)


def _sleep(seconds: float) -> None:
    """Backoff sleep, skipped under pytest."""
    if "PYTEST_CURRENT_TEST" not in os.environ:
        time.sleep(seconds)


def _read_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser — BOM-tolerant, quote-stripping."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _resolve_credentials() -> tuple[str, str] | None:
    """(address, app_password) from env, else the first fallback .env with both."""
    addr = os.environ.get("GMAIL_ADDRESS", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if addr and pw:
        return addr, pw
    for path in FALLBACK_ENV_PATHS:
        vals = _read_env_file(path)
        f_addr = (addr or vals.get("GMAIL_ADDRESS", "")).strip()
        f_pw = (pw or vals.get("GMAIL_APP_PASSWORD", "")).strip()
        if f_addr and f_pw:
            return f_addr, f_pw
    return None


def format_subject(project: str, subject: str) -> str:
    """The fleet-wide subject grammar: ``[ClaudeFin] <project> — <what>``."""
    return f"{SUBJECT_TAG} {project} — {subject}"


def send_alert(
    project: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments=None,
    to: str | None = None,
) -> bool:
    """Send a [ClaudeFin] alert email. Returns True on success, False otherwise.

    NEVER raises — any failure (missing creds, SMTP error, bad attachment
    path, programming surprise) is reported as a stderr ``[WARN]`` + ``False``
    so report generation is never gated on email delivery.
    """
    try:
        creds = _resolve_credentials()
        if not creds:
            _warn(
                "GMAIL_ADDRESS/GMAIL_APP_PASSWORD not set (env or fallback .env) — "
                f"alert NOT sent: {format_subject(project, subject)!r}"
            )
            return False
        addr, pw = creds

        msg = EmailMessage()
        msg["Subject"] = format_subject(project, subject)
        msg["From"] = addr
        msg["To"] = (to or os.environ.get("EMAIL_ALERT_TO", "").strip() or DEFAULT_TO)
        msg.set_content(body_text or subject)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        for path in attachments or []:
            try:
                p = Path(path)
                msg.add_attachment(
                    p.read_bytes(),
                    maintype="application",
                    subtype="octet-stream",
                    filename=p.name,
                )
            except OSError as e:
                # A bad attachment must not sink the alert itself.
                _warn(f"attachment skipped ({path}): {e}")

        last_err: Exception | None = None
        for attempt in range(ATTEMPTS):
            try:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
                    server.login(addr, pw)
                    server.send_message(msg)
                return True
            except smtplib.SMTPAuthenticationError as e:
                # Retrying a bad password is pointless — fail fast + loud.
                _warn(f"Gmail authentication failed — check GMAIL_APP_PASSWORD: {e}")
                return False
            except Exception as e:  # noqa: BLE001 — SMTP/OS/network; retry then report
                last_err = e
                if attempt < ATTEMPTS - 1:
                    _sleep(5 * (attempt + 1))
        _warn(f"send failed after {ATTEMPTS} attempts: {last_err}")
        return False
    except Exception as e:  # noqa: BLE001 — contract: never raise into the caller
        _warn(f"unexpected error ({type(e).__name__}): {e}")
        return False
