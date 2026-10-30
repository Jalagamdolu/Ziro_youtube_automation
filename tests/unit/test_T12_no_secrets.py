"""T12: no hard-coded keys in the repo, .env.example holds names only, logs redact secrets."""

import json
import re
from pathlib import Path

from app.core.log import bind_contextvars, clear_contextvars, log

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "runs", "node_modules", "__pycache__", ".mypy_cache"}
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"(?i)(api_key|secret|password|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
]


def _files() -> list[Path]:
    return [p for p in ROOT.rglob("*")
            if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts)
            and p.suffix in {".py", ".yaml", ".yml", ".toml", ".md", ".json", ".example", ""}]


def test_no_secrets_in_repo() -> None:
    hits = [f"{p.relative_to(ROOT)}: {pattern.pattern}" for p in _files()
            for pattern in SECRET_PATTERNS
            if pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert hits == []


def test_env_example_has_names_only() -> None:
    lines = (ROOT / ".env.example").read_text().splitlines()
    assignments = [line for line in lines if line and not line.startswith("#")]
    assert assignments and all(re.fullmatch(r"[A-Z_]+=", line) for line in assignments)


def test_logs_redact_secrets_and_carry_context(capsys) -> None:
    clear_contextvars()
    bind_contextvars(project_id="p1", stage="rendering", attempt=2)
    sample = "sample-value"
    log.info("calling provider", api_key=sample, authorization=sample)
    clear_contextvars()
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["api_key"] == line["authorization"] == "[redacted]"
    assert (line["project_id"], line["stage"], line["attempt"]) == ("p1", "rendering", 2)
