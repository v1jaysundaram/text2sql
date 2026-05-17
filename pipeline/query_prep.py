"""
Node 1 — query_prep

Corrects typos and minor grammatical errors in the incoming query.
Keeps the meaning exactly intact — no rephrasing or intent inference.

LLM: gpt-4o-mini (structured output via function calling)
Writes: cleaned_query
"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState


class _QueryAnalysis(BaseModel):
    cleaned_query: str = Field(
        description=(
            "Query with typos and minor grammatical errors corrected (spelling, subject-verb agreement, "
            "pluralization, missing articles). Normalize whitespace. Do NOT rephrase or change meaning."
        )
    )


_SYSTEM_PROMPT = """You are a query correction assistant for a natural language to SQL system.

Correct any typos and minor grammatical errors in the user's question (spelling, subject-verb agreement,
pluralization, missing articles). Normalize whitespace.
Do NOT rephrase, reword, or change the meaning in any way."""

_llm = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY).with_structured_output(
    _QueryAnalysis
)


def query_prep(state: SQLState) -> dict:
    analysis: _QueryAnalysis = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": state["original_query"]},
    ])
    return {"cleaned_query": analysis.cleaned_query}
