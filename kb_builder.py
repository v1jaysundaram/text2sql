
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

# Fetch sample data
def read_sql_sample(table_name: str) -> pd.DataFrame:

    dialect = engine.dialect.name
    if dialect == "mysql":
        rand_func = "RAND()"
    elif dialect == "postgresql":
        rand_func = "RANDOM()"
    else:
        raise ValueError(f"Unsupported DB dialect: {dialect}")

    query = f"SELECT * FROM {table_name} ORDER BY {rand_func} LIMIT 5;"
    df_sample = pd.read_sql(query, con=engine)
    return df_sample


# Model and Prompt Setup
llm = ChatOpenAI()

# LangGraph State
class AnnotatorState(TypedDict):
    description: str
    data_sample: str
    output: str

####### Annotate Tables ##########

prompt_annotate = ChatPromptTemplate.from_messages([
    ("system", """
You are a skilled data annotator. Your task is to generate structured descriptions for SQL tables and their columns.
The descriptions will be used by a Text-to-SQL system.

Do NOT include commentary or explanations—return only the requested structured output.
"""),

    ("human", '''
Analyze the SQL table and its sample rows. Generate the following **in a fixed format**:

1. **Table description**: 
   - Must **always** start with: "Table represents <what the table is about> (includes <important columns>)".
   - Only include **important columns** in the parentheses. Trivial columns like IDs or timestamps can be **omitted** unless essential.

2. **Columns list**:
   - Include **all columns** present in the table.
   - For each column:
       * Give a detailed description of what it represents and the data type.
       * Include 1 or 2 representative values from the sample rows.

Context: These tables are provided by Olist, the largest department store in Brazilian marketplaces. It's an e-commerce platform connecting small businesses to marketplaces.

Output should strictly look like below in form of list of list of strings.
MAKE SURE YOU ALWAYS CLOSE THE QUOTES in list of strings properly.
Do not include any extra text, or symbols in the start like - python, sql
     
[
  "<table description based on all column value>",
  [
    ["<column_1>: detail description of column along with datatype, sample values: v1, v2"], 
    ["<column_2>: detail description of column along with datatype, sample values: v1, v2"]
    ...
  ]
]

SQL table description:
{description}

Sample rows from the table:
{data_sample}
''')
])



def annotate_node(state: AnnotatorState):

    chain = prompt_annotate | llm
    
    response  = chain.invoke({
        "description": state["description"],
        "data_sample": state["data_sample"]
    })

    state["output"] = response.content
    return state

# Build Workflow
graph = StateGraph(AnnotatorState)

graph.add_node("annotate", annotate_node)

graph.add_edge(START, "annotate") 
graph.add_edge("annotate", END)

workflow = graph.compile()


# Main function to build knowledge base
def build_knowledge_base(save_path: str = "kb.json"):

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
        response = result.get("output", "").replace('```', '')
        print(response)
        print("=" * 80)

        kb[table_name] = eval(response)

        # Pause to avoid rate limits
        time.sleep(5)

    # Step 4: Save to JSON
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=4, ensure_ascii=False)

    print(f"Knowledge base saved to {save_path}")
    return kb


build_knowledge_base()