"""Python/pytest adapter used by generic project workflows."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from adapters.base import ProjectAdapter, ProjectInfo, detect_project


class PythonAdapter(ProjectAdapter):
    language = "Python"

    def detect_project(self, root: Path) -> ProjectInfo:
        info = detect_project(root)
        if "Python" not in info.languages:
            raise ValueError(f"No Python source files found under {root}")
        return info

    def discover_tests(self, root: Path) -> list[Path]:
        return sorted(p for p in root.rglob("*.py") if p.is_file() and (p.name.startswith("test_") or p.parent.name == "tests") and not {".venv", "venv", "__pycache__"}.intersection(p.parts))

    def generate_test_context(self, root: Path, info: ProjectInfo, limit: int = 80_000) -> str:
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
        tests = self.discover_tests(root)
        if not tests:
            raise RuntimeError("No pytest test files found; coverage cannot be measured.")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-m", "pytest", "--cov", str(root), "--cov-branch", f"--cov-report=json:{report_path}", "--cov-report=term-missing", *map(str, tests)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        report = self.collect_results(report_path)
        report["exit_code"] = result.returncode
        report["output"] = (result.stdout + "\n" + result.stderr)[-12000:]
        return report

    def execute_tests(self, root: Path, tests: Path, timeout: int = 120) -> dict[str, Any]:
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tests)], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"exit_code": result.returncode, "output": (result.stdout + "\n" + result.stderr)[-12000:]}

    def collect_results(self, report_path: Path) -> dict[str, Any]:
        if not report_path.is_file():
            return {"available": False, "files": {}, "totals": {}}
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return {"available": True, "files": data.get("files", {}), "totals": data.get("totals", {})}
