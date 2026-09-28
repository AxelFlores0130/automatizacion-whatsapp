import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main():
    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "root"),
            database=os.getenv("DB_NAME", "dorian_automatizacion"),
            autocommit=False,
        )
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT CURRENT_DATE(), COUNT(*), COALESCE(SUM(monto), 0)
            FROM ventas
            WHERE fecha_venta >= CURRENT_DATE()
              AND fecha_venta < CURRENT_DATE() + INTERVAL 1 DAY
              AND estado = %s
            """,
            ("COMPLETADA",),
        )
        fecha, cantidad_ventas, total_vendido = cursor.fetchone()

        print("RESUMEN DE VENTAS")
        print(f"Fecha: {fecha:%d/%m/%Y}")
        print(f"Ventas realizadas: {cantidad_ventas}")
        print(f"Total vendido: ${total_vendido:,.2f}")

    except Error as error:
        print(f"Error de MySQL: {error}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()
