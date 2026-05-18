"""
Node — verifier

Reasons about whether the retrieved tables are actually relevant to the
user's question. Filters retrieved_yamls down to verified_yamls.
If no tables are relevant, provides suggested_search_terms for a retry.

LLM: gpt-4o-mini (structured output)
Reads:  cleaned_query, retrieved_yamls, retry_count
Writes: verified_tables, verified_yamls, verifier_reasoning,
        suggested_search_terms, error_message
"""

from typing import List

import yaml
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MAX_RETRIES = 2


class VerifierOutput(BaseModel):
    relevant_tables: List[str] = Field(
        description=(
            "Subset of the retrieved table names that are truly needed to answer the "
            "question. Return an empty list if none of the retrieved tables are relevant."
        )
    )
    reasoning: str = Field(
        description="Brief explanation of which tables are needed and why, or why none are relevant."
    )
    suggested_search_terms: List[str] = Field(
        description=(
            "2-3 better search terms to use for retrieval if no tables are relevant. "
            "Return an empty list when relevant_tables is non-empty."
        )
    )


_SYSTEM_PROMPT = """You are a table relevance verifier for a natural language to SQL system.

You will be given a user's question and the frontmatter (name, description, business context)
of tables retrieved by a vector search. Your job is to decide which of these tables are
actually required to answer the question.

Rules:
- Only include tables that are genuinely necessary to construct the SQL query.
- If a table is only tangentially related (e.g. could be used but is not needed), exclude it.
- If none of the retrieved tables are relevant, return an empty relevant_tables list and
  provide 2-3 specific search terms that would help find the right tables.
- Do not hallucinate table names — only reference names from the provided list.
- Keep reasoning concise (1-3 sentences)."""


_llm = ChatOpenAI(model="gpt-4o-mini", api_key=Config.OPENAI_API_KEY).with_structured_output(
    VerifierOutput
)


def _build_tables_summary(retrieved_yamls: List[str]) -> str:
    parts = []
    for yaml_str in retrieved_yamls:
        data = yaml.safe_load(yaml_str)
        parts.append(
            f"Table: {data.get('table', '')}\n"
            f"Description: {data.get('description', '')}\n"
            f"Business Context: {data.get('business_context', '')}"
        )
    return "\n\n".join(parts)


def verifier(state: SQLState) -> dict:
    tables_summary = _build_tables_summary(state["retrieved_yamls"])

    user_message = (
        f"Question: {state['cleaned_query']}\n\n"
        f"Retrieved tables:\n\n{tables_summary}"
    )

    result: VerifierOutput = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    relevant_set = set(result.relevant_tables)
    verified_yamls = [
        yaml_str for yaml_str in state["retrieved_yamls"]
        if yaml.safe_load(yaml_str).get("table") in relevant_set
    ]

    error_message = ""
    if not result.relevant_tables and state["retry_count"] >= _MAX_RETRIES:
        error_message = (
            "Could not find relevant tables after 2 retries. "
            "Please try rephrasing your question."
        )

    return {
        "verified_tables": result.relevant_tables,
        "verified_yamls": verified_yamls,
        "verifier_reasoning": result.reasoning,
        "suggested_search_terms": result.suggested_search_terms if not result.relevant_tables else [],
        "error_message": error_message,
    }
