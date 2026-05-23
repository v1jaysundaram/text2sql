"""
Text-to-SQL v2.0 — LangGraph pipeline entry point.

Pipeline:
  query_prep → retrieval → verifier → sql_gen

Retry loop (up to 2 retries, shared counter):
  verifier: no verified tables        → query_prep (rewrite + extend concepts)
  verifier: partial sufficiency       → query_prep (rewrite + extend concepts with gap terms)

Dead ends (→ END immediately):
  verifier: retry ceiling hit while tables still empty
"""

from langgraph.graph import StateGraph, START, END

from config import Config
from pipeline.state import SQLState
from pipeline.query_prep import query_prep
from pipeline.retrieval import retrieval
from pipeline.verifier import verifier
from pipeline.sql_gen import sql_gen

_MAX_RETRIES = 2


def _route_from_verifier(state: SQLState) -> str:
    if not state["verified_tables"]:
        if state.get("error_message"):
            return END
        return "query_prep"
    if (state.get("verifier_sufficiency") == "partial"
            and state["retry_count"] < _MAX_RETRIES):
        return "query_prep"
    return "sql_gen"


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
        "retrieval_queries": [],
        # retrieval
        "retrieved_tables": [],
        "retrieved_yamls": [],
        # verifier
        "verified_tables": [],
        "verified_yamls": [],
        "verifier_reasoning": "",
        "verifier_sufficiency": "",
        "suggested_search_terms": [],
        "error_message": "",
        # retry control
        "retry_count": 0,
        # sql_gen
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
    #question = "What is the capital of France?"
    #question = "What is the total revenue by customer state for delivered orders in 2018?"
    #question = "List top sellers by state alongside their average review score"
    question = "How many users signed up in the last month, and which marketing channel brought them in?"
    result = run_text2sql(question, debug=True)
    print("SQL:", result.get("sql_query") or result.get("error_message"))