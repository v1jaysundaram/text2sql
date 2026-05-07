# -------------------------------
# Text-to-SQL (v5)
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
    subquestions: List[str]
    table_mappings: List[List[str]]
    column_selections: List[List[str]]

# Load the knowledge base
with open("kb.json", "r", encoding="utf-8") as f:
        KB = json.load(f)

# Define Nodes

########### Sub Question Generator ########### 
prompt_subq_gen = ChatPromptTemplate.from_messages([
    ("system", """
You are a reasoning assistant within a Text-to-SQL workflow. 
Your purpose is to break down complex analytical user queries into short, clear, and logically ordered sub-questions. 
Each sub-question represents one distinct piece of information required to answer the main query.

You do not generate SQL, table names, or column names. 
Your goal is to extract concise analytical phrases that reflect how a human analyst would reason through the problem.
     
You will be provided with:
- User Query: the main question asked by the user in natural language.

You will output:
- A pure JSON array of concise sub-questions, with no additional explanation or commentary.
"""),

    ("human", """
### Task
Break down the following user query into short, specific sub-questions (phrases).  
Each sub-question should represent one analytical step or piece of information needed to answer the query.

---

### Step-by-Step Rules
1. Keep each sub-question short — ideally a short phrase, not a full question.
2. Use natural analytical phrasing (e.g., "list of customers", "average order value", "number of reviews").
3. Maintain logical order — later sub-questions can depend on earlier ones.
4. Avoid redundancy or rephrasing the same idea.
5. Do not use table names, column names, or SQL keywords.
6. If some detail cannot be inferred from data, ignore it.

### What NOT to do
1. Include SQL Keywords - Don't use SELECT, WHERE, JOIN, etc.
2. Mention Schema - Avoid table or column names.
3. Repeat Ideas - Don't phrase the same logic twice.
4. Write Full Sentences - Keep them short analytical phrases.
    
---
          
### Output Format
Return the sub-questions as a **pure JSON array**, ith no explanation or extra text:
     
["sub-question 1", "sub-question 2", ...]

---
          
### Example

**User Query:**
"List of customers who have bought more than 5 products in the last month using UPI. Also, list the product categories they purchased."

**How to Think:**
1. Identify distinct pieces of required information.
2. Exclude unanswerable or irrelevant parts (e.g., "using UPI" if not supported).
3. Represent each as a short analytical phrase.

**Expected Output:*
["list of customers",
 "total products bought per customer",
 "product categories purchased"]

---
     
### Here is the input:
     
User Query:
{user_query}
""")
])


def subq_gen(state: SQLState) -> SQLState:
     
    chain = prompt_subq_gen | llm

    response = chain.invoke({
        "user_query": state["user_query"]
    })

    raw_output = response.content

    # Guardrail - valid list and non-empty. Fallback: return full user query
    try:
        subquestions = json.loads(raw_output)
        if not isinstance(subquestions, list) or not subquestions:
            raise ValueError
    except Exception:
        print(f"[Guardrail] Invalid subquestion output: {raw_output}")
        subquestions = [state["user_query"]]

    state["subquestions"] = subquestions

    return state


############ Sub-Question Table Mapper ###########

prompt_subq_table_map = ChatPromptTemplate.from_messages([
    ("system", """
You are a table mapping assistant within a Text-to-SQL workflow.
Your task is to map each analytical sub-question to the **single most relevant table** from the provided knowledge base descriptions.
You do NOT generate SQL queries or column names.
Focus solely on reasoning which table best fits each sub-question based on table and column descriptions.

### Inputs
- Sub-Questions: List of sub-questions generated from the user query.
- Knowledge Base: Full knowledge base containing tables and column descriptions.

### Output
- A JSON array of arrays mapping sub-questions to tables, strictly as described in the human prompt.
"""),

    ("human", """
### Task
For each sub-question, select the **single table** from the provided knowledge base that best contains the necessary information.


Guidelines:
1. Only select tables that directly contain or describe data relevant to the sub-question.
2. A table might not fully answer a sub-question but could act as a **linking table** between others — include it only if needed.
3. Prefer concise and minimal mappings — no need to include multiple tables unless conceptually necessary.
4. Do **not** invent or hallucinate tables not listed.
5. Use table names exactly as they appear in the input.
6. Don't include 'json', 'python', or triple backticks (```) in your output.

---
     
### Output Format
Return strictly as a **JSON array of arrays**, with no explanations or extra text.

- Each sublist contains **one or more sub-questions followed by exactly one table name**.
- Use double quotes for all strings.

Examples:

1. Multiple subquestions mapping to different tables:
[["subquestion1", "table_name1"], [""subquestion2", "table_name2"]]

2. Multiple subquestions mapping to the same table:
[["subquestion1", "subquestion2", "table_name"]]

3. Only one valid subquestion:
[["subquestion1", "table_name"]]

4. No valid subquestions:
[[]]
          
---     

### Example

Sub-Questions:
["list of customers", "distinct product ids", "product categories purchased"]

Tables:
- customer: customer_id, customer_unique_id, customer_state
- orders: order_id, customer_id, order_status, order_purchase_timestamp
- products: product_id, product_category_name

Reasoning:
- "list of customers" → maps to "customer"
- "distinct product ids" and "product categories purchased" → maps to "products"
     
Expected Output:
[["list of customers", "customer"], 
 ["distinct product ids", "product categories purchased", "products"]]    
      
---
     
## Here are the inputs:
     
Sub-Questions:
{subquestions}

Knowledge Base:
{KB}
""")
])


