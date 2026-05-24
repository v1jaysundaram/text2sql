"""
Text-to-SQL v2.0 — LangGraph pipeline entry point.

Pipeline:
  query_prep → retrieval → verifier → context_fetch → sql_gen

Retry loop (up to 2 retries, shared counter):
  verifier: no verified tables        → query_prep (EXTEND mode)
  verifier: partial sufficiency       → query_prep (EXTEND mode with gap terms)
  context_fetch: partial columns      → query_prep (EXTEND mode with targeted column terms)

Dead ends (→ END immediately):
  verifier: retry ceiling hit while tables still empty
  context_fetch: partial after max retries, or impossible
"""

from langgraph.graph import StateGraph, START, END

from config import Config
from pipeline.state import SQLState
from pipeline.query_prep import query_prep
from pipeline.retrieval import retrieval
from pipeline.verifier import verifier
from pipeline.context_fetch import context_fetch
from pipeline.sql_gen import sql_gen

_MAX_RETRIES = 1


def _route_from_verifier(state: SQLState) -> str:
    if not state["verified_tables"]:
        if state.get("error_message"):
            return END
        return "query_prep"
    if (state.get("verifier_sufficiency") == "partial"
            and state["retry_count"] < _MAX_RETRIES):
        return "query_prep"
    return "context_fetch"


def _route_from_context_fetch(state: SQLState) -> str:
    if state.get("context_fetch_completeness") == "complete":
        return "sql_gen"
    # incomplete — retry if budget remains, else terminal
    if state["retry_count"] < _MAX_RETRIES:
        return "query_prep"
    return END


_graph = StateGraph(SQLState)
_graph.add_node("query_prep", query_prep)
_graph.add_node("retrieval", retrieval)
_graph.add_node("verifier", verifier)
_graph.add_node("context_fetch", context_fetch)
_graph.add_node("sql_gen", sql_gen)

_graph.add_edge(START, "query_prep")
_graph.add_edge("query_prep", "retrieval")
_graph.add_edge("retrieval", "verifier")
_graph.add_conditional_edges(
    "verifier",
    _route_from_verifier,
    {"context_fetch": "context_fetch", "query_prep": "query_prep", END: END},
)
_graph.add_conditional_edges(
    "context_fetch",
    _route_from_context_fetch,
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
        "verifier_suggested_terms": [],
        "error_message": "",
        # retry control
        "retry_count": 0,
        # context_fetch
        "schema_plan": {},
        "context_fetch_reasoning": "",
        "context_fetch_completeness": "",
        "context_fetch_suggested_terms": [],
        "context_fetch_gap_message": "",
        "context_fetch_error": "",
        # sql_gen
        "sql_query": "",
    }

    result = workflow.invoke(initial_state)

    if debug:
        return result

    if result.get("error_message"):
        return {"error": result["error_message"]}
    if result.get("context_fetch_gap_message"):
        return {"error": result["context_fetch_gap_message"]}
    if result.get("context_fetch_error"):
        return {"error": result["context_fetch_error"]}
    return {"answer": result["sql_query"]}


if __name__ == "__main__":
    #question = "$$$$ Give me the list of all ordrs and when they where   placed."
    #question = "What is the capital of France?"
    #question = "What is the total revenue by customer state for delivered orders in 2018?"
    #question = "List top sellers by state alongside their average review score"
    #question = "How many users signed up in the last month, and which marketing channel brought them in?"
    question = "What is the average review score by product category?"
    ques
    result = run_text2sql(question, debug=True)
    print("SQL:", result.get("sql_query") or result.get("error_message"))