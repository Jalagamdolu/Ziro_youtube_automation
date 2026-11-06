"""The one-time YouTube authorization's local rules (D-67): only @Ziro.Digital, pinned by ID, and
the token written into .env without duplicates. No network calls."""

from app.api import youtube_auth


def channel(handle: str, channel_id: str = "UC123") -> dict:  # type: ignore[type-arg]
    return {"id": channel_id, "snippet": {"title": "Ziro", "customUrl": handle}}


def test_only_the_pinned_channel_matches() -> None:
    assert youtube_auth.matches(channel("@ziro.digital"), "@Ziro.Digital", "")  # first login
    assert youtube_auth.matches(channel("@ziro.digital"), "@Ziro.Digital", "UC123")
    assert not youtube_auth.matches(channel("@ziro.digital", "UC999"), "@Ziro.Digital", "UC123")
    assert not youtube_auth.matches(channel("@sometestchannel"), "@Ziro.Digital", "")
    assert not youtube_auth.matches({"id": "UC123", "snippet": {}}, "@Ziro.Digital", "")


def test_the_refresh_token_replaces_its_line_once() -> None:
    text = "A=1\nYT_REFRESH_TOKEN=\nB=2\n"
    once = youtube_auth.set_line(text, "YT_REFRESH_TOKEN", "tok")
    assert once == "A=1\nYT_REFRESH_TOKEN=tok\nB=2\n"
    assert youtube_auth.set_line(once, "YT_REFRESH_TOKEN", "new").count("YT_REFRESH_TOKEN") == 1
    assert youtube_auth.set_line("A=1", "YT_REFRESH_TOKEN", "tok") == "A=1\nYT_REFRESH_TOKEN=tok\n"
