# Changelog

All notable changes to this project are documented in this file.  
This project follows a simple versioning approach (v1, v2, ...).

---

## [v2.3] - 2026-05-23

### Changed

- **`pipeline/query_prep.py`** — CORRECT mode now outputs two fields: `cleaned_query` (typo correction, unchanged intent) and `retrieval_queries` (3–6 short concept phrases extracted from the question). These concept phrases are the primary retrieval signal — each becomes a separate ChromaDB query. REWRITE mode replaced with EXTEND mode: no LLM call on retry; existing `retrieval_queries` are extended in Python by appending the verifier's `suggested_search_terms`. Rewriting the query text is unnecessary since ChromaDB is driven by concept phrases, not the sentence. Renamed `_CorrectedQuery` → `_PrepOutput`, `_CORRECT_SYSTEM_PROMPT` → `_SYSTEM_PROMPT`.

- **`pipeline/retrieval.py`** — Multi-concept retrieval replaces single-query lookup. Queries ChromaDB once per concept phrase in `retrieval_queries` (TOP_K=3 per phrase). Results are deduplicated by table name — first-seen wins — and all unique tables are forwarded to the verifier. This widens the candidate pool from a fixed 3 to typically 6–10 unique tables, dramatically reducing partial-match failures on multi-concept questions.

- **`pipeline/verifier.py`** — Added `sufficiency: Literal["sufficient", "partial"]` to `VerifierOutput`. The verifier now performs a two-pass check in one LLM call: (1) filter irrelevant tables, (2) check whether the selected tables' descriptions collectively cover all concepts in `retrieval_queries`. Sets `partial` and populates `suggested_search_terms` when a concept is completely absent from all selected descriptions — not just when no tables are found. Updated system prompt: semantic layer is source of truth; if a description mentions a concept, trust it — column-level check is a later node's job. Concept list (`retrieval_queries`) is passed alongside `cleaned_query` so the sufficiency check is against the exact concepts that drove retrieval.

- **`pipeline/sql_gen.py`** — Now reads `verified_yamls` directly instead of `schema_plan`. Raw YAML content (columns, join conditions, metrics) is passed as-is with a system/user message split for stronger instruction following. Empty `verified_yamls` guard added.

- **`pipeline/state.py`** — Added `retrieval_queries: List[str]` and `verifier_sufficiency: str`. Removed `schema_plan` and all `context_fetch_*` fields (node deferred to Phase 2).

- **`main.py`** — `context_fetch` removed from active graph. Pipeline is now 4 nodes: `query_prep → retrieval → verifier → sql_gen`. Updated `_route_from_verifier`: routes to `query_prep` when verifier returns no tables OR `verifier_sufficiency == "partial"` (under retry ceiling); routes to `sql_gen` otherwise. `initial_state` and error surfacing updated accordingly.

### Preserved

- `pipeline/context_fetch.py` — built but excluded from active pipeline. Reserved for Phase 2 where it will serve as the final authoritative completeness check (full column-level schema plan, `SchemaPlan` structured output).

### Architectural Note

The concept extraction in `query_prep` is the primary defence against partial-match failures — each data concept the question requires gets its own retrieval shot. The verifier provides a best-effort sufficiency check using frontmatter alone; `context_fetch` (Phase 2) remains the authoritative check once full YAML column lists are in scope.

---
## [v2.2] - 2026-05-18

### Added

- Add `pipeline/verifier.py` — Node 3 (inserted between retrieval and sql_gen). LLM-powered gatekeeper that reads YAML frontmatter (table name, description, business context — no columns) for each retrieved table and reasons about which are truly required to answer the question. Returns `verified_tables` and `verified_yamls` (full YAML preserved for downstream nodes) for the confirmed subset.

- Add retry-with-rewrite loop: when the verifier finds no relevant tables it returns `suggested_search_terms` and `verifier_reasoning`. `query_prep` detects this feedback and switches to REWRITE mode — rewrites `original_query` to be more precise using the suggested terms, then re-runs retrieval and verification. Capped at 2 retries; exits gracefully with a user-facing error message on exhaustion.

### Changed

- Extend `pipeline/state.py` with six new fields: `verified_tables`, `verified_yamls`, `verifier_reasoning`, `suggested_search_terms`, `error_message`, `retry_count`.