def subq_table_map(state: SQLState) -> SQLState:
     
    chain = prompt_subq_table_map | llm

    response = chain.invoke({
        "subquestions": state["subquestions"],
        "KB": KB
    })
     
    # Parse table mappings
    table_mappings = json.loads(response.content.strip())
    state["table_mappings"] = table_mappings

    # Extract unique tables from mappings
    selected_tables = list({entry[-1] for entry in table_mappings if entry})
    state["selected_tables"] = selected_tables

    # Filter the KB for only relevant tables
    filtered_KB = {table: KB[table] for table in selected_tables if table in KB}
    state["filtered_kb"] = filtered_KB

    return state


########### Sub Question Column Selector ###########

prompt_subq_col_select = ChatPromptTemplate.from_messages([
    ("system",""" You are an intelligent column selector within a Text-to-SQL workflow.
Your role is to determine the **minimum necessary set of columns** required to answer each sub-question, using the given table mappings and the filtered knowledge base.

You do not write SQL queries.
You only select and describe relevant columns logically and analytically, based on the given table and column descriptions.

You will be provided with:
- User Question: the main question asked by the user.
- Sub-Questions: analytical sub-questions derived from the main query.
- Table Mappings: mapping of each subquestion to its most relevant table(s).
- Filtered Knowledge Base: filtered list of tables and their column descriptions.

You will output:
- A **pure JSON array of arrays**, where each array contains column names and their descriptions explaining their role in answering the sub-question.
          
"""),

    ("human", '''
### Task
For each sub-question, identify and list only the **columns necessary** to answer it, based on the 'Table Mappings' and 'Filtered Knowledge Base'.

---

### Step-by-Step Rules
1. For each sub-question:
   a. Identify the mapped table(s) using 'Table Mappings'.
   b. Examine only those tables in 'Filtered Knowledge Base' to find relevant columns.
   c. If a column required to answer the subquestion (or main question) is missing, you may include it from another table.
   d. Select **only** the columns directly useful for the subquestion — no extra or irrelevant columns.
2. Always include **unique identifiers** (like `order_id`, `product_id`, `customer_id`) needed to link or aggregate data.
3. Never include the column `customer_unique_id`.
4. For each selected column, include:
   - Column name  
   - Description explaining how it helps answer the subquestion  
   - Example sample values (from 'Filtered Knowledge Base' if available)
5. Avoid redundancy — do not repeat the same column or description multiple times.

---
     
### What NOT to do
1. Don't output SQL, keywords, or code blocks.
2. Don't mention schema, joins, or calculations.
3. Don't hallucinate column names not present in 'Filtered Knowledge Base'.
4. Don't output explanations, notes, or markdown formatting.
5. Don't include 'json', 'python', or triple backticks in your output.

---
     
### Output Format
Return output **strictly** as a JSON array of arrays, where each inner array contains:
- Column name
- Description with reasoning and sample values (if available)

**Example valid output**:
[
  ["column_name_1", "Full description of how it answers the subquestion, sample values: ..."],
  ["column_name_2", "Full description of how it answers the subquestion, sample values: ..."]
]

**Example invalid output**:
```json
[
  ["column_name_1", "Full description ..."],
  ["column_name_2", "Full description ..."]
]
     
### Example:

**Subquestion:**
"Total order value per customer"
     
**Selected Columns:** 
[
    ["item_price", "Price of the item; used to calculate total order value; sample: 10.0"], 
    ["item_quantity", "Number of items purchased; used to calculate total order value; sample: 2"]
]

---
### Here are the inputs:

User Query:
{user_query}

Subquestions:
{subquestions}

Table Mappings:
{table_mappings}

Filtered Knowledge Base:
{filtered_kb}
    ''')
])


def subq_col_select(state: SQLState) -> SQLState:

    chain = prompt_subq_col_select | llm

    response = chain.invoke({
        "filtered_kb": state["filtered_kb"],
        "table_mappings": state["table_mappings"],
        "subquestions": state["subquestions"],
        "user_query": state["user_query"]
        })
     
    column_selections = json.loads(response.content)
    state["column_selections"] = column_selections

    return state

######### SQL Generator ###########

