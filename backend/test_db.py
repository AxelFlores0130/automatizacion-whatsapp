import os

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error

load_dotenv()

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "root")
password = os.getenv("DB_PASSWORD", "root")
database = os.getenv("DB_NAME", "dorian_automatizacion")

connection = None
cursor = None

try:
    connection = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )

    if connection.is_connected():
        print("Conexión a MySQL exitosa")

        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE()")
        result = cursor.fetchone()

        if result:
            print(f"Base de datos: {result[0]}")

except Error as e:
    print(f"Error de MySQL: {e}")
finally:
    if cursor is not None:
        cursor.close()
    if connection is not None and connection.is_connected():
        connection.close()
