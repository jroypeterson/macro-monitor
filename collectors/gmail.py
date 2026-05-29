"""Gmail collector for the research digest.

Reads emails from an allowlist of senders (config/fed_research_sources.yaml
under `gmail_senders:`) using the user OAuth token shared across projects.
For each new email since the last digest, returns a ResearchPost with the
sender's display name, subject as the title, first ~300 chars of the
plain-text body as the summary, and a Gmail web URL.

Dedupe key: Gmail message id (stable, unique). Stored in the same
state/research_posted.db that the RSS collector uses, just keyed by
`gmail:<message_id>` instead of a URL so the namespace doesn't collide.

Token discovery: tries (in order)
  1. GMAIL_TOKEN_PATH env var (used by GH Actions to point at the
     secret-materialized JSON file)
  2. portfolio_daily/gmail_token.json (shared across local projects)
  3. earnings_agent/gmail_token.json
Refreshes automatically via the saved refresh_token.
"""

from __future__ import annotations

import base64
import email
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .rss import ResearchPost

# Allow standard Gmail readonly OR modify scope; we only need to read.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

# Default token search locations.
_TOKEN_CANDIDATES = [
    Path(__file__).parent.parent.parent / "portfolio_daily" / "gmail_token.json",
    Path(__file__).parent.parent.parent / "earnings_agent" / "gmail_token.json",
]


@dataclass(frozen=True)
class GmailSender:
    """One sender entry in fed_research_sources.yaml -> gmail_senders."""

    id: str
    display_name: str
    query: str             # Gmail search syntax (e.g., "from:agm@apollo.com")
    max_items_per_run: int = 3
    newer_than_days: int = 7


def find_gmail_token() -> Path | None:
    """Resolve the path to gmail_token.json. Returns None if not found."""
    override = os.environ.get("GMAIL_TOKEN_PATH")
    if override:
        p = Path(override.strip().strip('"').strip("'"))
        if p.exists():
            return p
    for cand in _TOKEN_CANDIDATES:
        if cand.exists():
            return cand
    return None


def build_service(token_path: Path | None = None):
    """Construct an authenticated Gmail service. Imports the google libs
    lazily so collectors can be imported even when the libs aren't
    installed (e.g., on a stripped-down test environment).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if token_path is None:
        token_path = find_gmail_token()
    if token_path is None:
        raise RuntimeError(
            "No gmail_token.json found. Set GMAIL_TOKEN_PATH env var or "
            "ensure portfolio_daily/gmail_token.json exists."
        )

    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def load_gmail_senders(cfg: dict | None = None) -> list[GmailSender]:
    """Parse the gmail_senders section of fed_research_sources.yaml."""
    if cfg is None:
        import yaml
        from .rss import DEFAULT_SOURCES_PATH

        cfg = yaml.safe_load(
            Path(DEFAULT_SOURCES_PATH).read_text(encoding="utf-8")
        )
    out: list[GmailSender] = []
    for s in cfg.get("gmail_senders", []) or []:
        out.append(
            GmailSender(
                id=s["id"],
                display_name=s["display_name"],
                query=s["query"],
                max_items_per_run=s.get("max_items_per_run", 3),
                newer_than_days=s.get("newer_than_days", 7),
            )
        )
    return out


def fetch_sender(service, sender: GmailSender) -> tuple[list[ResearchPost], str | None]:
    """Pull messages matching a sender's Gmail query. Returns (posts, error)."""
    try:
        # Append `newer_than:Nd` to the query to bound the fetch
        full_query = f"{sender.query} newer_than:{sender.newer_than_days}d"
        results = service.users().messages().list(
            userId="me",
            q=full_query,
            maxResults=sender.max_items_per_run,
        ).execute()
    except Exception as e:  # noqa: BLE001
        return [], f"gmail list error: {type(e).__name__}: {e}"

    posts: list[ResearchPost] = []
    for msg_meta in results.get("messages", []):
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_meta["id"],
                format="full",
            ).execute()
        except Exception as e:  # noqa: BLE001
            # Skip this one but continue with the rest
            continue
        post = _message_to_post(msg, sender)
        if post is not None:
            posts.append(post)
    return posts, None


