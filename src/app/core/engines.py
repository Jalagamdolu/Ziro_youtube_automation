"""Which engines run, from mode + the keys present (D-46). Keys upgrade quality, never block: no
ANTHROPIC_API_KEY means the free-tier writers, no SARVAM_API_KEY means Kokoro. Logged at startup
and shown as banners in the UI. Names only, never values.
"""

import os
from typing import Any

from app.core import config

KEYS = ("ANTHROPIC_API_KEY", "SARVAM_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
        "TAVILY_API_KEY", "PIXABAY_API_KEY", "PEXELS_API_KEY")


def has(name: str) -> bool:
    return bool(os.environ.get(name))


def voice() -> str:
    return "sarvam" if config.load()["mode"] == "production" and has("SARVAM_API_KEY") \
        else "kokoro"


def status() -> dict[str, Any]:
    production = config.load()["mode"] == "production"
    writer = ("fixture" if not production else "claude" if has("ANTHROPIC_API_KEY")
              else "groq/gemini" if has("GROQ_API_KEY") or has("GEMINI_API_KEY") else "none")
    return {"mode": config.load()["mode"], "writer": writer, "voice": voice(),
            "keys": {name: has(name) for name in KEYS}}


def banners() -> list[str]:
    """One line per missing upgrade, for the top of every page."""
    found = status()
    lines = []
    if found["mode"] == "prototype":
        lines.append("Prototype mode: hand-written fixture scripts (Claude stand-in); only "
                     "fixture topics have content.")
    elif found["writer"] != "claude":
        lines.append("No ANTHROPIC_API_KEY: scripts are written by the fallback writers "
                     f"({found['writer']}). Add the key to .env and restart for Claude.")
    if found["voice"] == "kokoro":
        lines.append("No SARVAM_API_KEY: narration uses Kokoro (local voice). Add the key to "
                     ".env and restart for Sarvam." if found["mode"] == "production" else
                     "Narration uses Kokoro (local voice); Sarvam runs in production mode.")
    return lines
