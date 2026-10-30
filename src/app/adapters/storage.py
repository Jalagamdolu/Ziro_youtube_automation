"""Storage adapter. Local directory now; a sandbox bucket implements the same Protocol later (§9).

Keys are relative paths such as "<project_id>/<stage>/v<n>/<file>".
"""

from pathlib import Path
from typing import Protocol

from app.core import config


class Storage(Protocol):
    def write(self, key: str, data: bytes) -> str: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


def get() -> Storage:
    return LocalStorage(config.runs_dir())
