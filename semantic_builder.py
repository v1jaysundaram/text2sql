"""
Semantic layer builder.

Reads table_purposes.yaml, introspects the live DB schema, samples column values,
calls GPT-4o once per table, and writes a YAML file to semantic/<table>.yaml.

Commands:
    python semantic_builder.py                                           # all 9 tables
    python semantic_builder.py --table olist_orders_dataset              # single table
    python semantic_builder.py --validate                           # validate all
    python semantic_builder.py --table olist_orders_dataset --validate  # validate one
    python semantic_builder.py --drift-check                                 # check all tables for schema drift
    python semantic_builder.py --table olist_orders_dataset --drift-check    # drift check one table
    python semantic_builder.py --sync                                        # patch all tables with DB changes
    python semantic_builder.py --table olist_orders_dataset --sync           # patch one table
"""

import argparse
import time
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import text

from config import Config
from connection import engine

SEMANTIC_DIR = Path("semantic")
TEMPLATE_PATH = SEMANTIC_DIR / "template.yaml"
EXAMPLE_PATH = SEMANTIC_DIR / "test.yaml"
PURPOSES_PATH = Path("table_purposes.yaml")


# Type Mapping

_TYPE_MAP = {
    "varchar": "VARCHAR", "char": "VARCHAR",
    "text": "VARCHAR", "tinytext": "VARCHAR", "mediumtext": "VARCHAR", "longtext": "VARCHAR",
    "int": "INT", "bigint": "INT", "smallint": "INT", "mediumint": "INT", "tinyint": "INT",
    "float": "FLOAT", "double": "FLOAT", "decimal": "FLOAT", "numeric": "FLOAT",
    "datetime": "DATETIME", "timestamp": "DATETIME", "date": "DATETIME", "time": "DATETIME",
    "boolean": "BOOLEAN", "bool": "BOOLEAN",
}


def _map_sql_type(data_type: str, col_type: str) -> str:
    if col_type == "tinyint(1)":
        return "BOOLEAN"
    return _TYPE_MAP.get(data_type.lower(), "VARCHAR")


# Column name suffix → YAML type overrides.
# Applied only when the DB-reported type is VARCHAR (e.g. dates stored as text).
# These are generic patterns — add or remove entries to match your dataset's conventions.
_NAME_OVERRIDES = [
    (("_timestamp", "_at", "_date", "_time"), "DATETIME"),
    (("_price", "_value", "_amount", "_cost", "_fee", "_total", "_weight"), "FLOAT"),
]


def _override_type_by_name(col_name: str, mapped_type: str) -> str:
    if mapped_type != "VARCHAR":      # only override VARCHAR — INT/FLOAT already correct
        return mapped_type
    name = col_name.lower()
    for suffixes, override in _NAME_OVERRIDES:
        if any(name.endswith(s) for s in suffixes):
            return override
    return mapped_type


# DB Helpers

