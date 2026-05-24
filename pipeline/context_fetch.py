"""
Node 4 — context_fetch

Column-level validation of verified table schemas. Checks whether the specific columns,
joins, and metrics needed to answer the question exist in the verified YAMLs, then
produces a structured SchemaPlan for sql_gen.

LLM: gpt-4o-mini (structured output)
Reads:  cleaned_query, verified_tables, verified_yamls, verifier_reasoning,
        verifier_suggested_terms, context_fetch_suggested_terms, retry_count
Writes: schema_plan, context_fetch_reasoning, context_fetch_completeness,
        context_fetch_suggested_terms, context_fetch_gap_message, context_fetch_error

Completeness semantics:
  "complete"   → all required columns/joins/metrics found → proceed to sql_gen
  "incomplete" → at least one column missing → retry with targeted column/table terms
"""

from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from config import Config
from pipeline.state import SQLState

_MAX_RETRIES = 1
_MODEL = "gpt-4o-mini"


# ─────────────────────────── Pydantic output models ───────────────────────────

class ColumnRef(BaseModel):
    table: str = Field(description="Exact table name from verified_tables")
    column: str = Field(description="Exact column name from YAML")
    role: str = Field(description="One of: SELECT, WHERE, GROUP BY, HAVING, ORDER BY, JOIN KEY")


class JoinSpec(BaseModel):
    from_table: str = Field(description="Left side of the JOIN")
    to_table: str = Field(description="Right side of the JOIN")
    join_type: str = Field(
        description=(
            "Default to the join type from YAML. Override to INNER only when the question "
            "filters on a column from the joined table (implying a match is required). "
            "Never change LEFT to INNER without a clear filter-based reason."
        )
    )
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
    description: str = Field(description="Exact filter condition as a SQL predicate, e.g. 'year = 2018' or 'status = \\'approved\\''  — only when the question explicitly states a filter value")


class SchemaGap(BaseModel):
    required_concept: str = Field(description="e.g. 'customer geographic location (state)'")
    why_needed: str = Field(description="e.g. 'question asks for breakdown by state'")
    missing_reason: str = Field(description="e.g. 'none of verified tables have state/city columns'")
    suggested_terms: List[str] = Field(description="3-5 specific column or table names written without underscores (e.g. 'customer state', 'order payments') — used for semantic retrieval")


class SchemaPlan(BaseModel):
    primary_table: str = Field(description="Table the FROM clause anchors to")
    used_tables: List[str] = Field(description="Subset of verified_tables actually needed")
    dropped_tables: List[str] = Field(description="Verified tables excluded; must be explicit")
    selected_columns: List[ColumnRef] = Field(description="All columns needed in SELECT/WHERE/GROUP BY/HAVING/ORDER BY")
    required_joins: List[JoinSpec] = Field(description="Ordered join sequence; conditions copied verbatim from YAML")
    relevant_metrics: List[MetricRef] = Field(description="Pre-built metric SQL expressions to embed verbatim")
    filter_hints: List[FilterHint] = Field(description="WHERE clause conditions inferred from the question")
    completeness: Literal["complete", "incomplete"] = Field(
        description=(
            "complete: all required columns, joins, and metrics exist in the verified schemas. "
            "incomplete: at least one required column or metric is missing — populate gaps and suggested_terms."
        )
    )
    gaps: List[SchemaGap] = Field(description="Populated when incomplete; empty when complete")
    gap_message: str = Field(description="User-facing explanation of what is missing; empty when complete")
    plan_reasoning: str = Field(description="Brief explanation of decisions made; always populated")
    suggested_terms: List[str] = Field(
        description="Aggregated suggested_terms from all gaps; populated when incomplete; empty otherwise"
    )


# ─────────────────────────── Helpers ───────────────────────────

def _format_yamls_for_plan(verified_yamls: List[str]) -> str:
    return "\n---\n".join(verified_yamls)



def _build_state_output(plan: SchemaPlan, retry_count: int) -> dict:
    incomplete = plan.completeness == "incomplete"
    error = ""
    if incomplete and retry_count >= _MAX_RETRIES:
        error = (
            "Could not find all required columns after retries. "
            "Please verify your semantic layer YAML files contain the needed columns, "
            "or rephrase your question."
        )
    return {
        "schema_plan": plan.model_dump(),
        "context_fetch_reasoning": plan.plan_reasoning,
        "context_fetch_completeness": plan.completeness,
        "context_fetch_suggested_terms": plan.suggested_terms if incomplete else [],
        "context_fetch_gap_message": plan.gap_message if incomplete else "",
        "context_fetch_error": error,
    }


