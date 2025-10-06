# db.py
"""
Database connection setup.
Supports MySQL and PostgreSQL only.
"""

# Import Libraries
from sqlalchemy import create_engine, text
from config import Config

# Check if the dialect is valid
if Config.DB_DIALECT not in ["mysql", "postgresql"]:
    raise ValueError("❌ Only 'mysql' and 'postgresql' are supported as DB_DIALECT")

# Build SQLAlchemy DB URL dynamically
db_url = f"{Config.DB_DIALECT}+{Config.DB_DRIVER}://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"

engine = create_engine(db_url, echo=False)  # echo=True prints SQL queries for debugging

def create_database():
    """
    Create database if it doesn't exist (MySQL/PostgreSQL).
    Call this only once at the beginning.
    """
    temp_url = f"{Config.DB_DIALECT}+{Config.DB_DRIVER}://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}/"
    temp_engine = create_engine(temp_url)

    with temp_engine.connect() as conn:
        if Config.DB_DIALECT == "mysql":
            # MySQL supports IF NOT EXISTS
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}"))
            
        elif Config.DB_DIALECT == "postgresql":
            # PostgreSQL does NOT support IF NOT EXISTS in CREATE DATABASE
            try:
                conn.execute(text(f"CREATE DATABASE {Config.DB_NAME}"))
            except Exception as e:
                print(f"⚠️ Database may already exist: {e}")
        print(f"✅ Database '{Config.DB_NAME}' is ready.")

# create DB (uncomment only first time)
#create_database()
