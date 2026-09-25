import os
import re
from decimal import Decimal, InvalidOperation
from datetime import timedelta

import mysql.connector
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from mysql.connector import Error
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:4200",
                "http://127.0.0.1:4200",
            ],
            "methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type"],
        }
    },
)
COMPROBANTES_PATH = os.getenv(
    "COMPROBANTES_PATH",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "comprobantes")
    )
)


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


@app.post("/api/auth/login")
def iniciar_sesion():
    payload = request.get_json(silent=True) or {}
    usuario = str(payload.get("usuario") or "").strip()
    contrasena = str(payload.get("contrasena") or "").strip()

    if not usuario or not contrasena:
        return jsonify({
            "ok": False,
            "mensaje": "Usuario y contraseña son obligatorios.",
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id_usuario, nombre, apellido, usuario, contrasena, telefono, estado
            FROM usuarios
            WHERE usuario = %s
            LIMIT 1
            """,
            (usuario,)
        )
        empleado = cursor.fetchone()

        if empleado is None or str(empleado.get("contrasena")) != contrasena:
            return jsonify({
                "ok": False,
                "mensaje": "Usuario o contraseña incorrectos.",
            }), 401

        if empleado.get("estado") != "ACTIVO":
            return jsonify({
                "ok": False,
                "mensaje": "Tu usuario se encuentra inactivo. Contacta al administrador.",
            }), 403

        return jsonify({
            "ok": True,
            "usuario": {
                "id_usuario": empleado.get("id_usuario"),
                "nombre": empleado.get("nombre"),
                "apellido": empleado.get("apellido"),
                "usuario": empleado.get("usuario"),
                "telefono": empleado.get("telefono"),
            },
        }), 200

    except Error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "ok": False,
            "mensaje": "No fue posible iniciar sesión.",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.post("/api/auth/registro")
def registrar_usuario():
    payload = request.get_json(silent=True) or {}

    nombre = str(payload.get("nombre") or "").strip()
    apellido = str(payload.get("apellido") or "").strip()
    telefono = str(payload.get("telefono") or "").strip() or None
    usuario = str(payload.get("usuario") or "").strip()
    contrasena = str(payload.get("contrasena") or "").strip()

    if not nombre or not apellido or not usuario or not contrasena:
        return jsonify({
            "ok": False,
            "mensaje": "Nombre, apellido, usuario y contraseña son obligatorios.",
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_usuario FROM usuarios WHERE usuario = %s LIMIT 1",
            (usuario,)
        )
        if cursor.fetchone() is not None:
            return jsonify({
                "ok": False,
                "mensaje": "El nombre de usuario ya está registrado.",
            }), 409

        cursor.execute(
            """
            INSERT INTO usuarios (nombre, apellido, usuario, contrasena, telefono)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (nombre, apellido, usuario, contrasena, telefono)
        )
        connection.commit()

        return jsonify({
            "ok": True,
            "mensaje": "Cuenta creada correctamente.",
        }), 201

    except mysql.connector.IntegrityError:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "ok": False,
            "mensaje": "El nombre de usuario ya está registrado.",
        }), 409
    except Error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "ok": False,
            "mensaje": "No fue posible crear la cuenta.",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


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


def _normalizar_form_value(valor):
    if valor is None:
        return None

    if isinstance(valor, str):
        texto = valor.strip()
        if texto == "" or texto.lower() == "none":
            return None
        return texto

    return valor


def _armar_payload_transferencia():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        return payload, request.files.get("archivo")

    payload = {}
    for clave, valor in request.form.items():
        payload[clave] = _normalizar_form_value(valor)

    archivo = request.files.get("archivo")
    return payload, archivo


