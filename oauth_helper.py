"""Gmail OAuth helper for adding new accounts.

Run via: `python -m macro_monitor.cli authorize-gmail --account <name>`

The flow:
  1. Read OAuth client credentials (the "installed app" JSON from Google
     Cloud Console — reused from earnings_agent/portfolio_daily, same
     earnings-agent-486621 GCP project)
  2. Start a local HTTP server on a random port (the redirect_uri)
  3. Open the user's browser to Google's consent screen
  4. User signs in as the target account and grants gmail.readonly
  5. Google redirects back to the local server with an auth code
  6. We exchange the code for tokens and save to disk

Token storage: Dropbox/API Keys/gmail_token_<account>.json so it's
accessible to all sibling projects under Claude Folder.
"""

from __future__ import annotations

from pathlib import Path

# Standard Gmail readonly scope — sufficient for reading mail; no
# label/send/modify access requested so the consent screen is minimal.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Token storage convention — matches analyst-days
TOKEN_DIR = Path("C:/Users/jroyp/Dropbox/API Keys")

# Reused client credentials (the GCP OAuth app, not a user-specific token)
DEFAULT_CLIENT_CREDS = (
    Path(__file__).parent.parent / "earnings_agent" / "gmail_client_credentials.json"
)


def token_path_for(account: str) -> Path:
    """Return the canonical path where this account's token lives."""
    return TOKEN_DIR / f"gmail_token_{account}.json"


def authorize_account(
    account: str,
    client_creds: Path | None = None,
    token_dir: Path | None = None,
) -> Path:
    """Run the OAuth consent flow for `account` and save the token.

    Returns the absolute path to the saved token.

    This launches an HTTP server on a free port, opens the user's
    browser to Google's OAuth consent screen, and waits for them to
    complete sign-in. Up to ~5 minutes for the user to consent.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    if client_creds is None:
        client_creds = DEFAULT_CLIENT_CREDS
    if not client_creds.exists():
        raise FileNotFoundError(
            f"Client credentials JSON not found at {client_creds}. "
            "Provide --client-credentials or ensure earnings_agent's "
            "credentials are in place."
        )
    if token_dir is None:
        token_dir = TOKEN_DIR
    token_dir.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_creds), SCOPES
    )

    print(
        f"\n[ ] About to open your browser for Google OAuth consent.\n"
        f"    When the consent screen appears, sign in as the *{account}* account\n"
        f"    and click 'Allow' to grant gmail.readonly access.\n"
        f"    (The browser will close itself when you're done.)\n"
    )

    # Opens browser; runs a local server; waits for the redirect.
    creds = flow.run_local_server(
        host="localhost",
        port=0,           # any free port
        open_browser=True,
        prompt="consent", # always show consent screen so we get refresh_token
    )

    # Save in the same format other projects use (authorized_user_info).
    out_path = token_path_for(account)
    out_path.write_text(creds.to_json(), encoding="utf-8")

    # Quick sanity check — make sure the token actually authenticated
    # the account the user expected.
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = svc.users().getProfile(userId="me").execute()
    actual = profile.get("emailAddress", "")

    print(f"\n[+] Token saved to: {out_path}")
    print(f"[+] Authenticated as: {actual}")

    expected_prefix = account.split("@")[0].lower()
    if expected_prefix not in actual.lower():
        print(
            f"\n[!] Warning: you signed in as {actual} but the account "
            f"argument was {account!r}. The token will still work for "
            f"{actual}, but the file is named for {account}. Rename it "
            f"if needed."
        )

    return out_path
