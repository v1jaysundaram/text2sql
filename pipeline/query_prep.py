"""
Node 1 — query_prep

Operates in two modes:

PREP mode (default, first pass): corrects typos/grammar in original_query and
extracts 3-6 concept phrases for multi-query ChromaDB retrieval.

EXTEND mode (retry, when verifier_suggested_terms or context_fetch_suggested_terms is non-empty):
no LLM call. Merges gap terms from verifier and/or context_fetch into retrieval_queries.
cleaned_query is unchanged — ChromaDB is driven by concept phrases, not the query sentence.

LLM: gpt-4o-mini (structured output, PREP mode only)
Reads:  original_query, verifier_suggested_terms, context_fetch_suggested_terms,
        retry_count, retrieval_queries
Writes: cleaned_query, retrieval_queries, [retry_count]
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
            "3-6 short concept phrases extracted from the question for semantic retrieval. "
            "Each phrase names one distinct concept needed to answer the question "
            "(e.g., 'customer orders', 'delivery status', 'revenue by region', 'product category'). "
            "Do NOT include the full question — only focused keyword phrases."
        )
    )


_SYSTEM_PROMPT = """You are a query preparation assistant for a natural language to SQL system.

Your tasks:
1. Correct any typos and minor grammatical errors in the user's question (spelling, subject-verb
   agreement, pluralization, missing articles). Normalize whitespace. Do NOT rephrase or change meaning.
2. Extract 3-6 short concept phrases from the question that capture distinct data concepts needed
   to answer it (e.g. entities, metrics, dimensions, filters). These are used as individual
   semantic search queries against a table description index — make each phrase focused and specific."""


_llm = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY).with_structured_output(
    _PrepOutput
)


def query_prep(state: SQLState) -> dict:
    verifier_terms = state.get("verifier_suggested_terms") or []
    cf_terms = state.get("context_fetch_suggested_terms") or []
    suggested_terms = list(dict.fromkeys(verifier_terms + cf_terms))

    if suggested_terms:
        # EXTEND mode: no LLM call — merge gap terms from verifier and/or context_fetch
        existing = state.get("retrieval_queries") or []
        return {
            "retrieval_queries": list(dict.fromkeys(existing + suggested_terms)),
            "retry_count": state["retry_count"] + 1,
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
