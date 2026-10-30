"""D-06: publishing without an approved qa_review is impossible at runtime and for mypy."""

from pathlib import Path

import pytest
from conftest import reject, run_to_qa_review
from mypy import api as mypy_api

from app.adapters.publisher import ApprovedRun, approved_run
from app.core import db
from app.core.errors import FatalError

ROOT = Path(__file__).resolve().parents[2]


def test_approved_run_cannot_be_forged() -> None:
    with pytest.raises(TypeError):
        ApprovedRun("project", 1, object())


def test_no_qa_approval_means_no_approved_run(client) -> None:
    project_id = run_to_qa_review(client)
    with db.session() as s, pytest.raises(FatalError, match="not approved"):
        approved_run(s, project_id)

    reject(client, project_id, "rendering")
    with db.session() as s, pytest.raises(FatalError):
        approved_run(s, project_id)


def test_type_checker_rejects_publish_without_approved_run(tmp_path: Path) -> None:
    snippet = tmp_path / "bypass.py"
    snippet.write_text(
        "from sqlalchemy.orm import Session\n"
        "from app.adapters.publisher import MockPublisher\n"
        "def bypass(s: Session) -> None:\n"
        "    MockPublisher().publish(s, 'some-project-id', {})\n"
    )
    stdout, _, exit_code = mypy_api.run(
        ["--config-file", str(ROOT / "pyproject.toml"), str(snippet)])
    assert exit_code == 1
    assert 'incompatible type "str"; expected "ApprovedRun"' in stdout
