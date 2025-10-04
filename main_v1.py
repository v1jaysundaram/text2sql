# -------------------------------
# Text-to-SQL (v1)
# -------------------------------

# Import Libraries
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()  

# Initialize the LLM
#llm = ChatOllama(model="sqlcoder")
llm = ChatOpenAI()

# Prompt Template
prompt = """
You are a SQL assistant. Given the schema below, generate a valid SQL query for the question in the given dialect. Output only the SQL query, nothing else.

Dialect: MySQL 

Schema:
XXXXXXXXXXXXXXXXXXXXXXXX

Question:
XXXXXXXXXXXXXXXXXXXXXXXX
"""

# Invoke the LLM
response = llm.invoke(prompt)

print(response.content)