prompt_sql_gen = ChatPromptTemplate.from_messages([
    ("system", """
You are an expert SQL query generator within a Text-to-SQL workflow.
Your role is to construct a single, syntactically correct, and optimized SQL query that answers the given user query.

You do not explain reasoning — you only output the final SQL query.

You will be provided with:
- 'User Query': the user's natural language question.
- 'Table Mappings': mapping of each subquestion to its relevant table(s).
- 'Selected Columns': columns chosen by previous nodes, which are mandatory for traceability and correctness.
- 'Filtered Knowledge Base': filtered table and column metadata, for resolving any ambiguities.
- 'SQL Dialect': specifies the SQL dialect to use (e.g., MySQL, PostgreSQL).

You will output:
- A **single SQL query string** formatted for the specified dialect, with no extra text or explanation.
"""),
    
("human", '''
### Task
Generate a single, syntactically valid SQL query that accurately answers the 'User Query', using only the provided tables and columns.

---

### Step-by-Step Rules
1. Review all **selected columns** — treat them as **mandatory** for inclusion in the final query.
2. Map subquestions to their tables using 'Table Mappings'.
3. If any column is ambiguous or unclear, only then refer to 'Filtered Knowledge Base' to confirm which table it belongs to.
4. Construct the SQL query:
   - Include all mandatory columns in SELECT or logical components.
   - Join tables based on relationships implied in 'Filtered Knowledge Base'.
   - Use proper table aliases for readability.
   - Use aggregation (SUM, AVG, COUNT, etc.) only when necessary and logically consistent.
   - Ensure GROUP BY, HAVING, and ORDER BY clauses are correctly applied.
5. Optimize for clarity and correctness:
   - Use CTEs if the logic becomes complex.
   - Avoid unnecessary subqueries or redundant joins.
6. Output **only the SQL query** — no explanation, code fences, markdown, or commentary.

---

### What NOT to do
1. Do not output explanations, reasoning, or comments.
2. Do not hallucinate any tables or columns not listed in the inputs.
3. Do not assume table ownership of columns without verifying via 'Filtered Knowledge Base'.
4. Do not include SQL dialect setup or connection commands.
5. Do not wrap the SQL in code blocks (```sql``` etc.).
6. Do not use reserved SQL keywords (like 'or', 'and') as aliases.

---

### Output Format
Output must be **only the SQL query**, formatted properly and ready to execute.

**Example of correct output**:
SELECT o.order_id, SUM(p.payment_value) AS total_payment,
       AVG(r.review_score) AS avg_review
FROM olist_orders_dataset o
JOIN olist_order_payments_dataset p ON o.order_id = p.order_id
JOIN olist_order_reviews_dataset r ON o.order_id = r.order_id
GROUP BY o.order_id;

**Example of incorrect output**:
```sql
-- extra formatting or commentary
SELECT ...
 
---
 
### Here are the inputs:

User Question:
{user_query}

SQL Dialect: 
{sql_dialect}

Table Mappings:
{table_mappings}

Selected Columns:
{column_selections}

Filtered Knowledge Base:
{filtered_kb}
''')
])



def sql_gen(state: SQLState) -> SQLState:
     
    chain = prompt_sql_gen | llm

    response = chain.invoke({
        "user_query": state["user_query"],
        "sql_dialect": Config.DB_DIALECT,
        "column_selections": state["column_selections"],
        "table_mappings": state["table_mappings"],
        "filtered_kb": state["filtered_kb"]
    })

    sql_query = response.content
    state["sql_query"] = sql_query

    return state



# Build Workflow
graph = StateGraph(SQLState)

graph.add_node("subq_gen", subq_gen)
graph.add_node("subq_table_map", subq_table_map)
graph.add_node("subq_col_select", subq_col_select)
graph.add_node("sql_gen", sql_gen)


graph.add_edge(START, "subq_gen")
graph.add_edge("subq_gen", "subq_table_map")
graph.add_edge("subq_table_map", "subq_col_select")
graph.add_edge("subq_col_select", "sql_gen")
graph.add_edge("sql_gen", END)

workflow = graph.compile()


"""# Test the workflow

user_query = "What is the correlation between payment value and review score?"

initial_state: SQLState = {
    "user_query": user_query,
    "sql_query": "",
    "selected_tables": [],
    "filtered_kb": {},          
    "subquestions": [],
    "table_mappings": [],
    "column_selections": []
}

# Run the workflow
final_state = workflow.invoke(initial_state)

print(final_state["sql_query"])"""


def run_text2sql(question: str) -> dict:
    """
    Executes the full Text-to-SQL pipeline and returns the final SQL query.
    """


    initial_state: SQLState = {
        "user_query": question,
        "sql_query": "",
        "selected_tables": [],
        "filtered_kb": {},          
        "subquestions": [],
        "table_mappings": [],
        "column_selections": []
    }

    response = workflow.invoke(initial_state)

    return {"answer": response["sql_query"]}

