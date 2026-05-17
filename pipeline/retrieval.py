"""
Node 2 — retrieval

Embeds cleaned_query and runs cosine similarity search against the ChromaDB
semantic index to retrieve the top-K most relevant table schemas (YAML files).

No LLM call — one embedding API call (text-embedding-3-small) + local HNSW search.
ChromaDB client and collection are initialized once at module load, not per query.
Writes: retrieved_tables, retrieved_yamls
"""

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config import Config
from pipeline.state import SQLState

_CHROMA_DIR = "chroma_db"
_COLLECTION_NAME = "semantic_tables"
_EMBEDDING_MODEL = "text-embedding-3-small"
_TOP_K = 3

# Loaded once at startup — avoids re-reading the index from disk on every query.
_ef = OpenAIEmbeddingFunction(api_key=Config.OPENAI_API_KEY, model_name=_EMBEDDING_MODEL)
_client = chromadb.PersistentClient(path=_CHROMA_DIR)
_collection = _client.get_collection(name=_COLLECTION_NAME, embedding_function=_ef)


def retrieval(state: SQLState) -> dict:
    collection = _collection
    results = collection.query(query_texts=[state["cleaned_query"]], n_results=_TOP_K)

    metadatas = results["metadatas"][0]
    table_names = [m["table"] for m in metadatas]
    yaml_paths = [m["yaml_path"] for m in metadatas]

    yamls = []
    for path in yaml_paths:
        with open(path, encoding="utf-8") as f:
            yamls.append(f.read())

    return {
        "retrieved_tables": table_names,
        "retrieved_yamls": yamls,
    }
