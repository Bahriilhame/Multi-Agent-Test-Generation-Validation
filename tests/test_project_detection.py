import json

from adapters import detect_project


def test_detects_python_project_and_tests(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text("def run(): return 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text("def test_run(): assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    report = detect_project(tmp_path)

    assert report.supported is True
    assert report.adapter == "python"
    assert report.source_files == ["src/app.py"]
    assert report.test_files == ["tests/test_app.py"]
    assert "pyproject.toml" in report.config_files


def test_identifies_javascript_but_does_not_claim_support(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "1"}}), encoding="utf-8")
    (tmp_path / "index.ts").write_text("export const answer = 42\n", encoding="utf-8")

    report = detect_project(tmp_path)

    assert "TypeScript" in report.languages
    assert "Vitest" in report.frameworks
    assert report.supported is False
    assert report.adapter is None
    assert report.unsupported_reason


def test_ignores_virtualenv_and_node_modules(tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "hidden.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("", encoding="utf-8")
    assert detect_project(tmp_path).languages == []


def test_detects_frameworks_from_source_and_java_build_metadata(tmp_path):
    (tmp_path / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("Flask>=3\n", encoding="utf-8")
    python_info = detect_project(tmp_path)
    assert "Flask" in python_info.frameworks

    java = tmp_path / "java-project"
    java.mkdir()
    (java / "src").mkdir()
    (java / "src" / "Application.java").write_text("class Application {}\n", encoding="utf-8")
    (java / "pom.xml").write_text("org.springframework.boot spring-boot-starter-test junit\n", encoding="utf-8")
    java_info = detect_project(java)
    assert "Spring Boot" in java_info.frameworks
    assert "JUnit" in java_info.frameworks
    assert "Maven" in java_info.package_managers
    assert java_info.supported is False
