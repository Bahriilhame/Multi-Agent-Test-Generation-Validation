# SWE-bench test generation research prototype

Foundation for a LangGraph workflow that studies repository coverage and generates tests. Agent implementation is intentionally not included yet.

## Environment

Use Python 3.11 or 3.12. Create a virtual environment outside the repository if the system drive is low on space, then install with `python -m pip install -e .`.

Copy `.env.example` to `.env` and set `SWE_CACHE_DIR` and `SWE_WORKSPACE_DIR` to locations with sufficient free space. The default dataset split is `dev`.

## Current foundation

- Dataset projection only exposes task ID, repository, commits, issue statement, hints, and version. Gold patch and reference test fields are excluded.
- LangGraph shared state and a minimal compiled graph are present; no agent logic is implemented.
- Git helper prepares a detached worktree at the dataset base commit.
- Docker helper reports engine availability. Docker must be running before containerized benchmark work.
- Coverage helper invokes pytest-cov with branch coverage and produces a JSON report.

## Commands

```powershell
python -m pip install -e .
pytest
```

