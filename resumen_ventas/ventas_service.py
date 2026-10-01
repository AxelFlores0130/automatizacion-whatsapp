import os
from datetime import date, datetime, timedelta
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from . import app_config
from .settings import FECHA_PRUEBA_VENTAS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_db_connection():
    saved_config = app_config.load_config()
    if saved_config is not None:
        return mysql.connector.connect(
            host=saved_config["host"],
            port=saved_config["port"],
            user=saved_config["user"],
            password=saved_config["password"],
            autocommit=False,
        )

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
                        AND ventas.estatus_venta = 'CONTADO'
                       THEN 1
                   END),
                   COALESCE(SUM(CASE
                       WHEN ventas.ApartadoEsApartado = 'N'
                        AND ventas.estatus_venta NOT LIKE '%DEV%'
                        AND ventas.estatus_venta NOT LIKE '%CANCEL%'
                        AND ventas.estatus_venta = 'CONTADO'
                       THEN ventas.APagar
                       ELSE 0
                   END), 0),
                   COUNT(CASE
                       WHEN ventas.ApartadoEsApartado = 'N'
                        AND ventas.estatus_venta NOT LIKE '%DEV%'
                        AND ventas.estatus_venta NOT LIKE '%CANCEL%'
                        AND ventas.estatus_venta = 'CREDITO'
                       THEN 1
                   END),
                   COALESCE(SUM(CASE
                       WHEN ventas.ApartadoEsApartado = 'N'
                        AND ventas.estatus_venta NOT LIKE '%DEV%'
                        AND ventas.estatus_venta NOT LIKE '%CANCEL%'
                        AND ventas.estatus_venta = 'CREDITO'
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
            contado_cantidad,
            contado_total,
            credito_cantidad,
            credito_total,
            cantidad_apartados,
            total_apartados,
        ) = cursor.fetchone()
        fecha = fecha_efectiva
        cantidad_no_apartado = contado_cantidad + credito_cantidad
        total_no_apartado = contado_total + credito_total
        cantidad_ventas = cantidad_no_apartado + cantidad_apartados
        total_vendido = total_no_apartado + total_apartados
        meses = (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
        fecha_texto = (
            f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"
        )
        if FECHA_PRUEBA_VENTAS is not None:
            texto_corte = "🕐 Corte de prueba: día completo"
        else:
            ahora = datetime.now()
            hora = ahora.strftime("%I:%M").lstrip("0")
            periodo = "a. m." if ahora.hour < 12 else "p. m."
            texto_corte = (
                f"🕐 Ventas acumuladas hasta las {hora} {periodo}"
            )
        mensaje = "\n".join(
            (
                "DORIAN MUEBLES",
                "📊 *RESUMEN DE VENTAS*",
                "",
                f"📅 {fecha_texto}",
                texto_corte,
                "",
                "*DESGLOSE DE VENTAS*",
                "",
                "💵 *Contado*",
                f"{contado_cantidad} "
                f"{'operación' if contado_cantidad == 1 else 'operaciones'}",
                f"${contado_total:,.2f}",
                "",
                "💳 *Crédito*",
                f"{credito_cantidad} "
                f"{'operación' if credito_cantidad == 1 else 'operaciones'}",
                f"${credito_total:,.2f}",
                "",
                "📦 *Apartados*",
                f"{cantidad_apartados} "
                f"{'operación' if cantidad_apartados == 1 else 'operaciones'}",
                f"${total_apartados:,.2f}",
                "",
                "──────────────────",
                "*TOTAL DE VENTAS*",
                "",
                f"🧾 {cantidad_ventas} "
                f"{'operación' if cantidad_ventas == 1 else 'operaciones'}",
                f"💰 *${total_vendido:,.2f}*",
                "──────────────────",
                "",
                "_Reporte generado automáticamente por el sistema "
                "de Dorian Muebles._",
            )
        )
        return {
            "fecha": fecha,
            "contado_cantidad": contado_cantidad,
            "contado_total": contado_total,
            "credito_cantidad": credito_cantidad,
            "credito_total": credito_total,
            "apartados_cantidad": cantidad_apartados,
            "apartados_total": total_apartados,
            "ventas_realizadas": cantidad_ventas,
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
