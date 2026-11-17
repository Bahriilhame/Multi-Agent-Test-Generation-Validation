
from graph.workflow import build_workflow
from experiments.tracking import new_run
from pathlib import Path
import logging

from experiments.tracking import finalize_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():

    workflow = build_workflow()

    run = new_run("checkout", "multiagent", "SmartTest-AI")
    source_test = Path("tests/generated/test_generated_checkout.py")
    run_test = Path(run["run_dir"]) / "generated_tests" / "test_generated_checkout.py"
    run_test.parent.mkdir(parents=True, exist_ok=True)

    initial_state = {
        "project_path": "src/shop",
        "project_name": "SmartTest-AI",
        "iteration": 0,
        "max_iterations": 2,
        "benchmark": "checkout",
        "mode": "multiagent",
        "run_id": run["run_id"],
        "run_dir": run["run_dir"],
        "generated_test_file": str(source_test),
        "generated_test_count": 0,
        "run_stage": "coverage",
    }

    print("\nStarting SmartTest AI...\n")

    try:
        initial_state["run_stage"] = "workflow"
        result = workflow.invoke(initial_state)
    except KeyboardInterrupt:
        initial_state["run_error"] = "Exécution interrompue par l'utilisateur (KeyboardInterrupt)."
        initial_state["run_stage"] = "interrupted"
        finalize_run(initial_state | {"validation_status": "interrupted"}, status="interrupted")
        print(f"\nRun interrompu et enregistré : {run['run_dir']}")
        raise
    except Exception as error:
        initial_state["run_error"] = f"{type(error).__name__}: {error}"
        if type(error).__name__ == "TimeoutError":
            initial_state["run_stage"] = "generation_timeout"
        else:
            initial_state["run_stage"] = "workflow_error"
        finalize_run(initial_state | {"validation_status": "error"}, status="error")
        print(f"\nÉchec enregistré dans : {run['run_dir']}")
        raise

    print("\nWorkflow finished.")

    print(result)


if __name__ == "__main__":
    main()
