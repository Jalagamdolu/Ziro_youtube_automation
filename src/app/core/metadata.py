"""A finished video's title, description and hashtags as they will be published (D-69): the
writer's package until the reviewer edits them on the Library card; an edit is a new versioned
artifact (stage "library") and an audit row. Editable only before the upload."""

import hashlib
import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters import storage
from app.core import audit, db
from app.core.models import Artifact, Project

NAME = "metadata.json"
EDITABLE = ("export_ready",)  # Ready or Scheduled, not uploaded yet


def edited(s: Session, project_id: str) -> dict[str, Any] | None:
    key = s.scalars(select(Artifact.storage_path).where(
        Artifact.project_id == project_id, Artifact.type == NAME, Artifact.stale.is_(False))
        .order_by(Artifact.version.desc())).first()
    return json.loads(storage.get().read(key)) if key else None


def current(s: Session, project_id: str) -> dict[str, Any]:
    """What would be published now: the reviewer's edit, else the writer's package."""
    mine = edited(s, project_id)
    if mine is not None:
        return mine
    key = s.scalars(select(Artifact.storage_path).where(
        Artifact.project_id == project_id, Artifact.type == "content_package.json",
        Artifact.stale.is_(False)).order_by(Artifact.version.desc())).first()
    if key is None:
        return {"title": s.get_one(Project, project_id).topic, "description": "", "tags": []}
    package = json.loads(storage.get().read(key))
    return {"title": package["top_titles"][0], "description": package["description"],
            "tags": package["tags"]}


def hashtags(text: str) -> list[str]:
    """'#ai, rag  #LLM' -> ['ai', 'rag', 'LLM']: words without the #, no duplicates."""
    words = [w.lstrip("#") for w in re.split(r"[\s,]+", text) if w.lstrip("#")]
    return list(dict.fromkeys(words))


def save(project_id: str, title: str, description: str, tags: list[str], actor: str) -> None:
    if not title.strip():
        raise ValueError("a title is required")
    if len(title) > 100:
        raise ValueError("YouTube titles are at most 100 characters")
    data = json.dumps({"title": title.strip(), "description": description.strip(),
                       "tags": tags}, indent=2, ensure_ascii=False).encode()
    with db.session() as s, s.begin():
        if s.get_one(Project, project_id).status not in EDITABLE:
            raise ValueError("only a video that is not uploaded yet can be edited")
        version = (s.scalar(select(func.max(Artifact.version)).where(
            Artifact.project_id == project_id, Artifact.type == NAME)) or 0) + 1
        key = storage.get().write(f"{project_id}/library/v{version}/{NAME}", data)
        s.add(Artifact(project_id=project_id, stage="library", type=NAME, version=version,
                       storage_path=key, checksum=hashlib.sha256(data).hexdigest(),
                       model_or_tool="reviewer"))
        audit.action(s, project_id, actor, f"edited title/description/hashtags (v{version})")