- Upgrade `pipeline/query_prep.py` to two-mode operation: CORRECT mode (default, first pass — typo correction only) and REWRITE mode (triggered by non-empty `suggested_search_terms` — rewrites query using verifier feedback and increments `retry_count`). Two separate module-level LLM chains, one per Pydantic output schema.

- Update `pipeline/sql_gen.py` to read from `verified_yamls` instead of `retrieved_yamls`. Promote `ChatOpenAI` instantiation to module level (was incorrectly inside the node function).

- Bump `retrieval.py` `_TOP_K` from 3 to 5 — gives verifier a wider candidate set to filter from (9 tables total in semantic index).

- Rewire `main.py` graph: `retrieval → verifier → [conditional]` replaces the direct `retrieval → sql_gen` edge. Conditional router sends to `sql_gen` (tables verified), `query_prep` (retry), or `END` (exhausted). Fix `initial_state` bug where `llm_model_used` was set but not defined in `SQLState`.

### Architectural Note

The verifier operates at table-level semantic granularity only — it matches table purpose against question intent but has no visibility into column definitions. A question requiring data the dataset doesn't contain (e.g. a column that doesn't exist) may pass the verifier with a partial table match. Column-level validation and out-of-scope detection are the responsibility of `context_fetch` (Phase 2, next node), which receives the full YAML including all column definitions.

---

## [v2.1] - 2026-05-17

### Added

- Introduce `pipeline/` module as the foundation for the Phase 2 LangGraph pipeline, replacing the single-function `main.py` approach.

- Add `pipeline/state.py` — shared `SQLState` TypedDict defining all inter-node fields. Each node reads upstream fields and writes only its own outputs, keeping state transitions explicit and traceable.

- Add `pipeline/query_prep.py` — Node 1. Corrects typos and minor grammatical errors (spelling, subject-verb agreement, pluralization, missing articles) using `gpt-4o-mini` structured output. Preserves meaning exactly — no rephrasing or intent inference. Input length check and HITL ambiguity redirection deferred to Phase 3.

- Add `pipeline/retrieval.py` — Node 2. Embeds the cleaned query via `text-embedding-3-small` and runs cosine similarity search against the ChromaDB semantic index. ChromaDB client is initialised once at module load (not per query) to avoid repeated index reads from disk. Returns top-K table names and full YAML content.

- Add `pipeline/sql_gen.py` — Node 3. Generates SQL from retrieved YAML schema context using `gpt-4o-mini`. Single model for now; multi-model routing will be added in Phase 2 once `context_fetch` provides accurate complexity signal.

### Changed

- Rebuild `main.py` as a LangGraph `StateGraph` assembling the three pipeline nodes (`query_prep → retrieval → sql_gen`) with a clean `run_text2sql(question, debug)` entry point.

### Architectural Note

Intent and complexity classification (join count, aggregation, window functions) was intentionally removed from `query_prep`. Surface-level language is not a reliable signal — complexity can only be accurately determined after schema retrieval and table verification in `context_fetch` (Phase 2). Classification and multi-model routing will be added at that stage.

---
## [v2.0] - 2026-05-11

### Added

- Introduce `semantic/` directory with one YAML file per table containing description, business context, column metadata, join paths, and metrics — replaces `kb.json` as the schema knowledge base.

- Add `semantic_builder.py` to automate YAML generation: introspects live DB schema via `INFORMATION_SCHEMA`, samples column values, and calls GPT-4o once per table to produce structured YAML files.

- Add `--validate`, `--drift-check`, and `--sync` flags to `semantic_builder.py` for ongoing maintenance: validate YAML structure, detect schema changes in the live DB, and patch existing YAMLs without overwriting manual edits.

- Add `semantic_embedder.py` to index YAML frontmatter (description + business_context) into a local ChromaDB vector store using `text-embedding-3-small` embeddings.

- Add `main.py` as the new pipeline entry point: embeds the user question, retrieves top-K relevant table YAMLs via cosine similarity search, and calls the LLM with full YAML context to generate SQL — replacing the 5-node LangGraph workflow.

### Changed

- Replace `kb.json` flat knowledge base with per-table YAML files that include join paths and business-level metrics, enabling richer and more accurate SQL generation context.

- Replace LLM-based table mapping and column selection nodes (Nodes 2 and 3 in v6) with embedding-based retrieval, reducing token usage by ~40%.

