import os
from datetime import timedelta

import mysql.connector
from flask import Flask, jsonify, request
from flask_cors import CORS
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "dorian_automatizacion"),
        autocommit=False,
    )


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "Backend de automatizacion WhatsApp funcionando"
    }), 200


def _serializar_hora_mysql(valor):
    if valor is None:
        return None

    if isinstance(valor, timedelta):
        total_segundos = int(valor.total_seconds())
        horas = total_segundos // 3600
        minutos = (total_segundos % 3600) // 60
        segundos = total_segundos % 60
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    return str(valor)


@app.get("/api/transferencias")
def obtener_transferencias():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        sql = """
            SELECT
                id_transferencia,
                mensaje_whatsapp_id,
                chat,
                tipo_archivo,
                monto,
                destinatario,
                cuenta_destino,
                cuenta_origen,
                comision,
                concepto,
                tipo_operacion,
                folio,
                fecha_transferencia,
                hora_transferencia,
                estado,
                id_cliente_dorian,
                id_pago_dorian,
                fecha_deteccion,
                fecha_validacion,
                fecha_registro_dorian
            FROM transferencias_detectadas
            ORDER BY fecha_deteccion DESC, id_transferencia DESC
        """
        cursor.execute(sql)
        filas = cursor.fetchall()

        transferencias = []
        for fila in filas:
            transferencias.append({
                "id_transferencia": fila.get("id_transferencia"),
                "mensaje_whatsapp_id": fila.get("mensaje_whatsapp_id"),
                "chat": fila.get("chat"),
                "tipo_archivo": fila.get("tipo_archivo"),
                "monto": float(fila["monto"]) if fila.get("monto") is not None else None,
                "destinatario": fila.get("destinatario"),
                "cuenta_destino": fila.get("cuenta_destino"),
                "cuenta_origen": fila.get("cuenta_origen"),
                "comision": float(fila["comision"]) if fila.get("comision") is not None else None,
                "concepto": fila.get("concepto"),
                "tipo_operacion": fila.get("tipo_operacion"),
                "folio": fila.get("folio"),
                "fecha_transferencia": fila.get("fecha_transferencia").isoformat() if fila.get("fecha_transferencia") is not None else None,
                "hora_transferencia": _serializar_hora_mysql(fila.get("hora_transferencia")),
                "estado": fila.get("estado"),
                "id_cliente_dorian": fila.get("id_cliente_dorian"),
                "id_pago_dorian": fila.get("id_pago_dorian"),
                "fecha_deteccion": fila.get("fecha_deteccion").isoformat() if fila.get("fecha_deteccion") is not None else None,
                "fecha_validacion": fila.get("fecha_validacion").isoformat() if fila.get("fecha_validacion") is not None else None,
                "fecha_registro_dorian": fila.get("fecha_registro_dorian").isoformat() if fila.get("fecha_registro_dorian") is not None else None,
            })

        return jsonify({
            "success": True,
            "total": len(transferencias),
            "transferencias": transferencias,
        }), 200

    except Error as error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "success": False,
            "error": "Error de MySQL al consultar transferencias",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.post("/api/transferencias")
def registrar_transferencia():
    payload = request.get_json(silent=True) or {}

    campos_obligatorios = [
        "mensaje_whatsapp_id",
        "chat",
        "tipo_archivo",
        "monto",
        "destinatario",
        "cuenta_destino",
        "cuenta_origen",
        "comision",
        "concepto",
        "tipo_operacion",
        "folio",
        "fecha_transferencia",
        "hora_transferencia",
    ]

    faltantes = [
        campo for campo in campos_obligatorios if payload.get(campo) is None
    ]

    if faltantes:
        return jsonify({
            "success": False,
            "error": "Faltan campos obligatorios",
            "faltantes": faltantes,
        }), 400

    sql = """
        INSERT INTO transferencias_detectadas (
            mensaje_whatsapp_id,
            chat,
            tipo_archivo,
            monto,
            destinatario,
            cuenta_destino,
            cuenta_origen,
            comision,
            concepto,
            tipo_operacion,
            folio,
            fecha_transferencia,
            hora_transferencia
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    valores = (
        payload.get("mensaje_whatsapp_id"),
        payload.get("chat"),
        payload.get("tipo_archivo"),
        payload.get("monto"),
        payload.get("destinatario"),
        payload.get("cuenta_destino"),
        payload.get("cuenta_origen"),
        payload.get("comision"),
        payload.get("concepto"),
        payload.get("tipo_operacion"),
        payload.get("folio"),
        payload.get("fecha_transferencia"),
        payload.get("hora_transferencia"),
    )

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(sql, valores)
        connection.commit()

        return jsonify({
            "success": True,
            "message": "Transferencia registrada correctamente",
            "id_transferencia": cursor.lastrowid,
        }), 201

    except mysql.connector.IntegrityError as error:
        if connection is not None:
            connection.rollback()
        mensaje = str(error)
        if "Duplicate entry" in mensaje or "UNIQUE" in mensaje:
            return jsonify({
                "success": False,
                "message": "La transferencia ya había sido registrada",
            }), 409

        return jsonify({
            "success": False,
            "error": f"Error de integridad en MySQL: {mensaje}",
        }), 400

    except Error as error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "success": False,
            "error": f"Error de MySQL: {error}",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
