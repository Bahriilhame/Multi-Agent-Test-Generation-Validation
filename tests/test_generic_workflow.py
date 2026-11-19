import json
import subprocess
import zipfile

import pytest

from adapters.base import ProjectInfo
from adapters.input_sources import materialize_source
from agents.generic_pipeline import (
    _coverage_is_saturated,
    _extract_code,
    _failure_repair_context,
    _merge_retry_tests,
    analyze_node,
    critic_node,
    finalize_node,
)
from experiments.review_project_run import review as review_project_run
from graph import generic_workflow
from sandbox.dependency_image import build_project_image
from sandbox.generic_runner import (
    _failure_details,
    _summary_count,
    run_in_docker,
    summarize_failure_details,
)
from tools import ollama_json
from tools.critic_schema import validate_critic_response
from tools.prompt_templates import build_generic_generation_prompt
from ui.live_status import read_events, summarize_events


def test_generated_test_code_requires_assertive_pytest_function():
    assert "test_value" in _extract_code("```python\ndef test_value():\n    assert 2 == 2\n```")
    with pytest.raises(ValueError, match="no pytest"):
        _extract_code("def helper():\n    return 1")
    filtered = _extract_code(
        "def test_existing():\n    assert True\n\ndef test_new():\n    assert 1 + 1 == 2\n",
        ["test_existing"],
    )
    assert "def test_existing" not in filtered
    assert "def test_new" in filtered


