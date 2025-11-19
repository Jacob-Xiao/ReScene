import mysql.connector
from mysql.connector import pooling

# MySQL 连接池
dbconfig = {
    "host": "localhost",
    "user": "root",
    "password": "你的密码",
    "database": "recene"
}

connection_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=5,
    **dbconfig
)
