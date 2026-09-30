import json
import os
import tempfile
import time as monotonic
from datetime import datetime, timedelta
from pathlib import Path

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
_ARCHIVO_ESTADO = Path(__file__).with_name("estado_envios.json")


def _leer_estados_envio():
    try:
        with _ARCHIVO_ESTADO.open("r", encoding="utf-8") as archivo:
            estados = json.load(archivo)
    except FileNotFoundError:
        return {}
    if not isinstance(estados, dict):
        raise ValueError("El archivo de estados de envíos no contiene un objeto JSON.")
    return estados


def _guardar_estados_envio(estados):
    archivo_temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=_ARCHIVO_ESTADO.parent,
            prefix="estado_envios_",
            suffix=".tmp",
            delete=False,
        ) as archivo:
            archivo_temporal = Path(archivo.name)
            json.dump(estados, archivo, ensure_ascii=False, indent=2)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(archivo_temporal, _ARCHIVO_ESTADO)
    finally:
        if archivo_temporal is not None and archivo_temporal.exists():
            archivo_temporal.unlink()


def _clave_envio(fecha, horario):
    return json.dumps(
        (fecha.isoformat(), horario.strftime("%H:%M:%S"), CHAT_DESTINO),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _actualizar_estado(clave, fecha, horario, estado, intentos, fecha_intento):
    estados = _leer_estados_envio()
    estados[clave] = {
        "fecha": fecha.isoformat(),
        "horario": horario.strftime("%H:%M:%S"),
        "chat_destino": CHAT_DESTINO,
        "estado": estado,
        "intentos": intentos,
        "fecha_intento": fecha_intento.isoformat(),
    }
    _guardar_estados_envio(estados)


def _leer_y_reservar_envio(horario, fecha):
    ahora = datetime.now()
    clave = _clave_envio(fecha, horario)
    estados = _leer_estados_envio()
    registro = estados.get(clave)

    if registro:
        if registro["estado"] == "ENVIADO":
            return "enviado", clave
        if registro["estado"] == "ENVIO_AMBIGUO":
            return "ambiguo", clave
        if registro["estado"] not in ("EN_PROCESO", "ERROR"):
            return "en_proceso", clave

        intentos = registro["intentos"]
        if intentos >= MAX_INTENTOS_ENVIO:
            return "max_intentos", clave
        fecha_intento = datetime.fromisoformat(registro["fecha_intento"])
        if (
            (ahora - fecha_intento).total_seconds()
            < INTERVALO_REINTENTO_SEGUNDOS
        ):
            if registro["estado"] == "EN_PROCESO":
                return "en_proceso", clave
            return "esperar_reintento", clave
    else:
        intentos = 0

    intentos += 1
    _actualizar_estado(
        clave,
        fecha,
        horario,
        "EN_PROCESO",
        intentos,
        ahora,
    )
    return "reservado", clave


def _consultar_resumen_ventas():
    connection = get_db_connection()
    try:
        return obtener_resumen_ventas(connection)
    finally:
        connection.close()


def _registrar_estado(clave, fecha, horario, estado):
    estados = _leer_estados_envio()
    registro = estados[clave]
    _actualizar_estado(
        clave,
        fecha,
        horario,
        estado,
        registro["intentos"],
        datetime.fromisoformat(registro["fecha_intento"]),
    )


def _registrar_error(clave, fecha, horario):
    if clave is None:
        return
    try:
        _registrar_estado(clave, fecha, horario, "ERROR")
        print("[VENTAS] Registro ERROR guardado localmente")
    except Exception as error:
        print(f"[VENTAS] No se pudo guardar estado ERROR: {error}")


def _procesar_horario(page, horario, fecha, tick, clave):
    global _ultimo_log_error
    clave_envio = None
    envio_iniciado = False
    try:
        accion, clave_envio = _leer_y_reservar_envio(horario, fecha)
        if accion == "enviado":
            if clave not in _estados_finales:
                print(
                    "[VENTAS] Resumen "
                    f"{horario:%H:%M} ya enviado hoy"
                )
                _estados_finales.add(clave)
            return
        if accion in ("en_proceso", "ambiguo", "max_intentos"):
            if accion == "max_intentos":
                print(
                    "[VENTAS] Reintentos agotados para el resumen "
                    f"{horario:%H:%M}"
                )
            elif accion == "ambiguo":
                print(
                    "[VENTAS] Envío ambiguo previamente registrado para "
                    f"{horario:%H:%M}; no se reintentará"
                )
            _estados_finales.add(clave)
            return
        if accion != "reservado":
            return

        resumen = _consultar_resumen_ventas()
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
            envio_iniciado = True
            enviado = enviar_resumen_whatsapp(page, resumen["mensaje"])
        except Exception as error:
            _registrar_error(clave_envio, fecha, horario)
            print(f"[VENTAS] Error de envío: {error}")
            print("[VENTAS] Regresando al monitor de comprobantes")
            return

        if enviado is None:
            _registrar_estado(
                clave_envio,
                fecha,
                horario,
                "ENVIO_AMBIGUO",
            )
            _estados_finales.add(clave)
            print(
                "[VENTAS] Envío ambiguo después del clic; "
                "estado local guardado, sin reintento"
            )
            print("[VENTAS] Regresando al monitor de comprobantes")
            return

        try:
            estado = "ENVIADO" if enviado is True else "ERROR"
            _registrar_estado(clave_envio, fecha, horario, estado)
            if enviado is True:
                print("[VENTAS] Resumen enviado y verificado")
                print("[VENTAS] Estado ENVIADO guardado localmente")
                _estados_finales.add(clave)
            else:
                print("[VENTAS] No se confirmó el envío del resumen")
                print("[VENTAS] Registro ERROR guardado localmente")
        except Exception as error:
            print(f"[VENTAS] Error al guardar resultado: {error}")
        finally:
            print("[VENTAS] Regresando al monitor de comprobantes")
    except Exception as error:
        if clave_envio is not None and not envio_iniciado:
            _registrar_error(clave_envio, fecha, horario)
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