def get_column_schema(table_name: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :table
            ORDER BY ORDINAL_POSITION
        """), {"db": Config.DB_NAME, "table": table_name}).fetchall()
    return [
        {"name": r[0], "type": _override_type_by_name(r[0], _map_sql_type(r[1], r[2]))}
        for r in rows
    ]


def get_sample_values(table_name: str, col_name: str, n: int = 5) -> list[str]:
    if Config.DB_DIALECT == "mysql":
        q = f"SELECT DISTINCT `{col_name}` FROM `{table_name}` WHERE `{col_name}` IS NOT NULL ORDER BY RAND() LIMIT {n}"
    else:
        q = f'SELECT DISTINCT "{col_name}" FROM "{table_name}" WHERE "{col_name}" IS NOT NULL ORDER BY RANDOM() LIMIT {n}'
    with engine.connect() as conn:
        rows = conn.execute(text(q)).fetchall()
    return [str(r[0]) for r in rows]


# Prompt Helpers

def _fmt_columns(columns: list[dict]) -> str:
    lines = []
    for col in columns:
        samples = ", ".join(col["samples"]) if col["samples"] else "no samples available"
        lines.append(f"  {col['name']} | {col['type']} | samples: {samples}")
    return "\n".join(lines)


# LLM YAML Builder

def build_yaml_via_llm(
    table_name: str,
    purpose: str,
    columns: list[dict],
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    example = EXAMPLE_PATH.read_text(encoding="utf-8")

    system_prompt = f"""You are a semantic layer builder for a text-to-SQL system.

Your task is to generate a YAML file that describes one database table. This YAML is
used to give an LLM the context it needs to write accurate SQL against this table.

OUTPUT FORMAT — match this template exactly:
---
{template}
---

REFERENCE EXAMPLE (a correctly completed YAML for another table):
---
{example}
---

RULES:
1. Output raw YAML only. No markdown code fences, no explanation, no preamble.
2. Write clear, analyst-friendly prose. Don't just restate column names.
3. For joins: include every table this table logically connects to. Infer joins from
   column naming patterns (e.g. a column named order_id implies a join on order_id)
   and the purpose description. Use the field name `condition:` (not `on:`) for the
   join predicate. Place a single "# TODO: review and adjust" comment above the joins
   list — do NOT add per-join TODO comments.
4. Join type: default to LEFT for all joins.
5. Cardinality is from THIS table's perspective TO the target table.
6. Generate 2-4 baseline metrics in the metrics section from column patterns:
   - DATETIME columns: duration or lag metrics using DATEDIFF or TIMESTAMPDIFF
   - FLOAT/DECIMAL columns: SUM and AVG aggregations
   - VARCHAR columns with status/category samples: count or percentage rate using CASE WHEN
   Add a comment "# TODO: review and adjust" above the metrics list.
   These are starting points — the user will verify and modify them.
7. Section headers must be normal case: `# Columns`, `# Joins`, `# Metrics` — not all caps.
8. business_context must answer: when should a SQL query start from this table?
   What analyses belong here? Do not restate the description field."""

    human_prompt = f"""Generate the YAML for this table.

Table name: {table_name}
Purpose: {purpose}

Columns (from live database schema):
{_fmt_columns(columns)}
"""

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])
    raw = response.content.strip()

    # strip accidental markdown fences or YAML document markers
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0].strip()
    if raw.startswith("---"):
        raw = raw.lstrip("-").lstrip()
    if raw.endswith("---"):
        raw = raw.rstrip("-").rstrip()

    return raw


# Validation

def validate_yaml(path: Path) -> bool:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"  [FAIL] YAML parse error: {e}")
        return False

    errors = []
    for key in ("version", "table", "description", "business_context", "columns", "joins", "metrics"):
        if key not in data:
            errors.append(f"missing top-level key '{key}'")

    for col in data.get("columns") or []:
        for k in ("name", "type", "description", "sample_values"):
            if k not in col:
                errors.append(f"column '{col.get('name', '?')}' missing '{k}'")

    for join in data.get("joins") or []:
        for k in ("to", "type", "condition", "cardinality"):
            if k not in join:
                errors.append(f"join to '{join.get('to', '?')}' missing '{k}'")

    if errors:
        for err in errors:
            print(f"  [WARN] {err}")
        return False

    return True


# Drift check

def drift_check(tables: list[str]):
    """Compare live DB schema against existing YAMLs. No LLM calls, no writes."""
    any_drift = False

    for table_name in tables:
        path = SEMANTIC_DIR / f"{table_name}.yaml"
        if not path.exists():
            print(f"[MISSING] {table_name}.yaml — run builder first")
            continue

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"[ERROR]   {table_name}.yaml — {e}")
            continue

        db_cols   = {c["name"]: c["type"] for c in get_column_schema(table_name)}
        yaml_cols = {c["name"]: c["type"] for c in data.get("columns", [])}

        added   = db_cols.keys() - yaml_cols.keys()
        removed = yaml_cols.keys() - db_cols.keys()
        changed = {
            name for name in db_cols.keys() & yaml_cols.keys()
            if db_cols[name] != yaml_cols[name]
        }

        if not any([added, removed, changed]):
            print(f"[OK]      {table_name}")
            continue

        any_drift = True
        print(f"[DRIFT]   {table_name}")
        for col in sorted(added):
            print(f"            + {col} ({db_cols[col]})  <- new in DB, not in YAML")
        for col in sorted(removed):
            print(f"            - {col}  <- in YAML, no longer in DB")
        for col in sorted(changed):
            print(f"            ~ {col}: YAML={yaml_cols[col]} -> DB={db_cols[col]}")

    if not any_drift:
        print("\nNo schema drift detected.")


# Sync (patch existing YAMLs with drift changes)

def _generate_col_description(table_name: str, col_name: str, col_type: str, samples: list[str]) -> str:
    """Single small LLM call to describe one new column."""
    samples_str = ", ".join(samples) if samples else "no samples available"
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    response = llm.invoke([
        SystemMessage(content="You are a data analyst writing concise column descriptions for a semantic layer. Respond with exactly one sentence — no YAML, no markdown."),
        HumanMessage(content=f"Table: {table_name}\nColumn: {col_name} ({col_type})\nSample values: {samples_str}\n\nDescribe what this column represents."),
    ])
    return response.content.strip().strip('"')


def _col_block(name: str, col_type: str, desc: str, samples: list[str]) -> str:
    """Build a YAML column entry as an indented string block."""
    lines = [
        f"  - name: {name}",
        f"    type: {col_type}",
        f"    description: {desc}",
        f"    sample_values:",
    ]
    for v in samples:
        lines.append(f'      - "{str(v).replace(chr(34), chr(92)+chr(34))}"')
    lines.append("")  # blank line after each entry
    return "\n".join(lines) + "\n"


def _insert_before_joins(text: str, block: str) -> str:
    """Insert a column block just before the # Joins section."""
    for marker in ("# Joins\n", "joins:\n"):
        if marker in text:
            return text.replace(marker, block + marker, 1)
    return text + block  # fallback: append at end


def _remove_col_block(text: str, col_name: str) -> str:
    """Remove a column entry block by name from raw YAML text."""
    start_marker = f"  - name: {col_name}\n"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return text
    search_from = start_idx + len(start_marker)
    end_idx = len(text)
    for marker in ("  - name:", "\n# Joins", "\n# Metrics"):
        pos = text.find(marker, search_from)
        if pos != -1 and pos < end_idx:
            end_idx = pos
    return text[:start_idx] + text[end_idx:]


def sync_yaml(table_name: str) -> bool:
    """Patch an existing YAML with column additions/removals detected from live DB.
    Uses raw text manipulation to preserve all comments and formatting."""
    path = SEMANTIC_DIR / f"{table_name}.yaml"
    if not path.exists():
        print(f"  [SKIP] {table_name}.yaml not found — run builder first")
        return False

    data      = yaml.safe_load(path.read_text(encoding="utf-8"))
    db_schema = get_column_schema(table_name)
    db_cols   = {c["name"]: c["type"] for c in db_schema}
    yaml_cols = {c["name"]: c["type"] for c in data.get("columns", [])}

    added   = sorted(db_cols.keys() - yaml_cols.keys())
    removed = sorted(yaml_cols.keys() - db_cols.keys())

    if not added and not removed:
        print(f"  [OK] no drift")
        return False

    text = path.read_text(encoding="utf-8")

    for col_name in removed:
        text = _remove_col_block(text, col_name)
        print(f"  - removed: {col_name}")

    for col_name in added:
        col_type = db_cols[col_name]
        samples  = get_sample_values(table_name, col_name, n=2)
        desc     = _generate_col_description(table_name, col_name, col_type, samples)
        block    = _col_block(col_name, col_type, desc, samples)
        text     = _insert_before_joins(text, block)
        print(f"  + added:   {col_name} ({col_type})")

    path.write_text(text, encoding="utf-8")
    return True


# Main

def main():
    parser = argparse.ArgumentParser(description="Build YAML semantic layer files from live DB schema.")
    parser.add_argument("--table", help="Target a single table only (by name).")
    parser.add_argument("--validate", action="store_true", help="Validate existing YAMLs without generating.")
    parser.add_argument("--drift-check", action="store_true", help="Compare live DB schema against existing YAMLs and report drift.")
    parser.add_argument("--sync", action="store_true", help="Patch existing YAMLs with column additions/removals from live DB.")
    args = parser.parse_args()

    purposes: dict = yaml.safe_load(PURPOSES_PATH.read_text(encoding="utf-8"))
    tables = [args.table] if args.table else list(purposes.keys())

    if args.drift_check:
        print("Checking for schema drift...\n")
        drift_check(tables)
        return

    if args.sync:
        print("Syncing YAMLs with live DB schema...\n")
        for table_name in tables:
            print(f"{table_name}")
            changed = sync_yaml(table_name)
            if not changed:
                print()
                continue
            print()
        return

    if args.validate:
        print("Validating existing YAML files...\n")
        for table_name in tables:
            path = SEMANTIC_DIR / f"{table_name}.yaml"
            if not path.exists():
                print(f"[MISSING]  {table_name}.yaml")
                continue
            ok = validate_yaml(path)
            print(f"{'[OK]     ' if ok else '[FAIL]   '} {table_name}.yaml")
        return

    SEMANTIC_DIR.mkdir(exist_ok=True)

    for i, table_name in enumerate(tables):
        print(f"\n[{i+1}/{len(tables)}] {table_name}")

        if table_name not in purposes:
            print(f"  [SKIP] '{table_name}' not found in {PURPOSES_PATH} — add a purpose entry first.")
            continue

        print("  ->fetching column schema...")
        columns = get_column_schema(table_name)

        print("  ->sampling column values...")
        for col in columns:
            col["samples"] = get_sample_values(table_name, col["name"])

        print("  ->calling LLM (gpt-4o)...")
        yaml_str = build_yaml_via_llm(table_name, purposes[table_name], columns)

        out_path = SEMANTIC_DIR / f"{table_name}.yaml"
        out_path.write_text(yaml_str, encoding="utf-8")

        ok = validate_yaml(out_path)
        status = "[OK]" if ok else "[WARN] written but has validation issues"
        print(f"  {status} -> {out_path}")

        if i < len(tables) - 1:
            time.sleep(2)  # avoid rate-limit spikes between tables

    print("\nDone.")


if __name__ == "__main__":
    main()
