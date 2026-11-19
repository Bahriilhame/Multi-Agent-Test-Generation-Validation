
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

PROJECT_DIR = BASE_DIR / "src" / "shop"

TESTS_DIR = BASE_DIR / "tests"

GENERATED_TESTS_DIR = TESTS_DIR / "generated"

REPORTS_DIR = BASE_DIR / "reports"

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5-coder:7b"
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)

MAX_ITERATIONS = int(os.getenv("SMARTTEST_MAX_ITERATIONS", "2"))

MIN_RELEVANCE_SCORE = float(os.getenv("SMARTTEST_MIN_QUALITY_SCORE", "70"))
RUNNER_IMAGE = os.getenv("SMARTTEST_DOCKER_IMAGE", "auto")
DOCKER_TIMEOUT_SECONDS = int(os.getenv("SMARTTEST_DOCKER_TIMEOUT_SECONDS", "120"))
