
from graph.workflow import build_workflow


def main():

    workflow = build_workflow()

    initial_state = {
        "project_path": "src/shop",
        "project_name": "SmartTest-AI",
        "iteration": 0,
        "max_iterations": 2
    }

    print("\nStarting SmartTest AI...\n")

    result = workflow.invoke(initial_state)

    print("\nWorkflow finished.")

    print(result)


if __name__ == "__main__":
    main()
