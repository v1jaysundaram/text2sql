import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Database Settings ---
    DB_DIALECT = os.getenv("DB_DIALECT")                  # mysql or postgresql
    DB_DRIVER = os.getenv("DB_DRIVER")                    # mysqlconnector or psycopg2
    DB_USER = os.getenv("DB_USER")                        # database username
    DB_PASSWORD = os.getenv("DB_PASSWORD")                # database password
    DB_HOST = os.getenv("DB_HOST")                        # usually localhost
    DB_PORT = os.getenv("DB_PORT")                        # 3306 for MySQL, 5432 for PostgreSQL
    DB_NAME = os.getenv("DB_NAME")                        # database name


    # --- Data Settings ---
    DATA_PATH = os.getenv("DATA_PATH") # folder containing CSV files
    CSV_CHUNK_SIZE = int(os.getenv("CSV_CHUNK_SIZE")) # number of rows to read per chunk
