from collections.abc import Callable

from app.nodes import stubs
from app.nodes.context import StageContext

# Stage name -> implementation. Looked up at call time, so tests can swap entries to inject faults.
FUNCS: dict[str, Callable[[StageContext], stubs.Outputs]] = {
    "draft": stubs.draft,
    "researching": stubs.researching,
    "scripting": stubs.scripting,
    "storyboarding": stubs.storyboarding,
    "rendering": stubs.rendering,
    "export_ready": stubs.export_ready,
    "mock_published": stubs.mock_published,
    "metrics_stub": stubs.metrics_stub,
}
