
#knowledge_base.py
"""
Generates annotated descriptions of SQL tables using an LLM workflow.
"""

# Import Libraries
import pandas as pd
import tqdm
import time
from typing import TypedDict
from db import engine  # your DB connection engine
import json
import ast

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END


# Table descriptions
table_description = {
    "olist_customers_dataset": "This dataset has information about the customer and its location. Used to identify unique customers in the orders dataset and to find the orders delivery location. At our system each order is assigned to a unique customer_id. This means that the same customer will get different ids for different orders. The purpose of having a customer_unique_id on the dataset is to allow you to identify customers that made repurchases at the store.",
    
    "olist_geolocation_dataset": "This dataset has information about Brazilian zip codes and its lat/lng coordinates. Used to plot maps and find distances between sellers and customers.",
    
    "olist_order_items_dataset": "This dataset includes data about the items purchased within each order.",
    
    "olist_order_payments_dataset": "This dataset includes data about the orders payment options.",
    
    "olist_order_reviews_dataset": "This dataset includes data about the reviews made by the customers after purchase.",
    
    "olist_orders_dataset": "This is the core dataset containing order-level details linking all other datasets.",
    
    "olist_products_dataset": "This dataset includes data about the products sold by Olist.",
    
    "olist_sellers_dataset": "This dataset includes data about the sellers that fulfilled orders made at Olist.",
    
    "product_category_name_translation": "Translates the product_category_name to English."
}

# Utility function: Fetch sample data
def read_sql_sample(table_name: str, n: int = 5) -> pd.DataFrame:
    """
    Fetch n random rows from the given table, DB-agnostic.

    Args:
        table_name (str): Name of the SQL table to sample.
        n (int): Number of random rows to fetch (default = 5).

    Returns:
        pd.DataFrame: Sampled rows.
    """
    dialect = engine.dialect.name
    if dialect == "mysql":
        rand_func = "RAND()"
    elif dialect == "postgresql":
        rand_func = "RANDOM()"
    else:
        raise ValueError(f"Unsupported DB dialect: {dialect}")

    query = f"SELECT * FROM {table_name} ORDER BY {rand_func} LIMIT {n};"
    df_sample = pd.read_sql(query, con=engine)
    return df_sample


# Model and Prompt Setup
llm = ChatOpenAI()

# LangGraph State
class AnnotatorState(TypedDict):
    description: str
    data_sample: str
    output: str

prompt_template = ChatPromptTemplate.from_messages([
    ("system", """
You are a skilled data annotator. Your task is to generate precise and detailed descriptions for SQL tables and their columns. 
Do not include explanations, commentary, or any extra text—output only what is requested. 

The descriptions you generate will be fed to a text-to-SQL system, so accuracy and nuance are critical. Ensure you capture all meaningful information present in the table structure and data samples.
"""),

    ("human", '''
- Analyze the provided SQL table and sample rows, and generate a detailed description for the table as a whole.  
- For each column, provide:
    * A precise description reflecting its role and data.
    * 1 or 2 representative sample values.  
- Incorporate any hints from the SQL table description into the column descriptions.  
- Avoid generic statements; base descriptions on concrete column details.

Context: Olist is a Brazilian e-commerce platform connecting small businesses to marketplaces. Orders may contain multiple items and sellers.

Output format:
["<table description>", [
    ["<column_1>: description, sample values: v1, v2"],
    ["<column_2>: description, sample values: v1, v2"]
]]

SQL table description:
{description}

Sample rows from the table:
{data_sample}
''')
])

# LangGraph Node
def annotate_node(state: AnnotatorState):
    """Single node that formats prompt → runs LLM → returns annotation output."""
    prompt = prompt_template.invoke({
        "description": state["description"],
        "data_sample": state["data_sample"]
    })
    response = llm.invoke(prompt)
    return {"output": response.content}

# Build Workflow
graph = StateGraph(AnnotatorState)
graph.add_node("annotate", annotate_node)
graph.add_edge(START, "annotate")
graph.add_edge("annotate", END)
workflow = graph.compile()


# Main function to build knowledge base
def build_knowledge_base(save_path: str = "kb.json"):
    """
    Build knowledge base by annotating each table using the workflow and save it to a JSON file.

    Args:
        save_path (str): Path to save the JSON file containing the knowledge base.

    Returns:
        dict: Dictionary of table annotations (all as lists).
    """
    kb = {}

    for table_name, desc in tqdm.tqdm(table_description.items()):
        # Step 1: Sample data
        df = read_sql_sample(table_name)
        df_dict = str(df.to_dict())

        # Step 2: Run workflow
        result = workflow.invoke({
            "description": desc,
            "data_sample": df_dict
        })

        # Step 3: Get output and convert to Python object
        response = result.get("output", "")
        print(response)
        print("=" * 80)

        try:
            # Safely evaluate Python-style literal (list/dict)
            kb[table_name] = ast.literal_eval(response)
        except Exception as e:
            print(f"Failed to parse output for {table_name}: {e}")
            kb[table_name] = []

        # Pause to avoid rate limits
        time.sleep(5)

    # Step 4: Save to JSON
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=4, ensure_ascii=False)

    print(f"Knowledge base saved to {save_path}")
    return kb


build_knowledge_base()