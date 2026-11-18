import json
import subprocess
import zipfile

import pytest

from adapters.input_sources import materialize_source
from agents.generic_pipeline import _extract_code
from experiments.review_project_run import review as review_project_run
from graph import generic_workflow
from sandbox.generic_runner import _failure_details, _summary_count, run_in_docker
from tools import ollama_json
from tools.critic_schema import validate_critic_response
from ui.live_status import read_events, summarize_events


def test_generated_test_code_requires_assertive_pytest_function():
    assert "test_value" in _extract_code("```python\ndef test_value():\n    assert 2 == 2\n```")
    with pytest.raises(ValueError, match="no pytest"):
        _extract_code("def helper():\n    return 1")


def test_generated_test_code_rejects_process_and_network_imports():
    with pytest.raises(ValueError, match="Forbidden generated test import"):
        _extract_code("import subprocess\ndef test_x():\n    assert True")
    with pytest.raises(ValueError, match="Forbidden generated code call"):
        _extract_code("def test_x():\n    eval('1')\n    assert True")
    with pytest.raises(ValueError, match="Forbidden generated test import"):
        _extract_code("import os\ndef test_x():\n    assert True")
    assert "service.run()" in _extract_code("def test_service(service):\n    assert service.run() == 'ok'")


def test_runner_parses_pytest_counts_and_failure_details():
    output = "1 failed, 2 passed, 1 error in 0.1s\n========== FAILURES ==========\nfailed assertion\n========== tests coverage ==========\n"
    assert _summary_count(output, "passed") == 2
    assert _summary_count(output, "failed") == 1
    assert _summary_count(output, "error") == 1
    assert "failed assertion" in _failure_details(output)


def test_live_status_summarizes_running_and_completed_steps(tmp_path):
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(
        '\n'.join([
            json.dumps({"node": "analyze", "status": "started", "iteration": 0, "timestamp": "t1"}),
            json.dumps({"node": "analyze", "status": "completed", "iteration": 0, "timestamp": "t2"}),
            json.dumps({"node": "generator", "status": "started", "iteration": 1, "timestamp": "t3"}),
            '{"node":"critic","status":',
        ]),
        encoding="utf-8",
    )
    steps = summarize_events(read_events(event_path))
    assert [(step["node"], step["status"]) for step in steps] == [
        ("analyze", "completed"),
        ("generator", "running"),
    ]
    assert steps[0]["finished_at"] == "t2"


def test_critic_schema_requires_consistent_score_and_grounds_issues():
    test_source = "def test_value():\n    assert value() == 4\n"
    response = json.dumps({
        "score": 88,
        "dimensions": {"contract": 24, "assertions": 24, "edge_cases": 20, "independence": 20},
        "issues": [{"test_name": "test_value", "severity": "major", "evidence": "assert value() == 4", "reason": "Expected value is wrong", "suggestion": "Use the contract value"}],
        "summary": "One issue",
    })
    parsed = validate_critic_response(response, test_source)
    assert parsed["score"] == 88
    assert len(parsed["issues"]) == 1
    unsupported = json.loads(response)
    unsupported["issues"][0]["evidence"] = "not present"
    parsed = validate_critic_response(json.dumps(unsupported), test_source)
    assert parsed["issues"] == []
    assert len(parsed["unsupported_issues"]) == 1
    unsupported["score"] = 20
    with pytest.raises(ValueError, match="sum of its dimensions"):
        validate_critic_response(json.dumps(unsupported), test_source)


def test_critic_rejects_false_claim_about_explicit_value_error_assertion():
    test_source = "import pytest\ndef test_rejects_invalid():\n    with pytest.raises(ValueError):\n        clamp(5, 10, 3)\n"
    response = json.dumps({
        "score": 18,
        "dimensions": {"contract": 10, "assertions": 6, "edge_cases": 2, "independence": 0},
        "issues": [{"test_name": "test_rejects_invalid", "severity": "major", "evidence": "clamp(5, 10, 3)", "reason": "The test does not verify that function raises a ValueError.", "suggestion": "Add an exception assertion."}],
        "summary": "The exception check is absent.",
    })
    parsed = validate_critic_response(response, test_source)
    assert parsed["issues"] == []
    assert len(parsed["unsupported_issues"]) == 1


