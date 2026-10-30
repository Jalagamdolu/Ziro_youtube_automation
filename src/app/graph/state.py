from typing import Annotated, TypedDict


def _merge(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    return {**old, **new}


class State(TypedDict):
    """Small graph state: paths, never blobs (§3)."""

    project_id: str
    artifacts: Annotated[dict[str, str], _merge]  # stage -> storage prefix "<id>/<stage>/v<n>"
    review_notes: Annotated[dict[str, str], _merge]  # target stage -> reviewer notes
    status: str