def test_generated_test_code_adds_import_for_project_symbol_used_in_fixture(tmp_path):
    (tmp_path / "config.py").write_text("class TestConfig:\n    TESTING = True\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("def create_app(config):\n    return config\n", encoding="utf-8")
    code = _extract_code(
        "import pytest\n"
        "@pytest.fixture\n"
        "def client():\n    return create_app(TestConfig)\n"
        "def test_client(client):\n    assert client is not None\n",
        project_root=tmp_path,
    )
    assert "from config import TestConfig" in code


def test_generation_prompt_stays_within_small_model_context_budget():
    prompt = build_generic_generation_prompt(
        source="def calculate(value):\n    return value + 1\n" * 500,
        uncovered=[
            {
                "file": f"module_{index}.py",
                "missing_lines": list(range(1, 200)),
                "missing_branches": list(range(1, 100)),
                "functions": [{"name": "calculate", "missing_lines": list(range(1, 100)), "missing_branches": list(range(1, 30))}],
            }
            for index in range(100)
        ],
        existing_tests="def test_existing():\n    assert True\n" * 1000,
        existing_test_names=["test_existing"],
        feedback="NameError: TestConfig is not defined\n" + "feedback " * 1000,
        task_context="context " * 1000,
    )
    assert len(prompt) < 7_000
    assert "module_0.py" in prompt
    assert "test_existing" in prompt
    assert "NameError: TestConfig is not defined" in prompt


def test_critic_skips_llm_when_pytest_already_failed(monkeypatch):
    def unexpected_llm_call(*_args, **_kwargs):
        raise AssertionError("Semantic review should be skipped after objective failures")

    monkeypatch.setattr("agents.generic_pipeline.ask_llm_json", unexpected_llm_call)
    result = critic_node({
        "generated_tests": "def test_bad():\n    assert 1 == 2\n",
        "execution_result": {"exit_code": 1, "failed": 1, "errors": 0, "generated_failed": 1, "failure_details": "assertion failed"},
        "coverage_before": 10,
        "coverage_after": 10,
    })
    assert result["accepted"] is False
    assert result["critic_result"]["heuristic_score"] <= 49
    assert result["critic_result"]["raw_heuristic_score"] > 49
    assert "Skipped semantic review" in result["critic_result"]["method"]


def test_critic_requires_real_coverage_gain_when_uncovered_code_remains(monkeypatch):
    response = json.dumps({
        "score": 100,
        "dimensions": {"contract": 25, "assertions": 25, "edge_cases": 25, "independence": 25},
        "issues": [],
        "summary": "Sound focused test.",
    })
    monkeypatch.setattr("agents.generic_pipeline.ask_llm_json", lambda *_args, **_kwargs: response)
    state = {
        "generated_tests": "def test_value():\n    assert 2 + 2 == 4\n",
        "execution_result": {"exit_code": 0, "passed": 1, "failed": 0, "errors": 0, "generated_passed": 1, "generated_failed": 0},
        "coverage_before": 50,
        "coverage_after": 50,
        "branch_coverage_before": 40,
        "branch_coverage_after": 40,
        "coverage_available": True,
        "coverage_saturated": False,
        "min_quality_score": 70,
    }
    result = critic_node(state)
    assert result["accepted"] is False
    assert result["critic_result"]["coverage_status"] == "no_improvement"
    assert any("Coverage did not increase" in item for item in result["critic_result"]["feedback"])


def test_critic_accepts_passing_tests_that_raise_line_or_branch_coverage(monkeypatch):
    response = json.dumps({
        "score": 100,
        "dimensions": {"contract": 25, "assertions": 25, "edge_cases": 25, "independence": 25},
        "issues": [],
        "summary": "Sound focused test.",
    })
    monkeypatch.setattr("agents.generic_pipeline.ask_llm_json", lambda *_args, **_kwargs: response)
    result = critic_node({
        "generated_tests": "def test_value():\n    assert 2 + 2 == 4\n",
        "execution_result": {"exit_code": 0, "passed": 1, "failed": 0, "errors": 0, "generated_passed": 1, "generated_failed": 0},
        "coverage_before": 50,
        "coverage_after": 60,
        "branch_coverage_before": 40,
        "branch_coverage_after": 40,
        "coverage_available": True,
        "coverage_saturated": False,
        "min_quality_score": 70,
    })
    assert result["accepted"] is True
    assert result["critic_result"]["coverage_status"] == "improved"
    assert result["best_candidate"]["coverage_after"] == 60


def test_critic_findings_block_acceptance_and_target_the_next_iteration(monkeypatch):
    response = json.dumps({
        "score": 90,
        "dimensions": {"contract": 25, "assertions": 25, "edge_cases": 20, "independence": 20},
        "issues": [{
            "test_name": "test_value",
            "severity": "major",
            "evidence": "assert value() == 3",
            "reason": "Expected value contradicts the source contract.",
            "suggestion": "Assert the documented value instead.",
        }],
        "summary": "Correct the expected value.",
    })
    monkeypatch.setattr("agents.generic_pipeline.ask_llm_json", lambda *_args, **_kwargs: response)
    result = critic_node({
        "generated_tests": "def test_value():\n    assert value() == 3\n",
        "execution_result": {"exit_code": 0, "passed": 1, "failed": 0, "errors": 0, "generated_passed": 1, "generated_failed": 0},
        "coverage_available": False,
        "min_quality_score": 70,
    })
    assert result["accepted"] is False
    assert result["critic_repair_targets"] == ["test_value"]
    assert "Expected value contradicts" in result["critic_feedback"]


def test_full_coverage_report_skips_generation_as_already_complete(tmp_path):
    result = finalize_node({
        "run_dir": str(tmp_path),
        "coverage_before": 100,
        "branch_coverage_before": 100,
        "coverage_saturated": True,
        "coverage_available": True,
        "iteration": 0,
    })
    assert result["final_report"]["status"] == "coverage_complete"
    assert result["final_report"]["coverage_goal"]["status"] == "already_complete"
    assert result["final_report"]["iterations"] == 0


def test_coverage_saturation_requires_line_and_branch_completion():
    coverage = {"totals": {"num_statements": 10, "percent_covered": 100, "num_branches": 4, "percent_branches_covered": 100}}
    assert _coverage_is_saturated(coverage, 0)
    coverage["totals"]["percent_branches_covered"] = 75
    assert not _coverage_is_saturated(coverage, 0)
    assert not _coverage_is_saturated(coverage, 1)


def test_analysis_stops_early_when_runner_image_lacks_project_dependencies(tmp_path, monkeypatch):
    info = ProjectInfo(
        root=str(tmp_path), name="sample", languages=["Python"],
        supported=True, adapter="python",
    )
    monkeypatch.setattr("agents.generic_pipeline.detect_project", lambda _root: info)
    monkeypatch.setattr("agents.generic_pipeline.ensure_runner_image", lambda: None)
    built = {}
    monkeypatch.setattr(
        "agents.generic_pipeline.build_project_image",
        lambda *_args, **_kwargs: (built.setdefault("image", "smarttest-project:test") or "smarttest-project:test", ["flask_sqlalchemy"]),
    )
    monkeypatch.setattr(
        "agents.generic_pipeline.run_in_docker",
        lambda *_args, **_kwargs: {"missing_dependencies": ["flask_sqlalchemy"]},
    )
    with pytest.raises(RuntimeError, match="Dependencies still missing"):
        analyze_node({"project_path": str(tmp_path), "run_dir": str(tmp_path / "run"), "docker_image": "auto"})
    assert built["image"] == "smarttest-project:test"


def test_project_image_auto_installs_declared_and_detected_dependencies(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("Flask>=3\n", encoding="utf-8")
    (project / "app.py").write_text("from flask_sqlalchemy import SQLAlchemy\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        if command[:2] == ["docker", "build"]:
            return subprocess.CompletedProcess(command, 0, "built", "")
        raise AssertionError(command)

    monkeypatch.setattr("sandbox.dependency_image.subprocess.run", fake_run)
    image, inferred = build_project_image(project, tmp_path / "run")
    assert image.startswith("smarttest-project:")
    assert "flask_sqlalchemy" in inferred
    context = tmp_path / "run" / "runtime" / "image-build"
    assert "Flask>=3" in (context / "requirements.txt").read_text(encoding="utf-8")
    assert "Flask-SQLAlchemy" in (context / "requirements-auto.txt").read_text(encoding="utf-8")
    dockerfile = (context / "Dockerfile").read_text(encoding="utf-8")
    assert "USER tester" in dockerfile
    assert "--target=/opt/project-dependencies" in dockerfile
    assert "PYTHONPATH=/opt/project-dependencies:/app" in dockerfile
    assert "COPY --chown=tester:tester" in dockerfile
    assert len(calls) == 2


def test_analysis_passes_existing_test_names_without_copying_test_bodies(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "def test_existing_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    info = ProjectInfo(
        root=str(tmp_path), name="sample", languages=["Python"],
        source_files=["app.py"], test_files=["test_app.py"], supported=True, adapter="python",
    )
    monkeypatch.setattr("agents.generic_pipeline.detect_project", lambda _root: info)
    monkeypatch.setattr("agents.generic_pipeline.ensure_runner_image", lambda: None)
    monkeypatch.setattr("agents.generic_pipeline.build_project_image", lambda *_args, **_kwargs: ("smarttest-project:test", []))
    monkeypatch.setattr(
        "agents.generic_pipeline.run_in_docker",
        lambda *_args, **_kwargs: {"missing_dependencies": [], "coverage": {"totals": {}, "files": {}}},
    )
    result = analyze_node({"project_path": str(tmp_path), "run_dir": str(tmp_path / "run")})
    assert result["existing_test_names"] == ["test_existing_add"]
    assert "test_app.py: test_existing_add" in result["existing_tests_context"]
    assert "add(1, 2)" not in result["existing_tests_context"]


def test_analysis_rebuilds_image_for_missing_dynamic_import(tmp_path, monkeypatch):
    info = ProjectInfo(root=str(tmp_path), name="dynamic", languages=["Python"], source_files=[], supported=True, adapter="python")
    monkeypatch.setattr("agents.generic_pipeline.detect_project", lambda _root: info)
    monkeypatch.setattr("agents.generic_pipeline.ensure_runner_image", lambda: None)
    build_calls = []

    def build(_root, _run_dir, **kwargs):
        build_calls.append(kwargs.get("extra_modules"))
        return f"smarttest-project:run{len(build_calls)}", kwargs.get("extra_modules", [])

    monkeypatch.setattr("agents.generic_pipeline.build_project_image", build)
    run_calls = []

    def run(_root, _run_dir, _tests, **kwargs):
        run_calls.append(kwargs["image"])
        if len(run_calls) == 1:
            return {"missing_dependencies": ["flask_sqlalchemy"], "exit_code": 1}
        return {"missing_dependencies": [], "exit_code": 0, "passed": 2, "failed": 0, "errors": 0, "coverage": {"totals": {}, "files": {}}}

    monkeypatch.setattr("agents.generic_pipeline.run_in_docker", run)
    result = analyze_node({"project_path": str(tmp_path), "run_dir": str(tmp_path / "run"), "docker_image": "auto"})
    assert build_calls == [None, ["flask_sqlalchemy"]]
    assert run_calls == ["smarttest-project:run1", "smarttest-project:run2"]
    assert result["docker_image"] == "smarttest-project:run2"


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


def test_runner_extracts_generated_test_pass_and_failure_names():
    from sandbox.generic_runner import _generated_test_names

    output = (
        "smarttest_generated/test_generated.py::test_good PASSED\n"
        "smarttest_generated/test_generated.py::test_bad[param] FAILED\n"
    )
    assert _generated_test_names(output, "PASSED") == ["test_good"]
    assert _generated_test_names(output, "FAILED|ERROR") == ["test_bad"]


def test_failure_summary_keeps_test_names_and_short_causes():
    output = """=========================== FAILURES ===========================
________________________ test_create_user_duplicate ________________________
> client.get('/create_user/testuser')
E       sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: user.username
________________________ test_create_user_invalid_name _____________________
> assert response.data == b'Not Found'
E       AssertionError: assert b'<html>404</html>' == b'Not Found'
"""
    summary = summarize_failure_details(output)
    assert "test_create_user_duplicate" in summary
    assert "UNIQUE constraint failed" in summary
    assert "test_create_user_invalid_name" in summary
    assert "response.data == b'Not Found'" in summary
    assert len(summary) < 1200


def test_retry_feedback_includes_failed_test_body_and_direct_repair_instruction():
    code = "def test_duplicate(client):\n    client.get('/user/same')\n    response = client.get('/user/same')\n    assert response.status_code == 400\n"
    details = "________________ test_duplicate ________________\nE sqlalchemy.exc.IntegrityError: UNIQUE constraint failed"
    feedback = _failure_repair_context(code, details)
    assert "test_duplicate" in feedback
    assert "client.get('/user/same')" in feedback
    assert "replaced or corrected" in feedback.lower()
    feedback = _failure_repair_context(
        code,
        details + "\nE sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: user.username",
    )
    assert "from sqlalchemy.exc import IntegrityError" in feedback
    assert "pytest.raises(IntegrityError)" in feedback
    assert "do not assert status_code 400" in feedback
    assert "Failing test test_generated" not in feedback


def test_retry_merge_keeps_passing_tests_and_replaces_only_failed_tests():
    previous = (
        "import pytest\n"
        "@pytest.fixture\ndef client(): return object()\n"
        "def test_passed(client): assert client is not None\n"
        "def test_failed(client): assert client.bad()\n"
    )
    replacement = (
        "import pytest\n"
        "client = object()\n"
        "def test_failed():\n    with pytest.raises(ValueError):\n        client.bad()\n"
        "def test_another(client): assert client is not None\n"
    )
    merged = _merge_retry_tests(previous, replacement, ["test_failed"])
    assert "def test_passed" in merged
    assert "pytest.raises(ValueError)" in merged
    assert merged.count("def test_passed") == 1
    assert "def test_another" in merged
    assert "def test_failed(client):" in merged
    assert "client = object()" not in merged


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


def test_langgraph_stops_when_baseline_coverage_is_already_complete(tmp_path, monkeypatch):
    counts = {"generate": 0, "finalize": 0}

    def analyze(_state):
        return {"coverage_saturated": True, "coverage_before": 100, "branch_coverage_before": 100}

    def generate(_state):
        counts["generate"] += 1
        raise AssertionError("No generation is needed when line and branch coverage are already complete")

    def finalize(_state):
        counts["finalize"] += 1
        return {"stage": "completed"}

    monkeypatch.setattr(generic_workflow, "analyze_node", analyze)
    monkeypatch.setattr(generic_workflow, "generate_node", generate)
    monkeypatch.setattr(generic_workflow, "finalize_node", finalize)
    result = generic_workflow.build_generic_workflow().invoke({
        "project_path": str(tmp_path), "run_dir": str(tmp_path / "run"), "iteration": 0, "max_iterations": 3,
    })
    assert counts == {"generate": 0, "finalize": 1}
    assert result["iteration"] == 0


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
    assert "/app" in docker_run
    assert "/app/smarttest_generated/test_generated.py" not in docker_run
    assert result["exit_code"] == 0
    assert result["container_policy"]["network"] == "none"