def _guardar_archivo_comprobante_servidor(mensaje_whatsapp_id, archivo):
    if archivo is None:
        return None

    nombre_original = getattr(archivo, "filename", "") or ""
    nombre_seguro = secure_filename(nombre_original)
    if not nombre_seguro:
        return None

    extension = os.path.splitext(nombre_seguro)[1].lower()
    extensiones_permitidas = {".jpg", ".jpeg", ".png", ".pdf"}
    if extension not in extensiones_permitidas:
        return None

    mensaje_seguro = secure_filename(str(mensaje_whatsapp_id or "comprobante"))
    if not mensaje_seguro:
        mensaje_seguro = "comprobante"

    nombre_final = f"{mensaje_seguro}{extension}"
    directorio_originales = os.path.join(COMPROBANTES_PATH, "originales")
    os.makedirs(directorio_originales, exist_ok=True)

    ruta_final = os.path.join(directorio_originales, nombre_final)
    archivo.save(ruta_final)
    return nombre_final


def _folio_utilizable(valor):
    if valor is None:
        return None

    folio = str(valor).strip()
    if (
        len(folio) < 6
        or not folio.isdigit()
        or len(set(folio)) == 1
    ):
        return None

    return folio


def _normalizar_hora_para_comparar(valor):
    if valor is None:
        return None

    if isinstance(valor, timedelta):
        total_microsegundos = (
            (valor.days * 86400 + valor.seconds) * 1_000_000
            + valor.microseconds
        )
        signo = "-" if total_microsegundos < 0 else ""
        total_segundos, microsegundos = divmod(
            abs(total_microsegundos),
            1_000_000
        )
        horas, resto = divmod(total_segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        fraccion = (
            f".{microsegundos:06d}".rstrip("0")
            if microsegundos
            else ""
        )
        return f"{signo}{horas:02d}:{minutos:02d}:{segundos:02d}{fraccion}"

    texto = str(valor).strip()
    coincidencia = re.fullmatch(
        r"(?P<signo>-?)(?P<horas>\d+):(?P<minutos>\d{1,2}):"
        r"(?P<segundos>\d{1,2})(?:\.(?P<fraccion>\d+))?",
        texto
    )
    if coincidencia is None:
        return texto

    fraccion = (coincidencia.group("fraccion") or "").rstrip("0")
    sufijo_fraccion = f".{fraccion}" if fraccion else ""
    return (
        f"{coincidencia.group('signo')}"
        f"{int(coincidencia.group('horas')):02d}:"
        f"{int(coincidencia.group('minutos')):02d}:"
        f"{int(coincidencia.group('segundos')):02d}"
        f"{sufijo_fraccion}"
    )


def _buscar_transferencia_duplicada(cursor, payload):
    mensaje_id = payload.get("mensaje_whatsapp_id")
    cursor.execute(
        """
        SELECT id_transferencia
        FROM transferencias_detectadas
        WHERE mensaje_whatsapp_id = %s
        LIMIT 1
        """,
        (mensaje_id,)
    )
    existente = cursor.fetchone()
    if existente is not None:
        return {
            "duplicate_type": "mensaje_whatsapp",
            "id_transferencia_existente": existente["id_transferencia"],
        }

    folio = _folio_utilizable(payload.get("folio"))
    if folio is not None:
        cursor.execute(
            """
            SELECT
                id_transferencia,
                monto,
                cuenta_origen,
                cuenta_destino,
                fecha_transferencia,
                hora_transferencia
            FROM transferencias_detectadas
            WHERE folio = %s
            ORDER BY id_transferencia DESC
            LIMIT 20
            """,
            (folio,)
        )

        for fila in cursor.fetchall():
            contradiccion = False
            for campo in (
                "monto",
                "cuenta_origen",
                "cuenta_destino",
                "fecha_transferencia",
                "hora_transferencia",
            ):
                nuevo = payload.get(campo)
                anterior = fila.get(campo)
                if nuevo is not None and anterior is not None:
                    if campo == "monto":
                        try:
                            valores_iguales = (
                                Decimal(str(nuevo))
                                == Decimal(str(anterior))
                            )
                        except (InvalidOperation, ValueError):
                            valores_iguales = str(nuevo) == str(anterior)
                    elif campo == "hora_transferencia":
                        valores_iguales = (
                            _normalizar_hora_para_comparar(nuevo)
                            == _normalizar_hora_para_comparar(anterior)
                        )
                    else:
                        valores_iguales = str(nuevo) == str(anterior)

                    if not valores_iguales:
                        contradiccion = True
                        break

            if not contradiccion:
                return {
                    "duplicate_type": "transferencia",
                    "id_transferencia_existente": fila[
                        "id_transferencia"
                    ],
                }

    campos_completos = (
        "monto",
        "cuenta_origen",
        "cuenta_destino",
        "fecha_transferencia",
        "hora_transferencia",
    )
    if all(payload.get(campo) is not None for campo in campos_completos):
        cursor.execute(
            """
            SELECT id_transferencia
            FROM transferencias_detectadas
            WHERE monto = %s
              AND cuenta_origen = %s
              AND cuenta_destino = %s
              AND fecha_transferencia = %s
              AND hora_transferencia = %s
            ORDER BY id_transferencia DESC
            LIMIT 1
            """,
            tuple(payload.get(campo) for campo in campos_completos)
        )
        existente = cursor.fetchone()
        if existente is not None:
            return {
                "duplicate_type": "transferencia",
                "id_transferencia_existente": existente[
                    "id_transferencia"
                ],
            }

    return None


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
                fecha_registro_dorian,
                archivo_comprobante
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
                "archivo_comprobante": fila.get("archivo_comprobante"),
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


@app.get("/api/transferencias/<int:id_transferencia>/comprobante")
def obtener_comprobante(id_transferencia):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT archivo_comprobante
            FROM transferencias_detectadas
            WHERE id_transferencia = %s
            """,
            (id_transferencia,)
        )
        transferencia = cursor.fetchone()

        if transferencia is None:
            return jsonify({
                "success": False,
                "error": "Transferencia no encontrada",
            }), 404

        nombre_archivo = transferencia.get("archivo_comprobante")
        if not nombre_archivo or os.path.basename(nombre_archivo) != nombre_archivo:
            return jsonify({
                "success": False,
                "error": "Comprobante no disponible",
            }), 404

        directorio_originales = os.path.join(COMPROBANTES_PATH, "originales")
        ruta_comprobante = os.path.join(
            directorio_originales,
            nombre_archivo
        )
        if not os.path.isfile(ruta_comprobante):
            return jsonify({
                "success": False,
                "error": "Comprobante no encontrado físicamente",
            }), 404

        extension = os.path.splitext(nombre_archivo)[1].lower()
        mimetype = {
            ".jpg": "image/jpeg",
            ".pdf": "application/pdf",
        }.get(extension)
        if mimetype is None:
            return jsonify({
                "success": False,
                "error": "Tipo de comprobante no permitido",
            }), 404

        return send_from_directory(
            directorio_originales,
            nombre_archivo,
            mimetype=mimetype
        )

    except Error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "success": False,
            "error": "Error de MySQL al consultar el comprobante",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.patch("/api/transferencias/<int:id_transferencia>/estado")
def cambiar_estado_transferencia(id_transferencia):
    payload = request.get_json(silent=True) or {}
    estado_solicitado = payload.get("estado")
    transiciones_permitidas = {
        ("PENDIENTE", "RECHAZADA"),
        ("RECHAZADA", "PENDIENTE"),
    }

    if estado_solicitado not in {"PENDIENTE", "RECHAZADA"}:
        return jsonify({
            "success": False,
            "error": "Estado solicitado no permitido",
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT estado
            FROM transferencias_detectadas
            WHERE id_transferencia = %s
            """,
            (id_transferencia,)
        )
        transferencia = cursor.fetchone()

        if transferencia is None:
            return jsonify({
                "success": False,
                "error": "Transferencia no encontrada",
            }), 404

        estado_actual = transferencia.get("estado")
        if (estado_actual, estado_solicitado) not in transiciones_permitidas:
            return jsonify({
                "success": False,
                "error": "Transición de estado no permitida",
                "estado_actual": estado_actual,
                "estado_solicitado": estado_solicitado,
            }), 409

        cursor.execute(
            """
            UPDATE transferencias_detectadas
            SET estado = %s
            WHERE id_transferencia = %s
            """,
            (estado_solicitado, id_transferencia)
        )
        connection.commit()

        return jsonify({
            "success": True,
            "id_transferencia": id_transferencia,
            "estado": estado_solicitado,
        }), 200

    except Error as error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "success": False,
            "error": f"Error de MySQL al cambiar el estado: {error}",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.delete("/api/transferencias/<int:id_transferencia>")
