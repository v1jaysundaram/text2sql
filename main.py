"""
Text-to-SQL v2.0 — LangGraph pipeline entry point.

Pipeline: query_prep → retrieval → sql_gen
Remaining nodes (verifier, context_fetch, sql_val, sql_exec) added incrementally.
"""

from langgraph.graph import StateGraph, START, END

from pipeline.state import SQLState
from pipeline.query_prep import query_prep
from pipeline.retrieval import retrieval
from pipeline.sql_gen import sql_gen

# Graph

_graph = StateGraph(SQLState)
_graph.add_node("query_prep", query_prep)
_graph.add_node("retrieval", retrieval)
_graph.add_node("sql_gen", sql_gen)

_graph.add_edge(START, "query_prep")
_graph.add_edge("query_prep", "retrieval")
_graph.add_edge("retrieval", "sql_gen")
_graph.add_edge("sql_gen", END)

workflow = _graph.compile()


def run_text2sql(question: str, debug: bool = False) -> dict:
    initial_state: SQLState = {
        "original_query": question,
        "cleaned_query": "",
        "retrieved_tables": [],
        "retrieved_yamls": [],
        "sql_query": "",
        "llm_model_used": "",
    }
    result = workflow.invoke(initial_state)
    if debug:
        return result
    return {"answer": result["sql_query"]}


if __name__ == "__main__":
    question = "$$$$ Give me the list of all ordrs and when they where   placed."
    result = run_text2sql(question, debug=True)
    print(result["sql_query"])
