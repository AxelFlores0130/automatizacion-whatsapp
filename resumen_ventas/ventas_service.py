import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "dorian_automatizacion"),
        autocommit=False,
    )


def obtener_resumen_ventas(connection):
    cursor = connection.cursor()
    try:
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
        mensaje = "\n".join(
            (
                "RESUMEN DE VENTAS",
                f"Fecha: {fecha:%d/%m/%Y}",
                f"Ventas realizadas: {cantidad_ventas}",
                f"Total vendido: ${total_vendido:,.2f}",
            )
        )
        return {
            "fecha": fecha,
            "cantidad_ventas": cantidad_ventas,
            "total_vendido": total_vendido,
            "mensaje": mensaje,
        }
    finally:
        cursor.close()
