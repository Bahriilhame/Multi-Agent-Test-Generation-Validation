"""Build a cached, project-specific Python test image from detected dependencies."""

from __future__ import annotations

import ast
import hashlib
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

BASE_IMAGE = "smarttest-runner:latest"
IMPORT_TO_DISTRIBUTION = {
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python-headless",
    "Crypto": "pycryptodome",
    "dateutil": "python-dateutil",
    "flask_sqlalchemy": "Flask-SQLAlchemy",
    "jwt": "PyJWT",
    "MySQLdb": "mysqlclient",
    "OpenSSL": "pyOpenSSL",
    "psycopg2": "psycopg2-binary",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
}
BASE_MODULES = set(sys.stdlib_module_names) | {
    "pytest", "coverage", "pluggy", "packaging", "langsmith", "pydantic",
    "typing_extensions", "iniconfig", "pygments", "exceptiongroup",
}


def _project_dependencies(root: Path, extra_modules: list[str] | None = None) -> tuple[list[str], list[str]]:
    requirements: list[Path] = sorted(root.glob("requirements*.txt"))
    deps: list[str] = []
    for path in requirements:
        deps.append(path.read_text(encoding="utf-8", errors="replace"))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        project = data.get("project", {})
        deps.extend(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            deps.extend(group)
        poetry = data.get("tool", {}).get("poetry", {})
        for name, value in poetry.get("dependencies", {}).items():
            if name.lower() == "python":
                continue
            deps.append(_poetry_requirement(name, value))
        for group in poetry.get("group", {}).values():
            for name, value in group.get("dependencies", {}).items():
                deps.append(_poetry_requirement(name, value))

    project_modules: set[str] = set()
    imported: set[str] = set()
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(part in {".git", ".venv", "venv", "tests", "test", "__pycache__", "node_modules", ".tox", ".mypy_cache"} for part in relative.parts):
            continue
        project_modules.add(path.stem)
        project_modules.update(part for part in relative.parent.parts if part.isidentifier())
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    inferred = sorted((imported | set(extra_modules or [])) - BASE_MODULES - project_modules)
    inferred_lines = [IMPORT_TO_DISTRIBUTION.get(name, name) for name in inferred]
    combined = "\n".join([*deps, *inferred_lines])
    unique = list(dict.fromkeys(line.strip() for line in combined.splitlines() if line.strip() and not line.lstrip().startswith("#")))
    return unique, inferred


def _poetry_requirement(name: str, value: object) -> str:
    if isinstance(value, str):
        version = value
    elif isinstance(value, dict):
        version = str(value.get("version", ""))
    else:
        version = ""
    if version in {"", "*"}:
        return name
    if version.startswith(("^", "~")):
        version = ">=" + version[1:]
    constraint = version if version.startswith(("=", "<", ">", "!", "~")) else "==" + version
    return f"{name}{constraint}"


def build_project_image(
    project_root: str | Path,
    run_dir: str | Path,
    *,
    extra_modules: list[str] | None = None,
    progress: Callable[[str, str, str | None], None] | None = None,
) -> tuple[str, list[str]]:
    """Create a non-root dependency image; only dependency metadata enters its build context."""
    root = Path(project_root).resolve()
    run = Path(run_dir).resolve()
    dependencies, inferred_modules = _project_dependencies(root, extra_modules)
    digest = hashlib.sha256("\n".join(sorted(dependencies)).encode()).hexdigest()[:16]
    image = f"smarttest-project:{digest}"

    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, check=False)
    if inspected.returncode == 0:
        return image, inferred_modules

    context = run / "runtime" / "image-build"
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    for source in sorted(root.glob("requirements*.txt")):
        target = context / source.name
        target.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    inferred = [IMPORT_TO_DISTRIBUTION.get(module, module) for module in inferred_modules]
    pyproject_dependencies = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        project = data.get("project", {})
        pyproject_dependencies.extend(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            pyproject_dependencies.extend(group)
        poetry = data.get("tool", {}).get("poetry", {})
        for name, value in poetry.get("dependencies", {}).items():
            if name.lower() != "python":
                pyproject_dependencies.append(_poetry_requirement(name, value))
        for group in poetry.get("group", {}).values():
            pyproject_dependencies.extend(
                _poetry_requirement(name, value)
                for name, value in group.get("dependencies", {}).items()
            )
    auto_dependencies = [*pyproject_dependencies, *inferred]
    if auto_dependencies:
        (context / "requirements-auto.txt").write_text("\n".join(auto_dependencies) + "\n", encoding="utf-8")
    (context / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\n"
        "USER tester\n"
        "ENV PATH=/home/tester/.local/bin:$PATH\n"
        "COPY --chown=tester:tester . /tmp/project-requirements/\n"
        "RUN for requirements_file in /tmp/project-requirements/requirements*.txt; do \\\n"
        "      if [ -f \"$requirements_file\" ] && [ -s \"$requirements_file\" ]; then \\\n"
        "        python -m pip install --user --no-cache-dir -r \"$requirements_file\" || exit $?; \\\n"
        "      fi; \\\n"
        "    done\n",
        encoding="utf-8",
    )
    if progress:
        progress("started", f"Construction de l’environnement Python ({len(dependencies)} dépendance(s) détectée(s))", None)
    result = subprocess.run(
        ["docker", "build", "--network=default", "-t", image, "-f", str(context / "Dockerfile"), str(context)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=900,
    )
    if result.returncode:
        detail = (result.stdout + "\n" + result.stderr)[-6000:]
        if progress:
            progress("failed", "Construction de l’environnement Python", detail[-1200:])
        raise RuntimeError("Automatic project dependency image build failed:\n" + detail)
    if progress:
        progress("completed", "Environnement Python construit", None)
    return image, inferred_modules