### Removed

- `kb.json` and `kb_builder.py` — superseded by the YAML semantic layer and `semantic_builder.py`.

### Archived

- All v1.0 series files moved to `archive/`: `main_v1.py` through `main_v6.py`, `schema_v1.txt`, `schema_v2.py`, `kb.json`, `kb_builder.py`, `db.py`, `csv_loader.py`, `test_eval.ipynb`, `test_db.ipynb` — retained for reference, no longer part of the active codebase.

---
## [v6] - 2025-11-23

### Added

- Introduce a SQL Validation & Cleanup node within the Text-to-SQL workflow to ensure queries generated by previous nodes are executable, logically valid, and structurally clean.

- Automatically fixes join types (defaults to LEFT JOIN unless INNER JOIN is clearly required).

- Checks for complex nested subqueries and converts to CTEs where appropriate.

- Adds sensible ORDER BY clauses when implied by trends, rankings, or time sequences using existing SELECT columns only.

- Preserves all columns, tables, filter values, and expressions from the previous SQL node without modification.

- Cleans formatting, indentation, and removes any stray symbols or markdown artifacts.

- Update run_text2sql() wrapper in the main workflow to support both Local testing and LanSmith evaluation.


### Changed

- Change test_eval.py to test_eval.ipynb, to combine local testing and LangSmith evaluation flows, using a single wrapper function.

- Local and LangSmith evaluation now use the same code path, eliminating duplicated logic.

### Removed

Separate code logic for local testing and LangSmith evaluation.

---

## [v5.1] - 2025-11-19

### Added

- Introduce a test_dataset containing 17 golden question–answer pairs covering core SQL patterns (filters, joins, aggregations, window functions, and edge cases).

- Add a dedicated run_text2sql() wrapper function to cleanly execute the full workflow and return only the final SQL output.

- Create a standalone test_eval.py script for running LangSmith evaluations using the golden dataset, enabling quick regression checks and automated evaluation runs.

---

## [v5] - 2025-10-14

### Changed

- Remove the Table Router Agent because it does not always pick the right tables and adds extra steps unnecessarily.  
- Add new LLM nodes for:  
  - Subquestion Generation — break a user query into smaller, clear subquestions.  
  - Subquestion → Table Mapping — link each subquestion to the correct table.  
  - Column Selection — pick only the columns needed for each subquestion, with explanations and sample values.  
- Simplify and standardize all prompts:  
  - Clear structure for system and human messages.  
  - Define input/output format using strict JSON. 
  
---

## [v4.1] - 2025-10-08

### Added

- Enhance Knowledge Base Builder (kb_builder.py) to include more detailed context:

    - Table descriptions now include key columns, but less important ones may be ignored in table summary.

    - Column-level descriptions now always contain all meaningful columns, data types with representative sample values.

---

## [v4] - 2025-10-07

### Added

- Introduce a Router Agent that filters the Knowledge Base to select only the relevant tables needed to answer each query.

### Changed

- Move SQL dialect configuration from user input to a direct injection within the SQL Generator.

---

## [v3] - 2025-10-06

### Added

- Implement kb_builder.py to automate knowledge base creation, annotation, and saving.
- Introduce kb.json, a structured knowledge base generated using LLM-based annotation of each SQL table.
- Each table entry now includes:
  - A detailed table description
  - Column-level descriptions with example values

### Changed

- Replace the static schema import (schema_v2.py) with the dynamic knowledge base (kb.json) for richer SQL generation context.

---

## [v2] - 2025-09-28

### Added
- Introduce `schema_v2.py` to store and import full schema details (table names and columns) directly.
- Prompt now automatically includes schema from the imported file — no need for manual input each time.

### Changed
- Simplify main script to reference the schema file instead of embedding raw schema text.

---

## [v1] - 2025-09-28

### Added
- Create initial working prototype for Text-to-SQL conversion.
- User manually provides:
  - Schema (table names and columns)
  - Query question
  - SQL dialect (e.g., MySQL)
- Integrate basic LLM call using `ChatOpenAI` to generate SQL queries.
- Database support scripts:
  - `db.py` – Create SQLAlchemy engine and manage database connection (for local setup/testing).
  - `csv_loader.py` – Load CSV files into SQL tables for testing queries.
