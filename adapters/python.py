"""Python/pytest adapter used by generic project workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.base import ProjectAdapter, ProjectInfo, detect_project


class PythonAdapter(ProjectAdapter):
    language = "Python"

    def detect_project(self, root: Path) -> ProjectInfo:
        info = detect_project(root)
        if not info.supported or info.adapter != "python":
            raise ValueError(info.unsupported_reason or f"No supported Python application source found under {root}")
        return info

    def discover_tests(self, root: Path) -> list[Path]:
        return sorted(p for p in root.rglob("*.py") if p.is_file() and (p.name.startswith("test_") or p.parent.name == "tests") and not {".venv", "venv", "__pycache__"}.intersection(p.parts))

    def generate_test_context(self, root: Path, info: ProjectInfo, limit: int = 16_000) -> str:
        chunks, used = [], 0
        for rel in info.source_files:
            p = root / rel
            try: content = p.read_text(encoding="utf-8")
            except (OSError, UnicodeError): continue
            chunk = f"\n# Source: {rel}\n```python\n{content}\n```\n"
            if used + len(chunk) > limit: break
            chunks.append(chunk); used += len(chunk)
        return "".join(chunks)

    def analyze_coverage(self, root: Path, report_path: Path) -> dict[str, Any]:
        from sandbox.generic_runner import run_in_docker
        result = run_in_docker(root, report_path.parent, "")
        if result.get("coverage"):
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result["coverage"], indent=2), encoding="utf-8")
        return {"available": result.get("coverage") is not None, "totals": (result.get("coverage") or {}).get("totals", {}), "files": (result.get("coverage") or {}).get("files", {}), "exit_code": result["exit_code"], "output": result["output"]}

    def execute_tests(self, root: Path, tests: Path, timeout: int = 120) -> dict[str, Any]:
        from sandbox.generic_runner import run_in_docker
        generated = tests.read_text(encoding="utf-8")
        return run_in_docker(root, tests.parent, generated, timeout_seconds=timeout)

    def collect_results(self, report_path: Path) -> dict[str, Any]:
        if not report_path.is_file():
            return {"available": False, "files": {}, "totals": {}}
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return {"available": True, "files": data.get("files", {}), "totals": data.get("totals", {})}
