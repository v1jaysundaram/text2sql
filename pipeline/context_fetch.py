"""
Node — context_fetch

Determines whether the verified table schemas are *sufficient* to answer the question,
then produces a structured SchemaPlan for sql_gen.

Reads:  cleaned_query, verified_tables, verified_yamls, verifier_reasoning, retry_count
Writes: schema_plan, context_fetch_reasoning, context_fetch_completeness,
        context_fetch_suggested_terms, context_fetch_user_message, context_fetch_error

Completeness semantics:
  "complete"   → sql_gen can produce a full answer
  "partial"    → some required concept is missing from verified tables → retry with gap terms
  "impossible" → data does not exist in the DB; user must rephrase → no retry
"""

from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MAX_RETRIES = 2
_MODEL = "gpt-4o-mini"


# ─────────────────────────── Pydantic output models ───────────────────────────

class ColumnRef(BaseModel):
    table: str = Field(description="Exact table name from verified_tables")
    column: str = Field(description="Exact column name from YAML")
    role: str = Field(description="One of: SELECT, WHERE, GROUP BY, HAVING, ORDER BY, JOIN KEY")


class JoinSpec(BaseModel):
    from_table: str = Field(description="Left side of the JOIN")
    to_table: str = Field(description="Right side of the JOIN")
    join_type: str = Field(description="LEFT or INNER — copied verbatim from YAML, never invented")
    condition: str = Field(description="Verbatim SQL join condition string from YAML")
    cardinality: str = Field(description="many_to_one | one_to_many | one_to_one | many_to_many")


class MetricRef(BaseModel):
    table: str
    metric_name: str
    sql_expression: str = Field(description="Verbatim SQL expression from YAML metrics.sql")
    description: str


class FilterHint(BaseModel):
    table: str = Field(description="Table containing the filter column")
    column: str = Field(description="Column to filter on")
    description: str = Field(description="e.g. WHERE order_status = 'delivered'")


class SchemaGap(BaseModel):
    required_concept: str = Field(description="e.g. 'customer geographic location (state)'")
    why_needed: str = Field(description="e.g. 'question asks for breakdown by state'")
    missing_reason: str = Field(description="e.g. 'none of verified tables have state/city columns'")
    suggested_terms: List[str] = Field(description="3-5 specific search terms for the missing concept")


class SchemaPlan(BaseModel):
    primary_table: str = Field(description="Table the FROM clause anchors to")
    used_tables: List[str] = Field(description="Subset of verified_tables actually needed")
    dropped_tables: List[str] = Field(description="Verified tables excluded; must be explicit")
    selected_columns: List[ColumnRef] = Field(description="All columns needed in SELECT/WHERE/GROUP BY/HAVING/ORDER BY")
    required_joins: List[JoinSpec] = Field(description="Ordered join sequence; conditions copied verbatim from YAML")
    relevant_metrics: List[MetricRef] = Field(description="Pre-built metric SQL expressions to embed verbatim")
    filter_hints: List[FilterHint] = Field(description="WHERE clause conditions inferred from the question")
    completeness: Literal["complete", "partial", "impossible"] = Field(
        description=(
            "complete: verified tables contain all data needed to answer the question fully. "
            "partial: at least one required concept (filter column, dimension, metric) is absent "
            "from verified tables — retry with suggested terms. "
            "impossible: the data simply does not exist in any relational e-commerce database — no retry."
        )
    )
    gaps: List[SchemaGap] = Field(description="Populated for partial and impossible; empty for complete")
    user_message: str = Field(description="User-facing explanation for impossible completeness; empty otherwise")
    plan_reasoning: str = Field(description="Brief explanation of decisions made; always populated")
    suggested_terms: List[str] = Field(
        description="Aggregated suggested_terms from all gaps; populated for partial; empty otherwise"
    )


# ─────────────────────────── Helpers ───────────────────────────

def _format_yamls_for_plan(verified_yamls: List[str]) -> str:
    """Compact YAML blocks stripped of version/business_context to reduce tokens."""
    parts = []
    for yaml_str in verified_yamls:
        data = yaml.safe_load(yaml_str)
        block = f"Table: {data['table']}\n"
        block += "Columns:\n"
        for col in data.get("columns", []):
            samples = ", ".join(str(v) for v in col.get("sample_values", [])[:3])
            block += f"  - {col['name']} ({col['type']}): {col['description']}"
            if samples:
                block += f" [samples: {samples}]"
            block += "\n"
        block += "Joins:\n"
        for j in data.get("joins", []):
            block += f"  - {j['type']} JOIN {j['to']} ON {j['condition']} ({j['cardinality']})\n"
        block += "Metrics:\n"
        for m in data.get("metrics", []):
            block += f"  - {m['name']}: {m['sql']}  # {m['description']}\n"
        parts.append(block)
    return "\n---\n".join(parts)


