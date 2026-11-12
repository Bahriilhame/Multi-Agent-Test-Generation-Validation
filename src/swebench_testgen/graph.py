"""Minimal LangGraph skeleton; agent implementation is intentionally deferred."""

from langgraph.graph import END, START, StateGraph

from .state import WorkflowState


def _initialize(state: WorkflowState) -> dict[str, object]:
    return {"iteration": state.get("iteration", 0), "status": "ready"}


def build_foundation_graph():
    """Compile a minimal graph to validate state and orchestration dependency."""
    graph = StateGraph(WorkflowState)
    graph.add_node("initialize", _initialize)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", END)
    return graph.compile()

