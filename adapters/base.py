"""Project discovery and adapter contracts for SmartTest-AI.

Only Python has an executable adapter today. Other ecosystems are identified
explicitly as planned so callers cannot mistake detection for support.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist",
    "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".tox",
}


@dataclass
class ProjectInfo:
    root: str
    name: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    supported: bool = False
    adapter: str | None = None
    unsupported_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectAdapter(ABC):
    """Common adapter API. Implementations own tool-specific behavior."""

    language: str

    @abstractmethod
    def detect_project(self, root: Path) -> ProjectInfo: ...

    @abstractmethod
    def analyze_coverage(self, root: Path, report_path: Path) -> dict[str, Any]: ...

    @abstractmethod
    def discover_tests(self, root: Path) -> list[Path]: ...

    @abstractmethod
    def generate_test_context(self, root: Path, info: ProjectInfo, limit: int = 16_000) -> str: ...

    @abstractmethod
    def execute_tests(self, root: Path, tests: Path, timeout: int = 120) -> dict[str, Any]: ...

    @abstractmethod
    def collect_results(self, report_path: Path) -> dict[str, Any]: ...


def _all_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and not IGNORED_DIRS.intersection(p.parts)]


def detect_project(root: str | Path) -> ProjectInfo:
    """Inspect a local project and report detectable conventions/tools."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Project directory does not exist: {root}")
    files = _all_files(root)
    rel = lambda paths: sorted(p.relative_to(root).as_posix() for p in paths)
    ext_language = {
        ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
        ".go": "Go", ".rs": "Rust", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
        ".swift": "Swift", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    }
    counts: dict[str, int] = {}
    for p in files:
        if p.suffix in ext_language:
            lang = ext_language[p.suffix]
            counts[lang] = counts.get(lang, 0) + 1
    languages = sorted(counts, key=lambda x: (-counts[x], x))
    config_filenames = {"pyproject.toml", "pytest.ini", "setup.py", "setup.cfg", "requirements.txt", "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "jest.config.js", "vitest.config.ts", "tox.ini", "Makefile", "Dockerfile", "go.mod", "Cargo.toml", "Gemfile", "composer.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
    configs = [p for p in files if p.name in config_filenames]
    tests = [p for p in files if p.name.startswith(("test_",)) or ".test." in p.name or ".spec." in p.name or "tests" in p.parts or "test" in p.parts]
    sources = [p for p in files if p.suffix in ext_language and p not in tests]
    frameworks: set[str] = set()
    managers: set[str] = set()
    config_names = {p.name for p in configs}
    if "requirements.txt" in config_names or "setup.py" in config_names: managers.add("pip")
    if "pyproject.toml" in config_names:
        pyproject = next(p for p in configs if p.name == "pyproject.toml")
        pytext = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
        managers.add("Poetry" if "[tool.poetry]" in pytext else "uv" if "[tool.uv" in pytext else "pip")
    if "package.json" in config_names: managers.add("npm")
    if "pnpm-lock.yaml" in config_names: managers.add("pnpm")
    if "yarn.lock" in config_names: managers.add("Yarn")
    if "pom.xml" in config_names: managers.add("Maven")
    if config_names.intersection({"build.gradle", "build.gradle.kts"}): managers.add("Gradle")
    if "go.mod" in config_names: managers.add("Go modules")
    if "Cargo.toml" in config_names: managers.add("Cargo")
    if "Gemfile" in config_names: managers.add("Bundler")
    if "composer.json" in config_names: managers.add("Composer")
    for p in files:
        if p.suffix == ".py" or p.name in {"requirements.txt", "pyproject.toml"}:
            try: txt = p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError: continue
            for marker, label in [("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"), ("pytest", "pytest"), ("coverage", "Coverage.py")]:
                if marker in txt: frameworks.add(label)
        if p.name == "package.json":
            try: data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): data = {}
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for marker, label in [("react", "React"), ("jest", "Jest"), ("vitest", "Vitest"), ("express", "Express")]:
                if marker in deps: frameworks.add(label)
        if p.name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            try: txt = p.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError: continue
            if "spring-boot" in txt or "org.springframework.boot" in txt: frameworks.add("Spring Boot")
            if "junit" in txt or "org.junit" in txt: frameworks.add("JUnit")
    python_source_count = sum(1 for p in sources if p.suffix == ".py")
    py_supported = python_source_count > 0 and bool(languages) and languages[0] == "Python"
    return ProjectInfo(
        root=str(root), name=root.name, languages=languages,
        frameworks=sorted(frameworks), package_managers=sorted(managers),
        source_files=rel(sources), test_files=rel(tests), config_files=rel(configs),
        entry_points=rel([p for p in sources if p.name in {"main.py", "app.py", "__main__.py", "index.js", "index.ts", "main.go", "Main.java", "Application.java"}]),
        supported=py_supported, adapter="python" if py_supported else None,
        unsupported_reason=None if py_supported else "Aucun adaptateur d'exécution n'est implémenté pour le langage principal du projet (ou aucun fichier source applicatif n'a été trouvé).",
    )
