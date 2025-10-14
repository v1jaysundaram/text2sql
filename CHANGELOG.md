# Changelog

All notable changes to this project will be documented in this file.  
This project follows a simple versioning approach (v1, v2, ...).

---

## [v5] - 2025-10-14

### Changed
## [v5] - 2025-10-14

### Changed
## [v5] - 2025-10-14

### Changed

- Removed the Table Router Agent because it was not always picking the right tables and added extra steps unnecessarily.  
- Added new LLM nodes for:  
  - Subquestion Generation — breaks a user query into smaller, clear subquestions.  
  - Subquestion → Table Mapping — links each subquestion to the correct table.  
  - Column Selection — picks only the columns needed for each subquestion, with explanations and sample values.  
- Simplified and standardized all prompts:  
  - Clear structure for system and human messages.  
  - Defined input/output format using strict JSON. 
  
---

## [v4.1] - 2025-10-08
### Added

- Enhanced Knowledge Base Builder (kb_builder.py) to include more detailed context:

    - Table descriptions now include key columns, but less important ones may be ignored in table summary.

    - Column-level descriptions now always contain all meaningful columns, data types with representative sample values.

---

## [v4] - 2025-10-07
### Added

- Introduced a Router Agent that filters the Knowledge Base to select only the relevant tables needed to answer each query.

### Changed

- Moved SQL dialect configuration from user input to a direct injection within the SQL Generator.

---

## [v3] - 2025-10-06
### Added

- Implemented kb_builder.py to automate knowledge base creation, annotation, and saving.
- Introduced kb.json, a structured knowledge base generated using LLM-based annotation of each SQL table.
- Each table entry now includes:
  - A detailed table description
  - Column-level descriptions with example values

### Changed

- Replaced the static schema import (schema_v2.py) with the dynamic knowledge base (kb.json) for richer SQL generation context.

---

## [v2] - 2025-09-28
### Added
- Introduced `schema_v2.py` to store and import full schema details (table names and columns) directly.
- Prompt now automatically includes schema from the imported file — no need for manual input each time.

### Changed
- Simplified main script to reference the schema file instead of embedding raw schema text.

---

## [v1] - 2025-09-28
### Added
- Initial working prototype for Text-to-SQL conversion.
- User manually provides:
  - Schema (table names and columns)
  - Query question
  - SQL dialect (e.g., MySQL)
- Integrated basic LLM call using `ChatOpenAI` to generate SQL queries.
- Database support scripts:
  - `db.py` – Creates SQLAlchemy engine and manages database connection (for local setup/testing).
  - `csv_loader.py` – Loads CSV files into SQL tables for testing queries.
