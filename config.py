"""
Environment variable loading and startup validation.
All os.getenv() calls are centralized here — import Config from this module, never call os.getenv() elsewhere.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Database (Required) ---
    DB_DIALECT = os.getenv("DB_DIALECT")        # mysql | postgresql
    DB_DRIVER = os.getenv("DB_DRIVER")          # mysqlconnector | psycopg2
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")

    # --- LLM (Required) ---
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # --- Observability (Optional) ---
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "text2sql")


    _REQUIRED = [
        "DB_DIALECT", "DB_DRIVER", "DB_USER", "DB_PASSWORD",
        "DB_HOST", "DB_PORT", "DB_NAME",
        "OPENAI_API_KEY",
    ]

    @classmethod
    def _validate(cls):
        missing = [var for var in cls._REQUIRED if not getattr(cls, var)]
        if missing:
            print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
            print("Copy .env.example to .env and fill in the values.")
            sys.exit(1)
        if cls.DB_DIALECT not in ("mysql", "postgresql"):
            print(f"[ERROR] Invalid DB_DIALECT '{cls.DB_DIALECT}'. Must be 'mysql' or 'postgresql'.")
            sys.exit(1)


Config._validate()
