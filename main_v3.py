# -------------------------------
# Text-to-SQL (v3)
# -------------------------------

# Import Libraries
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
import json

# Load environment variables
load_dotenv()  

# Initialize the LLM
#llm = ChatOllama(model="sqlcoder")
llm = ChatOpenAI()

# Load the knowledge base
with open("kb.json", "r", encoding="utf-8") as f:
    KB = json.load(f)

# Prompt Template
prompt = f"""
You are a SQL assistant. Given the schema below, generate a valid SQL query for the question in the given dialect. 
Output only the SQL query, nothing else.

Dialect: MySQL 

Schema:
{KB}

Question:
"For each state, show the number of orders, average review score, and total payment."
"""

# Invoke the LLM
response = llm.invoke(prompt)

print(response.content)

