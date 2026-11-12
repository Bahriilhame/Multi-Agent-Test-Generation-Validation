from swebench_testgen.dataset import AGENT_FIELDS, FORBIDDEN_AGENT_FIELDS, project_agent_task
from swebench_testgen.graph import build_foundation_graph


def test_dataset_projection_never_exposes_reference_patch_or_tests():
    row = {key: "value" for key in AGENT_FIELDS}
    row.update({key: "secret reference" for key in FORBIDDEN_AGENT_FIELDS})
    task = project_agent_task(row)
    assert set(task) == AGENT_FIELDS
    assert not (set(task) & FORBIDDEN_AGENT_FIELDS)


def test_graph_initializes_shared_state():
    result = build_foundation_graph().invoke({
        "task": {key: "x" for key in AGENT_FIELDS},
        "workspace_path": ".",
        "iteration": 0,
        "status": "ready",
    })
    assert result["iteration"] == 0
    assert result["status"] == "ready"

