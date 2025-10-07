# -------------------------------
# Text-to-SQL (v4)
# -------------------------------

# Import Libraries
from typing import TypedDict, List
import json
from dotenv import load_dotenv
from config import Config

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

# Load environment variables
load_dotenv()  

# Initialize the LLM
#llm = ChatOllama(model="sqlcoder")
llm = ChatOpenAI()


# Define State  
class SQLState(TypedDict):
    user_query: str
    sql_query: str
    selected_tables: List[str]
    filtered_kb: dict


# Load the knowledge base
with open("kb.json", "r", encoding="utf-8") as f:
        KB = json.load(f)
    
# Extract table descriptions
table_descriptions = {table: value[0] for table, value in KB.items()}


# Prompt Templates

# Router Prompt
router_template = ChatPromptTemplate.from_messages([
    ("system", "You are a concise router for a Text-to-SQL system. Given a user query and table descriptions, return only a JSON array of the table names that are relevant to answer the question. Do not include any explanation or extra text; output must be a JSON array only."),

    ("human", '''
Below are table descriptions:
{table_descriptions}

Instructions:
1. Split the question into sub-questions.
2. For each sub-question, check every table description carefully and decide which tables contain the required data.
3. Return a compact list of unique table names that together answer the full question.
4. Output must be a JSON array of strings, e.g. ["tableA","tableB"]. Nothing else.

User question:
{question}
''')
])


# SQL Generation Prompt Template

sqlgen_template = ChatPromptTemplate.from_messages([
    ("system", """
You are a expert SQL assistant. Given the schema below, generate a logically valid SQL query for the user question in the given dialect. 
Output only the SQL query, no headers nothing.        
 
"""),

    ("human", """
Schema: {filtered_kb}

SQL Dialect: {sql_dialect}   

     
Instructions:
- Use DISTINCT if counting unique values.
- Use only the tables listed above.
- Consider the table columns and example values.


User question:
{user_query}
""")
])


# Define Nodes

# Router Agent
def router_agent(state: SQLState) -> SQLState:

    router_chain = router_template | llm
   
    # Invoke the router chain
    response = router_chain.invoke({
        "table_descriptions": json.dumps(table_descriptions),
        "question": state["user_query"]
    })

    # Parse the JSON array of selected table names
    selected_tables = json.loads(response.content)
    state["selected_tables"] = selected_tables

    # Collect descriptions for selected tables including columns
    filtered_kb = {
        table: {
        "description": KB[table][0],     # Table-level description
        "columns": KB[table][1]          # Column-level details (list of lists)
        }
    for table in selected_tables
    }

    state["filtered_kb"] = filtered_kb

    return state


# SQL Generator
def sql_generator(state: SQLState) -> SQLState:
     
    sql_chain = sqlgen_template | llm

    response = sql_chain.invoke({
        "filtered_kb": state["filtered_kb"],
        "user_query": state["user_query"],
        "sql_dialect": Config.DB_DIALECT 
    })

    # Extract the SQL query from response
    state["sql_query"] = response.content

    return state


# Build Workflow
graph = StateGraph(SQLState)

graph.add_node("router_agent", router_agent)
graph.add_node("sql_generator", sql_generator)

graph.add_edge(START, "router_agent")
graph.add_edge("router_agent", "sql_generator")
graph.add_edge("sql_generator", END)

workflow = graph.compile()

# Test the workflow

user_query = "Which sellers have sold products in more than 3 different categories?"

# Initial state
test_state: SQLState = {
    "user_query": user_query,
    "sql_query": "",
    "selected_tables": [],
    "filtered_kb": {}
}

# Run the full workflow
final_state = workflow.invoke(test_state)

print(final_state["sql_query"])


    