def test_ollama_json_client_requests_native_json_response_mode(monkeypatch):
    calls = {}

    def fake_chat_ollama(**kwargs):
        calls.update(kwargs)
        return object()

    monkeypatch.setattr(ollama_json, "ChatOllama", fake_chat_ollama)
    ollama_json.get_json_llm()
    assert calls["format"] == "json"


def test_saved_run_critic_replay_recomputes_acceptance(tmp_path):
    run_dir = tmp_path / "run"
    tests_dir = run_dir / "generated_tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_generated.py").write_text("def test_answer():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    report = {"iterations": 1, "coverage_before": 50, "coverage_after": 100, "execution": {"exit_code": 0, "generated_passed": 1, "generated_failed": 0}}
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    response = run_dir / "critic_response_iteration-0.txt"
    response.write_text(json.dumps({
        "score": 80,
        "dimensions": {"contract": 20, "assertions": 20, "edge_cases": 20, "independence": 20},
        "issues": [], "summary": "Tests are sound.",
    }), encoding="utf-8")
    replay = review_project_run(run_dir, None, 70)
    assert replay["result"]["status"] == "accepted"
    assert replay["path"].is_file()


def test_zip_materialization_rejects_parent_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("../escaped.py", "bad = True")
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        materialize_source(archive, tmp_path / "extract")
    assert not (tmp_path / "escaped.py").exists()


def test_git_source_rejects_embedded_credentials(tmp_path):
    with pytest.raises(ValueError, match="cannot embed"):
        materialize_source("https://user:secret@example.com/org/repo.git", tmp_path / "clone")
    assert not (tmp_path / "clone").exists()


def test_zip_materialization_unpacks_safe_project(tmp_path):
    archive = tmp_path / "project.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("sample/src/app.py", "def run(): return 1")
    root, source_kind = materialize_source(archive, tmp_path / "extract")
    assert source_kind == "zip"
    assert (root / "src" / "app.py").is_file()


def test_langgraph_retries_then_accepts_with_iteration_bound(tmp_path, monkeypatch):
    counts = {"generate": 0, "execute": 0, "critic": 0}

    def analyze(_state):
        return {"coverage_before": 50}

    def generate(_state):
        counts["generate"] += 1
        return {"generated_tests": f"iteration {counts['generate']}"}

    def execute(_state):
        counts["execute"] += 1
        return {"execution_result": {"exit_code": 0}}

    def critic(_state):
        counts["critic"] += 1
        return {"accepted": counts["critic"] == 2, "critic_feedback": "repair"}

    def finalize(_state):
        return {"stage": "completed"}

    monkeypatch.setattr(generic_workflow, "analyze_node", analyze)
    monkeypatch.setattr(generic_workflow, "generate_node", generate)
    monkeypatch.setattr(generic_workflow, "execute_node", execute)
    monkeypatch.setattr(generic_workflow, "critic_node", critic)
    monkeypatch.setattr(generic_workflow, "finalize_node", finalize)
    result = generic_workflow.build_generic_workflow().invoke({
        "project_path": str(tmp_path), "run_dir": str(tmp_path / "run"), "iteration": 0, "max_iterations": 2,
    })
    assert counts == {"generate": 2, "execute": 2, "critic": 2}
    assert result["accepted"] is True
    assert result["iteration"] == 1


def test_docker_runner_stages_tests_and_enforces_container_policy(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text("from app import add\ndef test_add(): assert add(1, 2) == 3\n", encoding="utf-8")
    (project / ".env").write_text("SECRET=hidden\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "build"]:
            return subprocess.CompletedProcess(command, 0, "built", "")
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "image", "")
        if command[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        assert command[:2] == ["docker", "run"]
        return subprocess.CompletedProcess(command, 0, "2 passed in 0.1s", "")

    monkeypatch.setattr("sandbox.generic_runner.subprocess.run", fake_run)
    run_dir = tmp_path / "run"
    result = run_in_docker(project, run_dir, "def test_generated():\n    assert True\n")

    staged = run_dir / "runtime" / "app"
    assert (staged / "smarttest_generated" / "test_generated.py").is_file()
    assert not (staged / ".env").exists()
    docker_run = next(call for call in calls if len(call) > 1 and call[1] == "run")
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "--cpus", "--pids-limit", "--user"):
        assert flag in docker_run
    assert result["exit_code"] == 0
    assert result["container_policy"]["network"] == "none"
