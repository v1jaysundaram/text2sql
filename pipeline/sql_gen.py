"""
Node 4 — sql_gen

Generates SQL from the schema_plan (column/join/metric blueprint from context_fetch)
plus full verified YAMLs as reference for exact types and sample values.

LLM: gpt-4o-mini
Reads:  cleaned_query, schema_plan, verified_yamls
Writes: sql_query
"""

from typing import Any, Dict

from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You are a SQL writer for a natural language to SQL system.

You are given a schema plan and full table schemas.

Schema plan rules (highest priority):
- Use ONLY the tables listed in used_tables.
- Include ONLY the columns listed in selected_columns; their role field tells you
  whether each column belongs in SELECT, WHERE, GROUP BY, HAVING, or ORDER BY.
- Copy required_joins join conditions VERBATIM — do not rewrite or alter the ON condition.
  Use the join_type from the schema plan (it may already override the YAML default based on context).
- Copy relevant_metrics SQL expressions VERBATIM into the SELECT clause.
- Apply filter_hints as WHERE conditions; use sample values from the full schema for literals.

Full schema rules (reference only):
- Consult the full schemas for exact column names, data types, and sample values.
- Do NOT use any table or column not present in the full schemas.

Output rules:
- Output only the SQL query — no explanation, no markdown fences.
- Respect the SQL dialect specified."""

_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY)


def _format_schema_plan(plan: Dict[str, Any]) -> str:
    if not plan:
        return ""
    lines = [
        f"Primary table: {plan.get('primary_table', '')}",
        f"Used tables: {', '.join(plan.get('used_tables', []))}",
        f"Dropped tables: {', '.join(plan.get('dropped_tables', []))}",
        "",
        "Selected columns:",
    ]
    for col in plan.get("selected_columns", []):
        lines.append(f"  {col['table']}.{col['column']} — role: {col['role']}")

    lines.append("\nRequired joins:")
    for j in plan.get("required_joins", []):
        lines.append(
            f"  {j['join_type']} JOIN {j['to_table']} ON {j['condition']}  "
            f"({j['cardinality']})"
        )

    metrics = plan.get("relevant_metrics", [])
    if metrics:
        lines.append("\nMetrics (use SQL verbatim):")
        for m in metrics:
            lines.append(f"  {m['metric_name']}: {m['sql_expression']}  -- {m['description']}")

    hints = plan.get("filter_hints", [])
    if hints:
        lines.append("\nFilter hints:")
        for h in hints:
            lines.append(f"  {h['table']}.{h['column']}: {h['description']}")

    return "\n".join(lines)


def sql_gen(state: SQLState) -> dict:
    if not state.get("verified_yamls"):
        return {"sql_query": ""}

    plan_section = _format_schema_plan(state.get("schema_plan") or {})
    schema_context = "\n---\n".join(state["verified_yamls"])

    user_message = (
        f"Dialect: {Config.DB_DIALECT}\n\n"
        f"Question: {state['cleaned_query']}\n\n"
    )
    if plan_section:
        user_message += f"Schema Plan:\n{plan_section}\n\n"
    user_message += f"Full Schema Reference:\n{schema_context}"

    response = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])
    return {"sql_query": response.content.strip()}
