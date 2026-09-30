import os
from datetime import date, timedelta
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("VENTAS_DB_HOST", "localhost"),
        port=int(os.getenv("VENTAS_DB_PORT", "3306")),
        user=os.getenv("VENTAS_DB_USER", "root"),
        password=os.getenv("VENTAS_DB_PASSWORD", "root"),
        autocommit=False,
    )


def obtener_resumen_ventas(connection, fecha_consulta=None):
    fecha_efectiva = date.today() if fecha_consulta is None else fecha_consulta
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT COUNT(CASE
                       WHEN ventas.ApartadoEsApartado = 'N'
                        AND ventas.estatus_venta NOT LIKE '%DEV%'
                        AND ventas.estatus_venta NOT LIKE '%CANCEL%'
                       THEN 1
                   END),
                   COALESCE(SUM(CASE
                       WHEN ventas.ApartadoEsApartado = 'N'
                        AND ventas.estatus_venta NOT LIKE '%DEV%'
                        AND ventas.estatus_venta NOT LIKE '%CANCEL%'
                       THEN ventas.APagar
                       ELSE 0
                   END), 0),
                   COUNT(CASE
                       WHEN ventas.ApartadoEsApartado = 'S'
                        AND ventas.estatus_apartado NOT LIKE '%DEV%'
                        AND ventas.estatus_apartado NOT LIKE '%CANCEL%'
                       THEN 1
                   END),
                   COALESCE(SUM(CASE
                       WHEN ventas.ApartadoEsApartado = 'S'
                        AND ventas.estatus_apartado NOT LIKE '%DEV%'
                        AND ventas.estatus_apartado NOT LIKE '%CANCEL%'
                       THEN ventas.APagar
                       ELSE 0
                   END), 0)
            FROM (
                SELECT v1.ApartadoEsApartado,
                       v1.APagar,
                       CASE
                           WHEN v1.ApartadoEsApartado = 'N'
                           THEN dorian.trae_estatus_venta(v1.oid_ventas)
                       END AS estatus_venta,
                       CASE
                           WHEN v1.ApartadoEsApartado = 'S'
                           THEN dorian.trae_estatus_apdo(v1.oid_ventas)
                       END AS estatus_apartado
                FROM central.ventas v1
                JOIN central.cajas c1 ON c1.oid_cajas = v1.oid_Cajas
                JOIN central.tiendas t1 ON t1.oid_tiendas = c1.oid_Tiendas
                                WHERE v1.Fecha >= %s
                                    AND v1.Fecha < %s
            ) AS ventas
                        """,
                        (
                                fecha_efectiva,
                                fecha_efectiva + timedelta(days=1),
                        ),
        )
        (
            cantidad_no_apartado,
            total_no_apartado,
            cantidad_apartados,
            total_apartados,
        ) = cursor.fetchone()
        fecha = fecha_efectiva
        cantidad_ventas = cantidad_no_apartado + cantidad_apartados
        total_vendido = total_no_apartado + total_apartados
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
            "cantidad_no_apartado": cantidad_no_apartado,
            "total_no_apartado": total_no_apartado,
            "cantidad_apartados": cantidad_apartados,
            "total_apartados": total_apartados,
        }
    finally:
        cursor.close()
