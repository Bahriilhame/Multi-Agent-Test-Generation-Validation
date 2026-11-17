
from langgraph.graph import StateGraph, START, END

from graph.state import TestingState

from agents.coverage_agent import coverage_agent
from agents.test_generator_agent import test_generator_agent
from agents.validation_agent import validation_agent
from agents.relevance_critic_agent import relevance_critic_agent
from experiments.tracking import finalize_run


def finalize_node(state):
    status = state.get("validation_status", "completed")
    finalize_run(state, status=status)
    return {}


def build_workflow():

    graph = StateGraph(TestingState)

    # Déclaration des agents
    graph.add_node("coverage", coverage_agent)
    graph.add_node("generator", test_generator_agent)
    graph.add_node("validation", validation_agent)
    graph.add_node("critic", relevance_critic_agent)
    graph.add_node("finalize", finalize_node)

    # Connexion des agents
    graph.add_edge(START, "coverage")
    graph.add_edge("coverage", "generator")
    graph.add_edge("generator", "validation")
    graph.add_edge("validation", "critic")
    graph.add_edge("critic", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
