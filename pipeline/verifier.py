"""
Node 3 — verifier

Two-pass check in a single LLM call:
1. Filter: select which retrieved tables are genuinely needed.
2. Sufficiency: check whether the selected tables' descriptions collectively cover
   all concepts the question requires. Flag 'partial' if a concept is clearly absent.

If no tables are relevant → suggests retry terms → query_prep re-runs (EXTEND mode).
If tables found but partial → suggests gap terms → query_prep re-runs (EXTEND mode).
Semantic layer descriptions are the source of truth; column-level validation is sql_gen's job.

LLM: gpt-4o-mini (structured output)
Reads:  cleaned_query, retrieval_queries, retrieved_yamls, retry_count
Writes: verified_tables, verified_yamls, verifier_reasoning, verifier_sufficiency,
        verifier_suggested_terms, error_message
"""

from typing import List, Literal

import yaml
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MAX_RETRIES = 1


class VerifierOutput(BaseModel):
    relevant_tables: List[str] = Field(
        description=(
            "Subset of the retrieved table names that are truly needed to answer the "
            "question. Return an empty list if none of the retrieved tables are relevant."
        )
    )
    sufficiency: Literal["sufficient", "partial"] = Field(
        description=(
            "'sufficient': the selected tables' descriptions collectively cover ALL key concepts "
            "(entities, measures, dimensions, filters) the question requires. "
            "'partial': at least one required concept is clearly absent from ALL selected table "
            "descriptions — e.g. question asks 'by state' but no selected table mentions geography. "
            "Default to 'sufficient' when relevant_tables is empty (sufficiency is moot)."
        )
    )
    reasoning: str = Field(
        description=(
            "Brief explanation of which tables are needed and why, or why none are relevant. "
            "If partial, state which concept is missing and from which table it would be expected."
        )
    )
    suggested_search_terms: List[str] = Field(
        description=(
            "2-4 specific search terms for missing concepts when relevant_tables is empty "
            "OR sufficiency='partial'. Name the missing concept concisely "
            "(e.g., 'customer address state', 'product category name'). "
            "Empty when sufficient."
        )
    )


_SYSTEM_PROMPT = """You are a table relevance verifier for a natural language to SQL system.

You are given a user's question and the frontmatter (name, description, business context)
of tables retrieved by a vector search.

STEP 1 — Filter:
Select only the tables that are genuinely necessary to construct the SQL query.
Exclude tables that are tangential or not needed. Return an empty list if none are relevant.

STEP 2 — Sufficiency check (only when relevant_tables is non-empty):
You are given an explicit list of concepts that were extracted from the question.
Check whether each concept is covered by at least one selected table's description or
business context.

Set sufficiency:
- "sufficient": every required concept is mentioned or clearly implied in at least one
  selected table's description. If the description says the concept is there, trust it —
  do NOT speculate about whether a specific column exists. Column-level validation happens
  in a later node.
- "partial": a required concept is completely absent from ALL selected table descriptions
  with no mention or implication. This is a high bar — only flag partial when a concept
  has zero coverage across all descriptions.

IMPORTANT: The semantic layer is the source of truth. If a table's description implies a
concept is present, mark sufficient. Only suggest retry terms when a concept is genuinely
unrepresented across all retrieved table descriptions."""


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

    concepts = ", ".join(state.get("retrieval_queries") or [state["cleaned_query"]])
    user_message = (
        f"Question: {state['cleaned_query']}\n\n"
        f"Concepts to check coverage for: {concepts}\n\n"
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
            "Could not find relevant tables after retries. "
            "Please try rephrasing your question."
        )

    needs_terms = not result.relevant_tables or result.sufficiency == "partial"

    # Reset retry_count when handing off to context_fetch for the first time so context_fetch
    # gets its own fresh budget. Guard: only reset if context_fetch hasn't run yet ("").
    passing_to_context_fetch = (
        bool(result.relevant_tables)
        and result.sufficiency == "sufficient"
        and not state.get("context_fetch_completeness")
    )

    return {
        "verified_tables": result.relevant_tables,
        "verified_yamls": verified_yamls,
        "verifier_reasoning": result.reasoning,
        "verifier_sufficiency": result.sufficiency if result.relevant_tables else "",
        "verifier_suggested_terms": result.suggested_search_terms if needs_terms else [],
        "error_message": error_message,
        "retry_count": 0 if passing_to_context_fetch else state["retry_count"],
    }
