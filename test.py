from main_v5 import subq_gen, subq_table_map, subq_col_select, sql_gen, Config
import json
########### Test ###########
test_state = {
    "user_query": "For each state, show the number of orders, average review score, and total payment.",
    
    
    "subquestions": ['list of states', 'number of orders per state', 'average review score per state', 'total payment per state'],

    "table_mappings": [['list of states', 'olist_customers_dataset'], ['number of orders per state', 'olist_orders_dataset'], ['average review score per state', 'olist_order_reviews_dataset'], ['total payment per state', 'olist_order_payments_dataset']],

    "selected_tables": ['olist_orders_dataset', 'olist_order_payments_dataset', 'olist_customers_dataset', 'olist_order_reviews_dataset'],

    "filtered_kb": {'olist_customers_dataset': ['Table represents customer information (includes customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)', [['customer_id: Unique identifier for each customer, data type: VARCHAR, sample values: fad7d23c35cc53861ea7005b27cbeebf, 246ddb2dd49eae53ce1695190d61fc24'], ['customer_unique_id: Unique identifier for each customer, different from customer_id, data type: VARCHAR, sample values: 87b17699dbb8c555f40463875ccaea8d, 6a1bd3531227937b0bf249d29fbf9901'], ["customer_zip_code_prefix: The zip code prefix of the customer's location, data type: INTEGER, sample values: 49035, 96540"], ['customer_city: The city where the customer is located, data type: VARCHAR, sample values: aracaju, agudo'], ['customer_state: The state where the customer is located, data type: VARCHAR, sample values: SE, RS']]], 'olist_order_reviews_dataset': ['Table represents reviews made by customers after purchase (includes review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp)', [["review_id: alphanumeric identifier for each review, TEXT, sample values: '5cc99731674c4b5f4907c90be6906d68', '3338566cbe27d9977dc215eb193147e6'"], ["order_id: unique identifier for each order related to the review, TEXT, sample values: '499e36ddc9a7c36dd44e2dcd43a76620', '77e3266e92eda8a0570ce5b1045fa3b5'"], ['review_score: numerical rating given by the customer, INTEGER, sample values: 5, 2'], ["review_comment_title: title of the review comment, TEXT, sample values: 'Beleza e funcionalidade', 'Aprovado.'"], ["review_comment_message: detailed message of the review, TEXT, sample values: 'Almofada simples, bonita e bastante funcional. Gostei!', 'A entrega foi rápida, antes do prazo previsto.\r\nO produto corresponde às minhas expectativas até o momento. Está em uso há 4 dias.'"], ["review_creation_date: date and time when the review was created, TEXT, sample values: '2018-08-21 00:00:00', '2018-08-11 00:00:00'"], ["review_answer_timestamp: timestamp for when the review was answered, TEXT, sample values: '2018-08-22 11:55:10', '2018-08-12 14:00:41'"]]], 'olist_order_payments_dataset': ['Table represents orders payment options (includes order_id, payment_sequential, payment_type, payment_installments, payment_value)', [["order_id: Unique identifier for each order, datatype: VARCHAR, sample values: '9c9d443e386dc6332b14958d37eaf75b', '4db12ae1b5826c465cb48c30426fe425'"], ['payment_sequential: Sequential number for each payment within an order, datatype: INTEGER, sample values: 1, 1'], ["payment_type: Type of payment for the order, datatype: VARCHAR, sample values: 'credit_card', 'voucher'"], ['payment_installments: Number of installments for the payment, datatype: INTEGER, sample values: 2, 1'], ['payment_value: Amount paid for the order, datatype: FLOAT, sample values: 172.17, 298.81']]]},

    "column_selections": [['customer_state', "The state where the customer is located; links to 'olist_customers_dataset' and 'olist_orders_dataset' by state; sample values: SE, RS"], ['order_id', "Unique identifier for each order; used to count number of orders and link to 'olist_order_payments_dataset' and 'olist_order_reviews_dataset'; sample values: '9c9d443e386dc6332b14958d37eaf75b', '4db12ae1b5826c465cb48c30426fe425'"], ['review_score', 'Numerical rating given by the customer; used to calculate average review score per state; sample values: 5, 2'], ['payment_value', 'Amount paid for the order; used to calculate total payment per state; sample values: 172.17, 298.81']]


    }



result = sql_gen(test_state)

print(result["sql_query"])







