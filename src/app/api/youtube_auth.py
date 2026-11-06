"""One-time YouTube authorization (D-67): `make youtube-auth`, run on the host.

Sir logs in to @Ziro.Digital's Google account and clicks Allow; that consent is the founder
sign-off. The refresh token goes into .env (never printed) and the channel's ID is pinned in
config only if the authorized channel is the configured handle; any other channel's token is
revoked and nothing is saved. Standard library only, so it runs outside the containers where the
browser's redirect to 127.0.0.1 can reach it. Publishing stays mock (MockPublisher) regardless.
"""

import base64
import hashlib
import json
import re
import secrets
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
ENV, CONFIG = ROOT / ".env", ROOT / "src" / "config.yaml"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]  # readonly: the channel check
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"


def read_env() -> dict[str, str]:
    found = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)", line):
            found[m.group(1)] = m.group(2).strip().strip("\"'")
    return found


def set_line(text: str, name: str, value: str) -> str:
    """Replace `name=...` in .env-style text, or append it."""
    line = f"{name}={value}"
    if re.search(rf"(?m)^{name}=.*$", text):
        return re.sub(rf"(?m)^{name}=.*$", lambda _: line, text)
    return text.rstrip("\n") + f"\n{line}\n"


def pinned() -> tuple[str, str]:
    """(handle, channel_id) from config's youtube block."""
    text = CONFIG.read_text(encoding="utf-8")
    handle = re.search(r'(?m)^  channel_handle: "([^"]*)"', text)
    channel = re.search(r'(?m)^  channel_id: "([^"]*)"', text)
    if handle is None or channel is None:
        sys.exit("config.yaml has no youtube.channel_handle / channel_id")
    return handle.group(1), channel.group(1)


def matches(channel: dict[str, Any], handle: str, channel_id: str) -> bool:
    """The authorized channel is the one allowed target: same handle, and same ID once pinned.
    The adapter repeats this before every publish."""
    same_handle = channel["snippet"].get("customUrl", "").lower() == handle.lower()
    return same_handle and (not channel_id or channel["id"] == channel_id)


def _post(url: str, fields: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as reply:
        body = reply.read()
    return json.loads(body) if body else {}


def own_channel(access_token: str) -> dict[str, Any]:
    request = urllib.request.Request(CHANNELS_URL,
                                     headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(request, timeout=30) as reply:
        items: list[dict[str, Any]] = json.loads(reply.read()).get("items", [])
    if len(items) != 1:
        raise SystemExit(f"the account has {len(items)} YouTube channels; expected exactly one")
    return items[0]


def _code(client_id: str) -> tuple[str, str, str]:
    """Print the consent URL, wait for Google's redirect; returns (code, redirect, verifier)."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server's name)
            got.update(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

        def log_message(self, *args: Any) -> None:  # keep the code out of the terminal
            pass

    server = HTTPServer(("127.0.0.1", 0), Redirect)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge.decode(), "code_challenge_method": "S256", "state": state})
    print("\nOpen this link, log in with the @Ziro.Digital Google account, and click Allow:\n")
    print(url + "\n", flush=True)
    while "code" not in got and "error" not in got:
        server.handle_request()
    server.server_close()
    if got.get("error") or got.get("state") != state:
        raise SystemExit(f"authorization not completed: {got.get('error', 'state mismatch')}")
    return got["code"], redirect, verifier


def main() -> None:
    env = read_env()
    client_id, secret = env.get("YT_CLIENT_ID", ""), env.get("YT_CLIENT_SECRET", "")
    if not client_id or not secret:
        sys.exit("YT_CLIENT_ID and YT_CLIENT_SECRET must both be set in .env")
    if client_id.startswith("AIza") or secret.startswith("AIza"):
        sys.exit("that is an API key, not an OAuth client: create a Desktop app OAuth client")
    handle, channel_id = pinned()
    code, redirect, verifier = _code(client_id)
    tokens = _post(TOKEN_URL, {"code": code, "client_id": client_id, "client_secret": secret,
                           "redirect_uri": redirect, "grant_type": "authorization_code",
                           "code_verifier": verifier})
    refresh = tokens.get("refresh_token")
    granted = set(tokens.get("scope", "").split())
    if not refresh or not set(SCOPES) <= granted:
        sys.exit("Google returned no refresh token or not both scopes; run it again and tick both")
    channel = own_channel(tokens["access_token"])
    if not matches(channel, handle, channel_id):
        _post(REVOKE_URL, {"token": refresh})  # never keep a credential for another channel
        sys.exit(f"wrong channel: authorized {channel['snippet'].get('customUrl')!r}, allowed "
                 f"only {handle}. The token was revoked and nothing was saved.")
    ENV.write_text(set_line(ENV.read_text(encoding="utf-8"), "YT_REFRESH_TOKEN", refresh),
                   encoding="utf-8", newline="\n")
    text = CONFIG.read_text(encoding="utf-8")
    CONFIG.write_text(re.sub(r'(?m)^  channel_id: "[^"]*"', f'  channel_id: "{channel["id"]}"',
                             text), encoding="utf-8", newline="\n")
    print(f"YouTube credential ready for channel {channel['snippet']['title']} "
          f"({channel['snippet'].get('customUrl')}, {channel['id']})")


if __name__ == "__main__":
    main()
