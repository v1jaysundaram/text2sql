"""
Node 5 — sql_gen

Generates SQL purely from the schema_plan produced by context_fetch.
The plan already contains exact column names, verbatim join conditions,
verbatim metric SQL, and filter hints — no raw YAML needed.

LLM: gpt-4o-mini
Reads:  cleaned_query, schema_plan
Writes: sql_query
"""

import json

from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You are a SQL writer for a natural language to SQL system.

You are given a schema plan. Follow it exactly:
- Use ONLY the tables listed in used_tables.
- Include ONLY the columns in selected_columns; their role field tells you
  whether each belongs in SELECT, WHERE, GROUP BY, HAVING, or ORDER BY.
- Copy required_joins conditions VERBATIM — do not rewrite or alter the ON clause.
  Use the join_type specified in the plan.
- Copy relevant_metrics SQL expressions VERBATIM into the SELECT clause.
- Apply filter_hints as WHERE conditions exactly as described.

Output only the SQL query — no explanation, no markdown fences.
Respect the SQL dialect specified."""

_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY, timeout=60)


def sql_gen(state: SQLState) -> dict:
    plan = state.get("schema_plan") or {}
    if not plan:
        return {"sql_query": ""}

    user_message = (
        f"Dialect: {Config.DB_DIALECT}\n\n"
        f"Question: {state['cleaned_query']}\n\n"
        f"Schema Plan:\n{json.dumps(plan, indent=2)}"
    )

    response = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])
    return {"sql_query": response.content.strip()}
