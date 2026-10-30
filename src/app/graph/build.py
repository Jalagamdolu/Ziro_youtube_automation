from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core import config, retry
from app.graph.gates import gate_node
from app.graph.stages import GATES, WORK
from app.graph.state import State
from app.nodes.runner import run_stage

# Fixed edges; gates route themselves with Command(goto=...).
EDGES = [
    (START, "draft"),
    ("draft", "researching"),
    ("researching", "research_review"),
    ("scripting", "script_review"),
    ("storyboarding", "rendering"),
    ("rendering", "qa_review"),
    ("export_ready", "mock_published"),
    ("mock_published", "metrics_stub"),
    ("metrics_stub", END),
]


def build(checkpointer: PostgresSaver) -> CompiledStateGraph[Any, Any, Any, Any]:
    cfg = config.load()
    graph = StateGraph(State)
    for stage in WORK:
        graph.add_node(stage, _work_node(stage), retry_policy=retry.policy(stage, cfg))
    for gate in GATES:
        graph.add_node(gate, gate_node(gate))
    for source, target in EDGES:
        graph.add_edge(source, target)
    return graph.compile(checkpointer=checkpointer)


def _work_node(stage: str) -> Callable[..., Any]:
    def node(state: State) -> dict[str, Any]:
        return run_stage(stage, state)

    return node


@contextmanager
def checkpointer() -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(config.database_url()) as saver:
        yield saver


def setup_checkpoints() -> None:
    with checkpointer() as saver:
        saver.setup()


if __name__ == "__main__":
    setup_checkpoints()
