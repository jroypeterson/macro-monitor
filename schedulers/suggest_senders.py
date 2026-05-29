"""One-off research-sender suggester.

Scans the inbox for senders that look like macro / strategy / economist
newsletters, ranks by frequency over the last N days, and prints a
candidate list the user can review before adding to
`gmail_senders:` in fed_research_sources.yaml.

Not autonomous — surfaces candidates only, never modifies config.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from ..collectors.gmail import build_service

# Keyword patterns that signal macro/strategy/research newsletters.
# Used against the From line + sample subjects. High-recall, low-precision —
# the user reviews the list before adding anything.
RESEARCH_PATTERNS = re.compile(
    r"(macro|strategy|strateg(?:i|y)|economic|economist|markets?|"
    r"daily(?: spark| chart| update)?|weekly(?: review| update)?|"
    r"research|commentary|outlook|chartbook|"
    r"yardeni|slok|apollo|bianco|piper|nomura|barclays|citi|"
    r"goldman|morgan|jpmorgan|wells fargo|deutsche|hsbc|"
    r"federal reserve|fed (?:bank|board)|brookings|peterson|"
    r"hutchins|piie)",
    re.IGNORECASE,
)

# Subjects that suggest commentary/research content (vs. transactional)
SUBJECT_RESEARCH_HINTS = re.compile(
    r"(chart|outlook|daily|weekly|today|brief|note|comment|review|"
    r"deep dive|update|forecast|preview|recap|summary)",
    re.IGNORECASE,
)

# Senders to EXCLUDE — known noise.
EXCLUDE_PATTERNS = re.compile(
    r"(no-?reply|noreply|do-?not-?reply|donotreply|"
    r"@mailer\.|@email\.|mailchimp|sendgrid|"
    r"calendar|reminder|notification|alert|"
    r"receipt|invoice|confirmation|order|"
    r"linkedin|twitter|facebook|github|"
    r"zoom|microsoft|google|adobe)",
    re.IGNORECASE,
)


@dataclass
class SenderCandidate:
    from_field: str           # raw From header value
    display_name: str
    email_address: str
    domain: str
    count_90d: int
    sample_subjects: list[str]
    research_score: int       # crude relevance heuristic 0-3


def scan_inbox(days: int = 90, max_messages_to_scan: int = 2000) -> list[SenderCandidate]:
    """Scan recent inbox for recurring senders that look like research."""
    svc = build_service()

    # Pull the From + Subject + Date headers via metadata format —
    # cheaper than full message bodies.
    query = f"newer_than:{days}d"
    sender_data: dict[str, dict] = {}
    page_token: str | None = None
    seen = 0

    while seen < max_messages_to_scan:
        kwargs = dict(userId="me", q=query, maxResults=500)
        if page_token:
            kwargs["pageToken"] = page_token
        resp = svc.users().messages().list(**kwargs).execute()
        for m in resp.get("messages", []):
            seen += 1
            if seen > max_messages_to_scan:
                break
            full = svc.users().messages().get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in full.get("payload", {}).get("headers", [])
            }
            from_field = (headers.get("From") or "").strip()
            subject = (headers.get("Subject") or "").strip()
            if not from_field:
                continue

            email_addr = _extract_email(from_field)
            display_name = _extract_display_name(from_field)
            domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""

            key = email_addr.lower()
            if key not in sender_data:
                sender_data[key] = {
                    "from_field": from_field,
                    "display_name": display_name,
                    "email_address": email_addr,
                    "domain": domain,
                    "count": 0,
                    "subjects": [],
                }
            sender_data[key]["count"] += 1
            if len(sender_data[key]["subjects"]) < 3 and subject:
                sender_data[key]["subjects"].append(subject)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # Convert to candidate list, filter, score, rank
    candidates: list[SenderCandidate] = []
    for data in sender_data.values():
        # Exclusion filter
        if EXCLUDE_PATTERNS.search(data["from_field"]):
            continue
        # Drop senders we only saw 1-2 times (not recurring)
        if data["count"] < 2:
            continue

        score = _score_research_relevance(data)
        if score == 0:
            continue

        candidates.append(
            SenderCandidate(
                from_field=data["from_field"],
                display_name=data["display_name"],
                email_address=data["email_address"],
                domain=data["domain"],
                count_90d=data["count"],
                sample_subjects=data["subjects"],
                research_score=score,
            )
        )

    # Rank: research score desc, then frequency desc
    candidates.sort(key=lambda c: (-c.research_score, -c.count_90d))
    return candidates


def _score_research_relevance(data: dict) -> int:
    """0 = not research; 3 = strong signal. Combines From-field keywords
    and subject-line patterns."""
    score = 0
    from_match = RESEARCH_PATTERNS.search(data["from_field"])
    if from_match:
        score += 2
    subj_matches = sum(
        1 for s in data["subjects"] if SUBJECT_RESEARCH_HINTS.search(s)
    )
    if subj_matches >= 2:
        score += 1
    elif subj_matches == 1:
        score += 0  # weak — don't promote on one match alone
    return min(score, 3)


def _extract_email(from_field: str) -> str:
    """'Jane Doe <jane@example.com>' -> 'jane@example.com'."""
    m = re.search(r"<([^>]+)>", from_field)
    if m:
        return m.group(1).strip()
    # Bare email
    m = re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", from_field)
    if m:
        return m.group(0).strip()
    return from_field.strip()


def _extract_display_name(from_field: str) -> str:
    """'Jane Doe <jane@example.com>' -> 'Jane Doe'.
    'jane@example.com' -> 'jane@example.com' (no name)."""
    m = re.match(r'^"?([^"<]+?)"?\s*<', from_field)
    if m:
        return m.group(1).strip()
    return _extract_email(from_field).split("@")[0]


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------


def format_candidates(candidates: list[SenderCandidate], limit: int = 30) -> str:
    """Format the ranked list for human review."""
    if not candidates:
        return "No candidate research senders found in the scanned window."

    lines = [
        f"Top {min(limit, len(candidates))} research-sender candidates "
        f"({len(candidates)} total matched):",
        "",
        "Add interesting ones to config/fed_research_sources.yaml under",
        "`gmail_senders:` — see torsten_slok entry as the template.",
        "",
    ]
    for c in candidates[:limit]:
        lines.append(f"  ★{c.research_score} [{c.count_90d:3}x] {c.display_name}")
        lines.append(f"        from: {c.email_address}")
        for subj in c.sample_subjects:
            lines.append(f"        ─ {subj[:80]}")
        lines.append("")
    return "\n".join(lines)