def _run_guardrails(plan: SchemaPlan, verified_tables: List[str]) -> Optional[str]:
    """Returns an error string if guardrails fail; None if the plan is clean."""
    valid = set(verified_tables)
    for t in plan.used_tables:
        if t not in valid:
            return f"Hallucinated table '{t}' in used_tables — not in verified_tables."
    used_set = set(plan.used_tables)
    for j in plan.required_joins:
        if j.from_table not in used_set or j.to_table not in used_set:
            return f"Join {j.from_table} → {j.to_table} references table not in used_tables."
    return None


def _guardrail_fail_plan(reason: str) -> SchemaPlan:
    return SchemaPlan(
        primary_table="", used_tables=[], dropped_tables=[],
        selected_columns=[], required_joins=[], relevant_metrics=[], filter_hints=[],
        completeness="impossible",
        gaps=[SchemaGap(
            required_concept="valid schema reference",
            why_needed="plan referenced tables or joins not present in verified tables",
            missing_reason=reason,
            suggested_terms=[],
        )],
        user_message="An internal error occurred while building the query plan. Please try again.",
        plan_reasoning=f"Guardrail failed: {reason}",
        suggested_terms=[],
    )


def _build_state_output(plan: SchemaPlan, retry_count: int) -> dict:
    error = ""
    if plan.completeness == "partial" and retry_count >= _MAX_RETRIES:
        error = (
            "Could not build a complete schema plan after retries. "
            "Please rephrase your question to reference specific tables or metrics."
        )
    return {
        "schema_plan": plan.model_dump(),
        "context_fetch_reasoning": plan.plan_reasoning,
        "context_fetch_completeness": plan.completeness,
        "context_fetch_suggested_terms": plan.suggested_terms if plan.completeness == "partial" else [],
        "context_fetch_user_message": plan.user_message if plan.completeness == "impossible" else "",
        "context_fetch_error": error,
    }


# ─────────────────────────── System prompt ───────────────────────────

_SYSTEM_PROMPT = """You are a schema planner for a text-to-SQL system.
Given the user's question and verified table schemas, you must:

STEP 1 — Completeness Assessment (do this FIRST):
Identify all required data concepts in the question: filters (WHERE), dimensions (GROUP BY),
measures (SELECT aggregations), and sort criteria (ORDER BY).
Check whether each concept has a corresponding column in the verified tables.

Set completeness as follows:
- "complete":   ALL required concepts are covered by the verified tables.
- "partial":    At least one required concept is missing. Describe each gap and provide
                3-5 specific suggested_terms naming the missing column/concept.
- "impossible": The question asks for data that cannot exist in any relational e-commerce
                database (e.g. credit scores, social media metrics, real-time prices).
                Write a clear user_message telling the user what is missing and why.

STEP 2 — Build the schema plan (only for completeness = "complete"):
- primary_table: the fact/hub table the FROM clause anchors to.
- used_tables: ONLY tables whose columns, joins, or metrics are directly required.
- dropped_tables: list every verified table not used and briefly explain why.
- selected_columns: only columns in SELECT / WHERE / GROUP BY / HAVING / ORDER BY.
- required_joins: copy join conditions VERBATIM from the YAML. Never rewrite or invent them.
  Order joins logically outward from primary_table.
- relevant_metrics: when the question's aggregation matches a YAML metric, use its sql verbatim.
- filter_hints: infer WHERE conditions from the question; use sample values as reference.

HARD RULES:
- Do NOT reference table names not provided in the schema.
- Do NOT invent join conditions — only use conditions from the YAML joins section.
- Set "partial" rather than guessing at a plan with missing data."""


_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY).with_structured_output(SchemaPlan)


# ─────────────────────────── Node ───────────────────────────

def context_fetch(state: SQLState) -> dict:
    schema_text = _format_yamls_for_plan(state["verified_yamls"])
    user_msg = (
        f"Question: {state['cleaned_query']}\n\n"
        f"Verified Table Schemas:\n\n{schema_text}\n\n"
        f"Verifier Reasoning: {state['verifier_reasoning']}"
    )

    try:
        plan: SchemaPlan = _llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ])
    except Exception as exc:
        return {
            "schema_plan": None,
            "context_fetch_reasoning": f"LLM output validation failed: {exc}",
            "context_fetch_completeness": "impossible",
            "context_fetch_suggested_terms": [],
            "context_fetch_user_message": "An internal error occurred while planning the query. Please try again.",
            "context_fetch_error": "",
        }

    guardrail_err = _run_guardrails(plan, state["verified_tables"])
    if guardrail_err:
        plan = _guardrail_fail_plan(guardrail_err)

    return _build_state_output(plan, state["retry_count"])
