"""
Node 1 — query_prep

Operates in two modes:

CORRECT mode (default, first pass): corrects typos and minor grammatical errors
in original_query. Preserves meaning exactly.

REWRITE mode (when suggested_search_terms is non-empty): rewrites original_query
to be more precise using verifier feedback. Increments retry_count.

LLM: gpt-4o-mini (structured output via function calling)
Reads:  original_query, suggested_search_terms, verifier_reasoning, retry_count
Writes: cleaned_query, [retry_count]
"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState


# --- CORRECT mode ---

class _CorrectedQuery(BaseModel):
    cleaned_query: str = Field(
        description=(
            "Query with typos and minor grammatical errors corrected (spelling, subject-verb agreement, "
            "pluralization, missing articles). Normalize whitespace. Do NOT rephrase or change meaning."
        )
    )


_CORRECT_SYSTEM_PROMPT = """You are a query correction assistant for a natural language to SQL system.

Correct any typos and minor grammatical errors in the user's question (spelling, subject-verb agreement,
pluralization, missing articles). Normalize whitespace.
Do NOT rephrase, reword, or change the meaning in any way."""


# --- REWRITE mode ---

class _RewrittenQuery(BaseModel):
    cleaned_query: str = Field(
        description=(
            "A more precise rewrite of the original question that incorporates the suggested "
            "search terms and verifier feedback. The core intent must remain unchanged — only "
            "make the question more specific, well-formed, and aligned with the available tables."
        )
    )


_REWRITE_SYSTEM_PROMPT = """You are a query rewriter for a natural language to SQL system.

The user asked a question, but the initial retrieval found no relevant database tables.
You are given the original question, the verifier's reasoning, and suggested search terms.

Rewrite the question to be more precise and specific so that retrieval can find the right tables.
Use the suggested terms naturally. Do NOT change the user's core intent. Keep the rewrite concise."""


_llm_correct = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY).with_structured_output(
    _CorrectedQuery
)
_llm_rewrite = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY).with_structured_output(
    _RewrittenQuery
)


def query_prep(state: SQLState) -> dict:
    if state.get("suggested_search_terms"):
        suggested_terms = ", ".join(state["suggested_search_terms"])
        user_message = (
            f"Original question: {state['original_query']}\n\n"
            f"Verifier reasoning: {state['verifier_reasoning']}\n\n"
            f"Suggested search terms: {suggested_terms}"
        )
        result: _RewrittenQuery = _llm_rewrite.invoke([
            {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        return {
            "cleaned_query": result.cleaned_query,
            "retry_count": state["retry_count"] + 1,
        }

    result: _CorrectedQuery = _llm_correct.invoke([
        {"role": "system", "content": _CORRECT_SYSTEM_PROMPT},
        {"role": "user", "content": state["original_query"]},
    ])
    return {"cleaned_query": result.cleaned_query}
