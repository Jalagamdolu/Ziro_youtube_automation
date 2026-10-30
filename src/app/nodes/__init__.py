from collections.abc import Callable

from app.nodes import stubs
from app.nodes.researching import researching
from app.nodes.scripting import scripting
from app.nodes.context import Outputs, StageContext

# Stage name -> implementation. Looked up at call time, so tests can swap entries to inject faults.
FUNCS: dict[str, Callable[[StageContext], Outputs]] = {
    "draft": stubs.draft,
    "researching": researching,
    "scripting": scripting,
    "storyboarding": stubs.storyboarding,
    "rendering": stubs.rendering,
    "export_ready": stubs.export_ready,
    "mock_published": stubs.mock_published,
    "metrics_stub": stubs.metrics_stub,
}