def fetch_all_senders(
    senders: list[GmailSender], service=None
) -> tuple[list[ResearchPost], list[tuple[str, str]]]:
    """Iterate senders with per-sender graceful degradation."""
    posts: list[ResearchPost] = []
    errors: list[tuple[str, str]] = []

    if not senders:
        return posts, errors

    if service is None:
        try:
            service = build_service()
        except Exception as e:  # noqa: BLE001
            return [], [("gmail_auth", f"{type(e).__name__}: {e}")]

    for sender in senders:
        items, err = fetch_sender(service, sender)
        posts.extend(items)
        if err:
            errors.append((sender.id, err))
    return posts, errors


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------


def _message_to_post(msg: dict, sender: GmailSender) -> ResearchPost | None:
    """Convert a Gmail message resource into a ResearchPost."""
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    subject = headers.get("subject", "").strip()
    if not subject:
        return None

    date_header = headers.get("date", "")
    pub_iso = _parse_date_to_iso(date_header)

    body_text = _extract_plain_body(msg.get("payload", {}))
    summary = _clean_summary(body_text, subject_to_strip=subject)

    # Gmail message permalink — opens in the user's authenticated browser
    msg_id = msg.get("id", "")
    url = f"https://mail.google.com/mail/u/0/#all/{msg_id}"

    # Dedupe namespace: "gmail:<message_id>" so it can't collide with RSS URLs.
    return ResearchPost(
        source_id=sender.id,
        source_display=sender.display_name,
        title=subject,
        url=f"gmail-msg:{msg_id}",  # canonical dedupe key
        summary=summary,
        published_at_iso=pub_iso,
        # NOTE: we override .url for display in the digest renderer;
        # see _render_blocks where we detect gmail-msg: prefix and swap
        # in the permalink. This keeps the dedupe key stable even if
        # Gmail changes its UI URL structure.
    )


def gmail_url_from_dedupe_key(key: str) -> str:
    """Map a gmail-msg:<id> dedupe key back to a browser URL."""
    if key.startswith("gmail-msg:"):
        msg_id = key[len("gmail-msg:"):]
        return f"https://mail.google.com/mail/u/0/#all/{msg_id}"
    return key


def _parse_date_to_iso(date_str: str) -> str:
    """RFC 2822 -> ISO 8601 UTC."""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def _extract_plain_body(payload: dict) -> str:
    """Walk the MIME payload tree to find the plain-text body."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_b64(data)
    for part in payload.get("parts", []) or []:
        text = _extract_plain_body(part)
        if text:
            return text
    # Fall back to HTML stripped to plain text
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            html = _decode_b64(data)
            return re.sub(r"<[^>]+>", "", html)
    return ""


def _decode_b64(data: str) -> str:
    """Gmail uses URL-safe base64 without padding."""
    try:
        # Pad to multiple of 4
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _clean_summary(
    text: str, max_len: int = 280, subject_to_strip: str | None = None
) -> str:
    """Strip extra whitespace, collapse lines, drop tracking URLs +
    newsletter boilerplate, and truncate.

    `subject_to_strip` — newsletter bodies often re-print the subject line
    early on. If we recognize it, we cut everything before (and the
    subject itself) so the summary is the actual content opener.
    """
    # Strip zero-width joiners / soft hyphens used by newsletters for spacing.
    text = re.sub(r"[​-‏⁠­͏]", "", text)
    # Strip URLs (tracking links litter the top of marketing emails).
    text = re.sub(r"https?://\S+", "", text)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    # If the body re-prints the subject line, cut everything up to and
    # including it. Newsletter convention: "Header text [date] [SUBJECT] [content]"
    if subject_to_strip and len(subject_to_strip) > 8:
        idx = text.lower().find(subject_to_strip.lower())
        if idx >= 0:
            text = text[idx + len(subject_to_strip):].lstrip(" -–—:.|")

    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text
