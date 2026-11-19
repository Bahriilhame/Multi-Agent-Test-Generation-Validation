"""Bounded LangGraph loop for arbitrary supported local projects."""

import json
from datetime import UTC, datetime
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from agents.generic_pipeline import (
    analyze_node,
    critic_node,
    execute_node,
    finalize_node,
    generate_node,
)
from graph.state import TestingState


def _safe(node):
    def wrapped(state):
        node_name = node.__name__.removesuffix("_node")
        event = {"timestamp": datetime.now(UTC).isoformat(), "node": node_name, "status": "started", "iteration": state.get("iteration", 0)}
        run_dir = state.get("run_dir")
        if run_dir:
            folder = Path(run_dir)
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            result = node(state)
            event.update({"timestamp": datetime.now(UTC).isoformat(), "status": "failed" if result.get("run_error") else "completed"})
            if run_dir:
                with (Path(run_dir) / "events.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            return result
        except Exception as error:  # noqa: BLE001 - each node failure is recorded and routed to finalize.
            message = f"{type(error).__name__}: {error}"
            event.update({"timestamp": datetime.now(UTC).isoformat(), "status": "failed", "error": message})
            if run_dir:
                with (Path(run_dir) / "events.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            return {"run_error": message, "errors": [*state.get("errors", []), message], "stage": "error"}
    return wrapped


def _after(state):
    return "finalize" if state.get("run_error") or state.get("coverage_saturated") else "generator"


def _retry_or_finish(state):
    if state.get("run_error") or state.get("accepted"):
        return "finalize"
    if int(state.get("iteration", 0)) + 1 < max(1, int(state.get("max_iterations", 2))):
        return "retry"
    return "finalize"


def _increment(state):
    iteration = int(state.get("iteration", 0))
    run_dir = state.get("run_dir")
    if run_dir:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "node": "retry",
            "status": "completed",
            "iteration": iteration,
        }
        with (Path(run_dir) / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"iteration": iteration + 1, "stage": "retrying"}


def build_generic_workflow():
    graph = StateGraph(TestingState)
    graph.add_node("analyze", _safe(analyze_node))
    graph.add_node("generator", _safe(generate_node))
    graph.add_node("validation", _safe(execute_node))
    graph.add_node("critic", _safe(critic_node))
    graph.add_node("retry", _increment)
    graph.add_node("finalize", _safe(finalize_node))
    graph.add_edge(START, "analyze")
    graph.add_conditional_edges("analyze", _after, {"finalize": "finalize", "generator": "generator"})
    graph.add_conditional_edges("generator", lambda s: "finalize" if s.get("run_error") else "validation", {"finalize": "finalize", "validation": "validation"})
    graph.add_conditional_edges("validation", lambda s: "finalize" if s.get("run_error") else "critic", {"finalize": "finalize", "critic": "critic"})
    graph.add_conditional_edges("critic", _retry_or_finish, {"finalize": "finalize", "retry": "retry"})
    graph.add_edge("retry", "generator")
    graph.add_edge("finalize", END)
    return graph.compile()
