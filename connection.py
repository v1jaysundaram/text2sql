"""
SQLAlchemy engine and connection utilities.
Supports MySQL (mysqlconnector) and PostgreSQL (psycopg2).
"""

from sqlalchemy import create_engine, text

from config import Config


_db_url = (
    f"{Config.DB_DIALECT}+{Config.DB_DRIVER}://"
    f"{Config.DB_USER}:{Config.DB_PASSWORD}"
    f"@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
)

engine = create_engine(_db_url, echo=False)


def test_connection() -> bool:
    """Ping the database with SELECT 1. Returns True on success."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Connected to '{Config.DB_NAME}' on {Config.DB_HOST}:{Config.DB_PORT}")
        return True
    except Exception as e:
        print(f"[FAILED] Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