def eliminar_transferencia(id_transferencia):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT estado
            FROM transferencias_detectadas
            WHERE id_transferencia = %s
            """,
            (id_transferencia,)
        )
        transferencia = cursor.fetchone()

        if transferencia is None:
            return jsonify({
                "success": False,
                "error": "Transferencia no encontrada",
            }), 404

        if transferencia.get("estado") != "RECHAZADA":
            return jsonify({
                "success": False,
                "error": "Solo se pueden eliminar transferencias rechazadas",
                "estado_actual": transferencia.get("estado"),
            }), 409

        cursor.execute(
            """
            DELETE FROM transferencias_detectadas
            WHERE id_transferencia = %s
              AND estado = %s
            """,
            (id_transferencia, "RECHAZADA")
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return jsonify({
                "success": False,
                "error": "La transferencia no pudo eliminarse",
            }), 409

        connection.commit()
        return jsonify({
            "success": True,
            "id_transferencia": id_transferencia,
            "message": "Transferencia eliminada correctamente",
        }), 200

    except Error as error:
        if connection is not None:
            connection.rollback()
        return jsonify({
            "success": False,
            "error": f"Error de MySQL al eliminar la transferencia: {error}",
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.post("/api/transferencias")
def registrar_transferencia():
    payload, archivo = _armar_payload_transferencia()

    campos_obligatorios = [
        "mensaje_whatsapp_id",
        "chat",
        "tipo_archivo",
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
            hora_transferencia,
            archivo_comprobante
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    connection = None
    cursor = None
    archivo_guardado = None
    ruta_archivo_guardado = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        duplicado = _buscar_transferencia_duplicada(cursor, payload)
        if duplicado is not None:
            connection.rollback()
            return jsonify({
                "success": False,
                "duplicate": True,
                **duplicado,
            }), 409

        if archivo is not None and getattr(archivo, "filename", None):
            nombre_archivo = _guardar_archivo_comprobante_servidor(
                payload.get("mensaje_whatsapp_id"),
                archivo,
            )
            if nombre_archivo is None:
                return jsonify({
                    "success": False,
                    "error": "Archivo no permitido o inválido",
                }), 400

            ruta_archivo_guardado = os.path.join(
                COMPROBANTES_PATH,
                "originales",
                nombre_archivo,
            )
            archivo_guardado = nombre_archivo
            payload["archivo_comprobante"] = nombre_archivo

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
            payload.get("archivo_comprobante"),
        )

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
        if archivo_guardado is not None and ruta_archivo_guardado and os.path.exists(ruta_archivo_guardado):
            try:
                os.remove(ruta_archivo_guardado)
            except OSError:
                pass
        mensaje = str(error)
        if "Duplicate entry" in mensaje or "UNIQUE" in mensaje:
            return jsonify({
                "success": False,
                "duplicate": True,
                "duplicate_type": "mensaje_whatsapp",
                "message": "La transferencia ya había sido registrada",
            }), 409

        return jsonify({
            "success": False,
            "error": f"Error de integridad en MySQL: {mensaje}",
        }), 400

    except Error as error:
        if connection is not None:
            connection.rollback()
        if archivo_guardado is not None and ruta_archivo_guardado and os.path.exists(ruta_archivo_guardado):
            try:
                os.remove(ruta_archivo_guardado)
            except OSError:
                pass
        return jsonify({
            "success": False,
            "error": f"Error de MySQL: {error}",
        }), 500

    except Exception:
        if connection is not None:
            connection.rollback()
        if archivo_guardado is not None and ruta_archivo_guardado and os.path.exists(ruta_archivo_guardado):
            try:
                os.remove(ruta_archivo_guardado)
            except OSError:
                pass
        raise

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
