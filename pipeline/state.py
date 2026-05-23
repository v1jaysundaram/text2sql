"""
Shared LangGraph state for the Text-to-SQL pipeline.

Each node reads upstream fields and writes only its own output fields.
Add new fields here when a new node is introduced.
"""

from typing import List
from typing_extensions import TypedDict


class SQLState(TypedDict):
    # input
    original_query: str

    # query_prep
    cleaned_query: str          # typos + grammar corrected, whitespace normalized
    retrieval_queries: List[str]  # concept phrases for multi-query ChromaDB retrieval

    # retrieval
    retrieved_tables: List[str]
    retrieved_yamls: List[str]  # raw YAML content strings

    # verifier
    verified_tables: List[str]
    verified_yamls: List[str]
    verifier_reasoning: str
    verifier_sufficiency: str   # "sufficient" | "partial" | ""
    suggested_search_terms: List[str]
    error_message: str

    # retry control
    retry_count: int

    # sql_gen
    sql_query: str
