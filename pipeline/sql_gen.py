"""
Node 4 — sql_gen

Generates a SQL query directly from verified table schemas (YAML) and the
cleaned query. The full YAML content — columns, join conditions, metrics — is
passed as-is; the LLM must not invent anything not present in the schemas.

LLM: gpt-4o-mini
Reads:  cleaned_query, verified_yamls
Writes: sql_query
"""

from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You are a SQL writer for a natural language to SQL system.

Rules:
- Use ONLY the tables and columns present in the schemas provided.
- Copy join conditions VERBATIM from the schema — do not rewrite or invent them.
- Use metric SQL expressions verbatim where the schema defines them.
- Do NOT invent tables, columns, or joins not present in the schemas.
- Output only the SQL query — no explanation, no markdown fences."""

_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY)


def sql_gen(state: SQLState) -> dict:
    if not state.get("verified_yamls"):
        return {"sql_query": ""}

    schema_context = "\n---\n".join(state["verified_yamls"])
    user_message = (
        f"Dialect: {Config.DB_DIALECT}\n\n"
        f"Question: {state['cleaned_query']}\n\n"
        f"Schemas:\n{schema_context}"
    )
    response = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])
    return {"sql_query": response.content.strip()}
