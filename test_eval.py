# tests/test_eval.py

from langsmith import Client, evaluate

# Import your wrapper function from your main workflow file
from main_v6 import run_text2sql


def run_langsmith_eval():
    """
    Runs evaluation of the Text-to-SQL pipeline using LangSmith.

    """

    client = Client()

    dataset_name = "text2sql"       # Your dataset name in LangSmith

    evaluate(
        run_text2sql,
        data=dataset_name,
        #data=client.list_examples(dataset_name=dataset_name, splits=["golden_set"]), # quick_test, golden_set, base
        experiment_prefix="text2sql-test-3",
        num_repetitions=2, # This field defaults to 1
        max_concurrency=2 # This defaults to None
    )


if __name__ == "__main__":
    run_langsmith_eval()
