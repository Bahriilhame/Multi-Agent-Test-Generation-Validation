
from graph.workflow import build_workflow
from experiments.tracking import new_run
from pathlib import Path
import shutil


def main():

    workflow = build_workflow()

    run = new_run("checkout", "multiagent", "SmartTest-AI")
    source_test = Path("tests/generated/test_generated_checkout.py")
    run_test = Path(run["run_dir"]) / "generated_tests" / "test_generated_checkout.py"
    run_test.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_test, run_test)

    initial_state = {
        "project_path": "src/shop",
        "project_name": "SmartTest-AI",
        "iteration": 0,
        "max_iterations": 2,
        "benchmark": "checkout",
        "mode": "multiagent",
        "run_id": run["run_id"],
        "run_dir": run["run_dir"],
        "generated_test_file": str(run_test),
        "generated_test_count": 0,
    }

    print("\nStarting SmartTest AI...\n")

    result = workflow.invoke(initial_state)

    print("\nWorkflow finished.")

    print(result)


if __name__ == "__main__":
    main()
