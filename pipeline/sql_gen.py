"""
Node — sql_gen

Generates a SQL query from the verified schema context and cleaned query.

LLM: gpt-4o-mini
Reads:  cleaned_query, verified_yamls
Writes: sql_query
"""

from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MODEL = "gpt-4o-mini"

_PROMPT_TEMPLATE = """You are a SQL assistant. Given the schema context below, generate a valid SQL query for the question.
Output only the SQL query — no explanation, no markdown fences.

Dialect: {dialect}

Question:
{question}

Schema Context:
{schema}

"""

_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY)


def sql_gen(state: SQLState) -> dict:
    schema_context = "\n---\n".join(state["verified_yamls"])
    prompt = _PROMPT_TEMPLATE.format(
        dialect=Config.DB_DIALECT,
        schema=schema_context,
        question=state["cleaned_query"],
    )
    response = _llm.invoke(prompt)
    return {"sql_query": response.content.strip()}
