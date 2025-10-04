# csv_loader.py
"""
Load CSV files into the database (MySQL or PostgreSQL) using SQLAlchemy engine.
"""
import os
import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from db import engine  # engine from db.py, DB-agnostic
from config import Config
import logging


def load_csvs_to_db(folder_path=None, chunk_size=None):
    """
    Load all CSV files from a folder into database tables using SQLAlchemy engine.

    Args:
        folder_path (str): Folder containing CSV files. Defaults to Config.DATA_PATH.
        chunk_size (int): Number of rows to read per chunk. Defaults to Config.CSV_CHUNK_SIZE.
    """
    folder_path = folder_path or Config.DATA_PATH
    chunk_size = chunk_size or Config.CSV_CHUNK_SIZE

    # List all CSV files in the folder
    csv_files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
    
    if not csv_files:
        print("No CSV files found in folder:", folder_path)
        return

    print(f"Found {len(csv_files)} CSV files. Starting import...\n")

    # Process each CSV file
    for file in csv_files:
        table_name = os.path.splitext(file)[0]  # table name = file name without extension
        file_path = os.path.join(folder_path, file)
        total_rows = 0  # Track rows loaded per file

        try:
            # Read CSV in chunks for memory efficiency
            for chunk in pd.read_csv(file_path, chunksize=chunk_size):
                with engine.begin() as conn:  # Commit automatically, rollback if error
                    chunk.to_sql(
                        name=table_name,
                        con=conn,
                        index=False,
                        if_exists='append',  # 'append' or 'replace'
                        method='multi'  # Insert multiple rows per query
                    )
                    total_rows += len(chunk)  # Update row count

            # Print per-file summary after all chunks loaded
            print(f"✅ Successfully loaded '{file}' ({total_rows} rows) into table '{table_name}'\n")

        except SQLAlchemyError as e:
            print(f"❌ SQLAlchemy error for '{file}': {e}\n")
        except Exception as e:
            print(f"❌ Unexpected error for '{file}': {e}\n")

# Load all CSVs from the default folder
load_csvs_to_db()