"""
Node 1 — query_prep

Operates in two modes:

PREP mode (default, first pass): corrects typos/grammar in original_query and
extracts concept phrases for multi-query ChromaDB retrieval.

EXTEND mode (retry, when verifier_suggested_terms or context_fetch_suggested_terms is non-empty):
no LLM call. Merges gap terms into retrieval_queries. No counter logic — counters are
owned by their respective nodes (verifier, context_fetch).

LLM: gpt-4o-mini (structured output, PREP mode only)
Reads:  original_query, verifier_suggested_terms, context_fetch_suggested_terms, retrieval_queries
Writes: cleaned_query, retrieval_queries
"""

from typing import List

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState


class _PrepOutput(BaseModel):
    cleaned_query: str = Field(
        description=(
            "Query with typos and minor grammatical errors corrected (spelling, subject-verb agreement, "
            "pluralization, missing articles). Normalize whitespace. Do NOT rephrase or change meaning."
        )
    )
    retrieval_queries: List[str] = Field(
        description=(
            "short concept phrases extracted from the question for semantic retrieval. "
            "Each phrase names one distinct concept needed to answer the question "
            "(e.g., 'customer orders', 'delivery status', 'revenue by region', 'product category'). "
            "Do NOT include the full question — only focused keyword phrases."
        )
    )


_SYSTEM_PROMPT = """You are a query preparation assistant for a natural language to SQL system.

Your tasks:
1. Correct any typos and minor grammatical errors in the user's question (spelling, subject-verb
   agreement, pluralization, missing articles). Normalize whitespace. Do NOT rephrase or change meaning.
2. Extract short concept phrases from the question that capture distinct data concepts needed
   to answer it (e.g. entities, metrics, dimensions, filters). These are used as individual
   semantic search queries against a table description index — make each phrase focused and specific."""


_llm = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY, timeout=60).with_structured_output(
    _PrepOutput
)


def query_prep(state: SQLState) -> dict:
    verifier_terms = state.get("verifier_suggested_terms") or []
    cf_terms = state.get("context_fetch_suggested_terms") or []
    suggested_terms = list(dict.fromkeys(verifier_terms + cf_terms))

    if suggested_terms:
        # EXTEND mode: no LLM call — merge gap terms, counters managed by their nodes
        existing = state.get("retrieval_queries") or []
        return {
            "retrieval_queries": list(dict.fromkeys(existing + suggested_terms)),
        }

    # PREP mode: correct query + extract concepts
    result: _PrepOutput = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": state["original_query"]},
    ])
    return {
        "cleaned_query": result.cleaned_query,
        "retrieval_queries": result.retrieval_queries,
    }
