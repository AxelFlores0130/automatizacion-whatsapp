import time as monotonic
from datetime import datetime, timedelta

from .settings import (
    CHAT_DESTINO,
    HORARIOS_RESUMEN,
    INTERVALO_COMPROBACION_SEGUNDOS,
    INTERVALO_REINTENTO_SEGUNDOS,
    MAX_INTENTOS_ENVIO,
    VENTANA_ENVIO_MINUTOS,
)
from .ventas_service import get_db_connection, obtener_resumen_ventas
from .whatsapp_sender import enviar_resumen_whatsapp


_ultima_comprobacion_por_horario = {}
_ultimo_log_error = 0.0
_estados_finales = set()


def _leer_y_reservar_envio(horario):
    connection = get_db_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id_envio, estado, intentos,
                   TIMESTAMPDIFF(SECOND, fecha_intento, NOW())
                       AS segundos_desde_intento
            FROM envios_resumen_ventas
            WHERE fecha = CURRENT_DATE()
              AND horario = %s
              AND chat_destino = %s
            LIMIT 1
            """,
            (horario.strftime("%H:%M:%S"), CHAT_DESTINO),
        )
        registro = cursor.fetchone()

        if registro and registro["estado"] == "ENVIADO":
            return "enviado", None
        if registro and registro["estado"] == "EN_PROCESO":
            return "en_proceso", None
        if registro and registro["intentos"] >= MAX_INTENTOS_ENVIO:
            return "max_intentos", None
        if (
            registro
            and registro["segundos_desde_intento"]
            < INTERVALO_REINTENTO_SEGUNDOS
        ):
            return "esperar_reintento", None

        resumen = obtener_resumen_ventas(connection)
        if registro:
            cursor.execute(
                """
                UPDATE envios_resumen_ventas
                SET cantidad_ventas = %s,
                    total_vendido = %s,
                    mensaje = %s,
                    estado = 'EN_PROCESO',
                    intentos = intentos + 1,
                    fecha_intento = NOW(),
                    fecha_envio = NULL
                WHERE id_envio = %s
                  AND estado = 'ERROR'
                  AND intentos < %s
                """,
                (
                    resumen["cantidad_ventas"],
                    resumen["total_vendido"],
                    resumen["mensaje"],
                    registro["id_envio"],
                    MAX_INTENTOS_ENVIO,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return "ocupado", None
            envio_id = registro["id_envio"]
        else:
            cursor.execute(
                """
                INSERT INTO envios_resumen_ventas (
                    fecha, horario, chat_destino, cantidad_ventas,
                    total_vendido, mensaje, estado, intentos, fecha_intento
                )
                VALUES (
                    CURRENT_DATE(), %s, %s, %s, %s, %s,
                    'EN_PROCESO', 1, NOW()
                )
                """,
                (
                    horario.strftime("%H:%M:%S"),
                    CHAT_DESTINO,
                    resumen["cantidad_ventas"],
                    resumen["total_vendido"],
                    resumen["mensaje"],
                ),
            )
            envio_id = cursor.lastrowid

        connection.commit()
        return "reservado", (envio_id, resumen)
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


def _guardar_resultado(envio_id, enviado):
    connection = get_db_connection()
    cursor = None
    try:
        cursor = connection.cursor()
        estado = "ENVIADO" if enviado else "ERROR"
        cursor.execute(
            """
            UPDATE envios_resumen_ventas
            SET estado = %s,
                fecha_envio = CASE
                    WHEN %s = 'ENVIADO' THEN NOW()
                    ELSE NULL
                END
            WHERE id_envio = %s AND estado = 'EN_PROCESO'
            """,
            (estado, estado, envio_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("No se pudo actualizar el estado del envío.")
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


def _registrar_error(envio_id):
    if envio_id is None:
        return
    try:
        _guardar_resultado(envio_id, False)
        print("[VENTAS] Registro ERROR guardado")
    except Exception as error:
        print(f"[VENTAS] No se pudo guardar estado ERROR: {error}")


def _procesar_horario(page, horario, fecha, tick, clave):
    global _ultimo_log_error
    envio_id = None
    try:
        accion, reserva = _leer_y_reservar_envio(horario)
        if accion == "enviado":
            if clave not in _estados_finales:
                print(
                    "[VENTAS] Resumen "
                    f"{horario:%H:%M} ya enviado hoy"
                )
                _estados_finales.add(clave)
            return
        if accion in ("en_proceso", "max_intentos"):
            if accion == "max_intentos":
                print(
                    "[VENTAS] Reintentos agotados para el resumen "
                    f"{horario:%H:%M}"
                )
            _estados_finales.add(clave)
            return
        if accion != "reservado":
            return

        envio_id, resumen = reserva
        print(
            "[VENTAS] Corresponde enviar resumen de las "
            f"{horario:%H:%M}"
        )
        print("[VENTAS] Consultando ventas acumuladas del día")
        print(
            "[VENTAS] Ventas: "
            f"{resumen['cantidad_ventas']} | "
            f"Total: ${resumen['total_vendido']:,.2f}"
        )

        try:
            enviado = enviar_resumen_whatsapp(page, resumen["mensaje"])
        except Exception as error:
            _registrar_error(envio_id)
            print(f"[VENTAS] Error de envío: {error}")
            print("[VENTAS] Regresando al monitor de comprobantes")
            return

        if enviado is None:
            _estados_finales.add(clave)
            print(
                "[VENTAS] Envío ambiguo después del clic; "
                "registro permanece EN_PROCESO, sin reintento"
            )
            print("[VENTAS] Regresando al monitor de comprobantes")
            return

        try:
            _guardar_resultado(envio_id, enviado)
            if enviado:
                print("[VENTAS] Resumen enviado y verificado")
                print("[VENTAS] Registro de envío guardado")
                _estados_finales.add(clave)
            else:
                print("[VENTAS] No se confirmó el envío del resumen")
                print("[VENTAS] Registro ERROR guardado")
        except Exception as error:
            print(f"[VENTAS] Error al guardar resultado: {error}")
        finally:
            print("[VENTAS] Regresando al monitor de comprobantes")
    except Exception as error:
        if envio_id is not None:
            _registrar_error(envio_id)
        if tick - _ultimo_log_error >= 60:
            print(f"[VENTAS] Error del resumen programado: {error}")
            _ultimo_log_error = tick
        print("[VENTAS] Regresando al monitor de comprobantes")


def verificar_resumen_programado(page):
    ahora = datetime.now()
    tick = monotonic.monotonic()

    for horario in HORARIOS_RESUMEN:
        inicio = datetime.combine(ahora.date(), horario)
        fin = inicio + timedelta(minutes=VENTANA_ENVIO_MINUTOS)
        if not inicio <= ahora < fin:
            continue

        clave = (ahora.date(), CHAT_DESTINO, horario)
        if clave in _estados_finales:
            continue

        ultimo_tick = _ultima_comprobacion_por_horario.get(horario, 0.0)
        if tick - ultimo_tick < INTERVALO_COMPROBACION_SEGUNDOS:
            continue
        _ultima_comprobacion_por_horario[horario] = tick

        _procesar_horario(page, horario, ahora.date(), tick, clave)
