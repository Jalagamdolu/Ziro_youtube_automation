import json
from dataclasses import dataclass
from typing import Any

from app.adapters.storage import Storage


@dataclass(frozen=True)
class StageContext:
    """A stage function's input: its project, upstream artifact prefixes and reviewer notes."""

    project_id: str
    inputs: dict[str, str]
    notes: str | None
    storage: Storage

    def read_json(self, stage: str, name: str) -> Any:
        return json.loads(self.storage.read(f"{self.inputs[stage]}/{name}"))

    def read_text(self, stage: str, name: str) -> str:
        return self.storage.read(f"{self.inputs[stage]}/{name}").decode("utf-8")
