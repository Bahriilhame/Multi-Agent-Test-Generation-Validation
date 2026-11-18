# Architecture SmartTest-AI

## Two workflows

`python main.py` remains the initial checkout demonstration. `platform_cli.py run SOURCE` invokes the project-generic LangGraph workflow. The latter uses these nodes:

```text
analyze/detect/coverage → generator → isolated validation → relevance critic
                                      ↑                         │
                                      └──── bounded retry ──────┘
                                                  ↓
                                               finalize
```

The graph state carries the resolved project information, chosen adapter, source and test context, line and branch coverage, generated tests, Docker results, critic evidence, iteration count, errors and acceptance decision. Each run records `events.jsonl`, logs, generated tests, coverage JSON and a final JSON/Markdown report.

## Adapters

`ProjectAdapter` defines project detection, coverage, test discovery, context preparation, test execution and result collection. `detect_project()` recognizes Python, JavaScript, TypeScript and Java plus common package managers/configurations and frameworks. Only `PythonAdapter` is executable. Unsupported primary languages are reported without routing their code through the Python runner.

The Python runner stages a disposable source copy and a separately generated test module. It omits Git metadata, virtual environments, common secret files and links. It measures application coverage while omitting test files. Application dependencies must already exist in the chosen image; runtime package installation is intentionally avoided. Missing Python modules in baseline pytest output stop the run early with a Docker image build hint.

## Four agents

1. **Coverage analyst:** project discovery, existing-test discovery, baseline pytest/coverage in Docker, missing lines/branches/functions and a priority ordering.
2. **Test generator:** Ollama prompt using source, uncovered details, existing tests, task context and prior critique; validates Python syntax, pytest functions and disallowed imports/process calls before saving into a unique run directory.
3. **Validation executor:** constrained Docker runner, offline network, read-only root and project mount, dropped Linux capabilities, `no-new-privileges`, non-root UID, process/memory/CPU limits, timeout, temporary output mount and container cleanup.
4. **Relevance critic:** deterministic assertion/execution/coverage checks combined with an Ollama semantic review. It rejects failed tests, a quality score under threshold, missing semantic review or a coverage regression. The loop has a configurable iteration cap.

The critic score is a review aid, not a proof of assertion strength. Mutation testing remains available for the checkout demonstration; generic mutation analysis is future work.

## Isolation boundary

Project Python and generated tests execute only inside Docker. The host process reads source text and invokes Docker CLI, but does not import or run project modules. The runtime container receives no network, Docker socket, host environment variables or writable project mount. Docker still relies on its daemon and host kernel; a Docker escape remains a platform risk. A custom image should contain only the project dependencies and pytest tools required for the run.

ZIP extraction checks for traversal, symlinks, file-count limits and a 1 GB uncompressed size cap. Git sources are cloned without submodules; their files are staged with the same link and secret exclusions.

## Benchmarks

- **HumanEval:** official task data, generated pytest tests on reference solutions; this is not official solution-generation pass@k.
- **MBPP:** sanitized test split and reference tests; run artifacts explicitly label the protocol and are not conflated with HumanEval.
- **SWE-bench Lite:** task prep excludes gold patches from prompts. `run-tests` evaluates generated tests on the base revision. `official-eval` delegates real patch predictions to the upstream harness and reports the official resolution protocol separately. A test-generation score is never labeled as an SWE-bench resolved score.

Benchmark datasets and artifacts remain reproducible per-run, with task IDs, seeds, versions/hashes when supplied by the adapter, model configuration, test output and coverage reports.