# ─────────────────────────── System prompt ───────────────────────────

_SYSTEM_PROMPT = """You are a schema planner for a text-to-SQL system.

CONTEXT: The upstream verifier has already confirmed that the verified table schemas
collectively cover all required concepts at the description level. Your job is strictly
column-level validation — check whether the specific columns, join conditions, and metrics
needed to answer the question actually exist in the schemas provided.

YAML STRUCTURE NOTE: In each schema, columns are listed as YAML entries where `name:` is the
field holding the column's identifier (e.g. `name: customer_id` means the column is called
`customer_id`). The word `name` itself is NOT a data column — never reference it as one.
Only use the values that appear after `name:` as actual column names.

STEP 1 — Column-level Completeness Assessment (do this FIRST):
For each concept phrase provided, identify the specific data element it requires (a column,
metric, or join key) and verify it exists by name in the schemas.

Set completeness as follows:
- "complete":    Every concept phrase maps to a real column/metric present in the schemas.
- "incomplete":  At least one concept phrase cannot be satisfied by any existing column or metric.
                 Populate gaps and suggested_terms.

STEP 2 — Build the schema plan (only for completeness = "complete"):
- primary_table: the fact/hub table the FROM clause anchors to.
- used_tables: ONLY tables whose columns, joins, or metrics are directly required.
- dropped_tables: list every verified table not used and briefly explain why.
- selected_columns: only columns in SELECT / WHERE / GROUP BY / HAVING / ORDER BY.
- required_joins: copy join conditions VERBATIM from the YAML. Order joins logically outward
  from primary_table. Default join_type to YAML value; override to INNER only when the
  question filters on a column from the joined table (a WHERE on that table implies a match
  is required). Never invent join conditions.
- relevant_metrics: when the question's aggregation matches a YAML metric, use its sql verbatim.
- filter_hints: infer WHERE conditions from the question; use sample values as reference.

HARD RULES:
- Do NOT reference table names not present in the verified schemas.
- Do NOT invent join conditions — only use conditions from the YAML joins section.
- Set "incomplete" rather than guessing at a plan with missing columns.
- filter_hints: ONLY populate when the question explicitly states a filter value or condition.
  Never invent filters based on assumed business context.
- For gaps: suggest the specific column or table name you are looking for, but written without
  underscores (e.g. 'customer state' not 'customer_state', 'order payments' not 'order_payments').
  These are used for semantic search — be specific, not generic."""


_llm = ChatOpenAI(model=_MODEL, api_key=Config.OPENAI_API_KEY, timeout=60).with_structured_output(SchemaPlan)


# ─────────────────────────── Node ───────────────────────────

def context_fetch(state: SQLState) -> dict:
    schema_text = _format_yamls_for_plan(state["verified_yamls"])
    previous_terms = list(dict.fromkeys(
        (state.get("verifier_suggested_terms") or []) +
        (state.get("context_fetch_suggested_terms") or [])
    ))

    previous_terms_section = ""
    if previous_terms:
        previous_terms_section = (
            f"Previously tried search terms (already retrieved, did not resolve all gaps): "
            f"{previous_terms}\n"
            f"Suggest different, more targeted column/table names to resolve remaining gaps.\n\n"
        )

    concepts = state.get("retrieval_queries") or []
    concepts_section = (
        f"Concept phrases extracted from the question: {', '.join(concepts)}\n\n"
        if concepts else ""
    )

    user_msg = (
        f"Question: {state['cleaned_query']}\n\n"
        f"{concepts_section}"
        f"Verified Table Schemas:\n\n{schema_text}\n\n"
        f"Verifier Reasoning: {state['verifier_reasoning']}\n\n"
        f"{previous_terms_section}"
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
            "context_fetch_completeness": "incomplete",
            "context_fetch_suggested_terms": [],
            "context_fetch_gap_message": "",
            "context_fetch_error": str(exc),
        }

    return _build_state_output(plan, state["retry_count"])
