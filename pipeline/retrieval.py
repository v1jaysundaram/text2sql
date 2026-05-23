"""
Node 2 — retrieval

Runs one ChromaDB cosine similarity search per concept phrase from retrieval_queries
(produced by query_prep). Results are deduplicated by table name (first-seen wins);
all unique tables are forwarded to the verifier for relevance filtering.
Falls back to cleaned_query if retrieval_queries is empty.

No LLM call — embedding API calls (text-embedding-3-small) + local HNSW search.
ChromaDB client and collection are initialized once at module load.
Reads:  retrieval_queries, cleaned_query
Writes: retrieved_tables, retrieved_yamls
"""

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config import Config
from pipeline.state import SQLState

_CHROMA_DIR = "chroma_db"
_COLLECTION_NAME = "semantic_tables"
_EMBEDDING_MODEL = "text-embedding-3-small"
_TOP_K = 3  # per concept query

# Loaded once at startup — avoids re-reading the index from disk on every query.
_ef = OpenAIEmbeddingFunction(api_key=Config.OPENAI_API_KEY, model_name=_EMBEDDING_MODEL)
_client = chromadb.PersistentClient(path=_CHROMA_DIR)
_collection = _client.get_collection(name=_COLLECTION_NAME, embedding_function=_ef)


def retrieval(state: SQLState) -> dict:
    queries = state.get("retrieval_queries") or [state["cleaned_query"]]

    seen: dict[str, str] = {}  # table_name → yaml_path, insertion-ordered dedup
    for q in queries:
        results = _collection.query(
            query_texts=[q],
            n_results=_TOP_K,
            include=["metadatas"],
        )
        for meta in results["metadatas"][0]:
            table = meta["table"]
            if table not in seen:
                seen[table] = meta["yaml_path"]

    table_names, yamls = [], []
    for table_name, yaml_path in seen.items():
        table_names.append(table_name)
        with open(yaml_path, encoding="utf-8") as f:
            yamls.append(f.read())

    return {
        "retrieved_tables": table_names,
        "retrieved_yamls": yamls,
    }
