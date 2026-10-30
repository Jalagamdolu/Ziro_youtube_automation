"""Wrappers around the vendored skill-pack tools (D-09): run by path, never imported or edited."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SKILLS = Path(__file__).resolve().parents[2] / "vendor" / "youtube-agent-skill" / "skills"


def score_hooks(hooks: list[str]) -> list[dict[str, Any]]:
    """hookscore.py --json: per hook its properties, verdict, band and formula; best first."""
    return _run_on_lines(SKILLS / "yt-script" / "hookscore.py", hooks)


def lint_titles(titles: list[str], thumbnail_text: str) -> list[dict[str, Any]]:
    """title.py --json against the thumbnail text: per title its score and issues; best first."""
    return _run_on_lines(SKILLS / "yt-package" / "title.py", titles, "--thumb", thumbnail_text)


def _run_on_lines(tool: Path, lines: list[str], *args: str) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write("\n".join(lines) + "\n")
    try:
        done = subprocess.run([sys.executable, "-I", str(tool), f.name, *args, "--json"],
                              capture_output=True, text=True, check=True, timeout=60)
    finally:
        Path(f.name).unlink()
    result: list[dict[str, Any]] = json.loads(done.stdout)
    return result
