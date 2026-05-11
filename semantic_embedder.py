"""
One-time indexer: reads semantic YAML files, embeds description + business_context,
and upserts into a local ChromaDB collection for retrieval at query time.

Commands:
    python semantic_embedder.py           # embed / re-embed all tables
    python semantic_embedder.py --reset   # delete collection and re-embed
"""

import argparse
from pathlib import Path

import yaml
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config import Config

SEMANTIC_DIR = Path("semantic")
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "semantic_tables"
SKIP_FILES = {"template.yaml", "test.yaml"}
EMBEDDING_MODEL = "text-embedding-3-small"


# ChromaDB

def _get_client_and_ef():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = OpenAIEmbeddingFunction(api_key=Config.OPENAI_API_KEY, model_name=EMBEDDING_MODEL)
    return client, ef


# Embedding

def embed_all(reset: bool = False):
    client, ef = _get_client_and_ef()
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)

    yaml_files = sorted(f for f in SEMANTIC_DIR.glob("*.yaml") if f.name not in SKIP_FILES)
    for path in yaml_files:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        table = data["table"]
        description = (data.get("description") or "").strip()
        business_context = (data.get("business_context") or "").strip()
        document = f"{description}\n\n{business_context}"
        collection.upsert(
            ids=[table],
            documents=[document],
            metadatas=[{"table": table, "yaml_path": str(path)}],
        )
        print(f"Embedded: {table}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed semantic YAML frontmatter into ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Delete and re-create the collection before embedding")
    args = parser.parse_args()
    embed_all(reset=args.reset)
