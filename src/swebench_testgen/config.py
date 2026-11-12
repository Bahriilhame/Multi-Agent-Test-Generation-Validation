"""Environment-backed project configuration."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    dataset_id: str = "princeton-nlp/SWE-bench_Lite"
    dataset_revision: str | None = None
    dataset_split: str = "dev"
    cache_dir: Path = Path(".cache/huggingface")
    workspace_dir: Path = Path("workspaces")
    max_iterations: int = 2
    coverage_minimum: int = 0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            dataset_id=os.getenv("SWE_DATASET_ID", "princeton-nlp/SWE-bench_Lite"),
            dataset_revision=os.getenv("SWE_DATASET_REVISION") or None,
            dataset_split=os.getenv("SWE_DATASET_SPLIT", "dev"),
            cache_dir=Path(os.getenv("SWE_CACHE_DIR", ".cache/huggingface")),
            workspace_dir=Path(os.getenv("SWE_WORKSPACE_DIR", "workspaces")),
            max_iterations=max(1, int(os.getenv("SWE_MAX_ITERATIONS", "2"))),
            coverage_minimum=max(0, int(os.getenv("SWE_COVERAGE_MINIMUM", "0"))),
        )

