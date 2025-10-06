# Changelog

All notable changes to this project will be documented in this file.  
This project follows a simple versioning approach (v1, v2, ...).

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
