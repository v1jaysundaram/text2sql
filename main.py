"""
Text-to-SQL entry point: embeds the user question, retrieves relevant table YAMLs
from ChromaDB, and calls the LLM with full schema context to generate SQL.
"""

from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from langchain_openai import ChatOpenAI

from config import Config

TOP_K = 3
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "semantic_tables"
EMBEDDING_MODEL = "text-embedding-3-small"


# ChromaDB

def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = OpenAIEmbeddingFunction(api_key=Config.OPENAI_API_KEY, model_name=EMBEDDING_MODEL)
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def _retrieve_yaml_context(question: str) -> str:
    collection = _get_collection()
    results = collection.query(query_texts=[question], n_results=TOP_K)
    yaml_paths = [meta["yaml_path"] for meta in results["metadatas"][0]]
    parts = []
    for path in yaml_paths:
        with open(path, encoding="utf-8") as f:
            parts.append(f.read())
    return "\n---\n".join(parts)


# Pipeline

def run_text2sql(question: str) -> str:
    llm = ChatOpenAI()
    yaml_context = _retrieve_yaml_context(question)
    prompt = f"""You are a SQL assistant. Given the schema context below, generate a valid SQL query for the question. Output only the SQL query, nothing else.

Dialect: {Config.DB_DIALECT}

Schema Context:
{yaml_context}

Question:
{question}"""
    response = llm.invoke(prompt)
    return response.content


if __name__ == "__main__":
    question = "How many customers are there in the state of Minas Gerais?"
    sql = run_text2sql(question)
    print(sql)
