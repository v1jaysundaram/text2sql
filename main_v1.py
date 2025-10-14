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
olist_customers_dataset - customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state

olist_order_payments_dataset - order_id, payment_sequential, payment_type, payment_installments, payment_value

olist_order_reviews_dataset - review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp

olist_orders_dataset - order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date

Question:
For each state, show the number of orders, average review score, and total payment.
"""

# Invoke the LLM
response = llm.invoke(prompt)

print(response.content)
