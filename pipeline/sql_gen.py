"""
Node 3 — sql_gen

Generates a SQL query from the retrieved schema context and cleaned query.
Uses a single model for now.

LLM: gpt-4o-mini
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


def sql_gen(state: SQLState) -> dict:
    llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY)

    schema_context = "\n---\n".join(state["retrieved_yamls"])
    prompt = _PROMPT_TEMPLATE.format(
        dialect=Config.DB_DIALECT,
        schema=schema_context,
        question=state["cleaned_query"],
    )

    response = llm.invoke(prompt)
    return {
        "sql_query": response.content.strip()
    }
