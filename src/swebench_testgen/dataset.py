"""Load only agent-safe SWE-bench task metadata."""

from collections.abc import Iterable
import os
from pathlib import Path
from typing import Any

from .state import TaskInput

AGENT_FIELDS = frozenset({
    "instance_id", "repo", "base_commit", "environment_setup_commit",
    "problem_statement", "hints_text", "version",
})
FORBIDDEN_AGENT_FIELDS = frozenset({"patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS"})


def project_agent_task(row: dict[str, Any]) -> TaskInput:
    """Project a raw benchmark row onto the allow-listed fields only."""
    missing = AGENT_FIELDS.difference(row)
    if missing:
        raise ValueError(f"Missing required SWE-bench fields: {sorted(missing)}")
    return {key: str(row[key] or "") for key in AGENT_FIELDS}  # type: ignore[return-value]


def load_tasks(split: str = "dev", *, revision: str | None = None,
               cache_dir: str | None = None, limit: int | None = None) -> list[TaskInput]:
    """Fetch official dataset rows, returning no gold patch/test fields."""
    from datasets import load_dataset

    if split not in {"dev", "test"}:
        raise ValueError("SWE-bench Lite split must be 'dev' or 'test'")
    kwargs: dict[str, Any] = {"split": split}
    resolved_cache = cache_dir or os.getenv("SWE_CACHE_DIR")
    if resolved_cache:
        cache_root = Path(resolved_cache).expanduser().resolve()
        kwargs["cache_dir"] = str(cache_root / "datasets")
        os.environ.setdefault("HF_HOME", str(cache_root / "hf"))
    if revision:
        kwargs["revision"] = revision
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", **kwargs)
    rows: Iterable[dict[str, Any]] = dataset
    if limit is not None:
        rows = list(dataset.select(range(min(limit, len(dataset)))))
    return [project_agent_task(row) for row in rows]

