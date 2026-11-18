"""Common CLI to run the independent HumanEval and MBPP adapters."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime

from config.settings import BASE_DIR


def _command(benchmark: str, limit: int, seed: int, baseline_only: bool, critic_mode: str) -> list[str]:
    command = [sys.executable, "-m", f"experiments.{benchmark}", "--limit", str(limit), "--seed", str(seed), "--critic-mode", critic_mode]
    if baseline_only:
        command.append("--baseline-only")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run independent Python benchmark adapters sequentially")
    parser.add_argument("--benchmarks", choices=("humaneval", "mbpp", "all"), default="all")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", help="Ollama model name")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--critic-mode", choices=("llm", "heuristic"), default="llm")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = BASE_DIR / "experiments" / "benchmark-suites" / run_id
    run_dir.mkdir(parents=True)
    env = os.environ.copy()
    if args.model:
        env["OLLAMA_MODEL"] = args.model
    names = ["humaneval", "mbpp"] if args.benchmarks == "all" else [args.benchmarks]
    results = []
    for name in names:
        command = _command(name, args.limit, args.seed, args.baseline_only, args.critic_mode)
        try:
            process = subprocess.run(command, check=False, cwd=BASE_DIR, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = process.stdout + "\n" + process.stderr
            code = process.returncode
        except OSError as error:
            output, code = str(error), 127
        (run_dir / f"{name}.log").write_text(output, encoding="utf-8")
        results.append({"benchmark": name, "exit_code": code, "command": command, "log": f"{name}.log", "model": env.get("OLLAMA_MODEL", "qwen2.5-coder:7b"), "limit": args.limit, "seed": args.seed, "critic_mode": args.critic_mode, "metric_note": "HumanEval and MBPP scores use distinct task splits and protocols; do not treat them as interchangeable."})
    summary = {"run_id": run_id, "status": "completed" if all(row["exit_code"] == 0 for row in results) else "partial_or_failed", "benchmarks": results}
    (run_dir / "benchmark_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": summary["status"], "benchmarks": [{"benchmark": row["benchmark"], "exit_code": row["exit_code"]} for row in results]}, indent=2))
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
