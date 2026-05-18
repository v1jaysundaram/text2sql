"""
Text-to-SQL v2.0 — LangGraph pipeline entry point.

Pipeline: query_prep → retrieval → verifier → [route]
          ↑                                  → sql_gen → END   (tables verified)
          └──── retry ────────────────────────←          (no tables, retry_count < 2)
                                             → END       (no tables, retry_count >= 2)
"""

from langgraph.graph import StateGraph, START, END

from pipeline.state import SQLState
from pipeline.query_prep import query_prep
from pipeline.retrieval import retrieval
from pipeline.verifier import verifier
from pipeline.sql_gen import sql_gen


def _route_from_verifier(state: SQLState) -> str:
    if state["verified_tables"]:
        return "sql_gen"
    if state.get("error_message"):
        return END
    return "query_prep"


_graph = StateGraph(SQLState)
_graph.add_node("query_prep", query_prep)
_graph.add_node("retrieval", retrieval)
_graph.add_node("verifier", verifier)
_graph.add_node("sql_gen", sql_gen)

_graph.add_edge(START, "query_prep")
_graph.add_edge("query_prep", "retrieval")
_graph.add_edge("retrieval", "verifier")
_graph.add_conditional_edges(
    "verifier",
    _route_from_verifier,
    {"sql_gen": "sql_gen", "query_prep": "query_prep", END: END},
)
_graph.add_edge("sql_gen", END)

workflow = _graph.compile()


def run_text2sql(question: str, debug: bool = False) -> dict:
    initial_state: SQLState = {
        "original_query": question,
        "cleaned_query": "",
        "retrieved_tables": [],
        "retrieved_yamls": [],
        "verified_tables": [],
        "verified_yamls": [],
        "verifier_reasoning": "",
        "suggested_search_terms": [],
        "error_message": "",
        "retry_count": 0,
        "sql_query": "",
    }
    result = workflow.invoke(initial_state)
    if debug:
        return result
    if result.get("error_message"):
        return {"error": result["error_message"]}
    return {"answer": result["sql_query"]}


if __name__ == "__main__":
    #question = "$$$$ Give me the list of all ordrs and when they where   placed."
    question = "Do we have a user by the name of Vijay?"
    #question = "How many users signed up in the last month, and which marketing channel brought them in?"
    result = run_text2sql(question, debug=True)
    print(result.get("sql_query") or result.get("error_message"))
