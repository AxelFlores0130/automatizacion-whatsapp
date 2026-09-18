from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError
)
import re
import os
import base64
import time
import shutil
import pytesseract
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter


# ============================================================
# CONFIGURACIÓN
# ============================================================

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROFILE_PATH = (
    r"C:\Users\DORIAN\Desktop\automatizacion whatsapp\chrome_profile"
)

TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

COMPROBANTES_PATH = (
    r"C:\Users\DORIAN\Desktop\automatizacion whatsapp\comprobantes"
)

DOWNLOAD_PATH = r"C:\Users\DORIAN\Downloads"

os.makedirs(COMPROBANTES_PATH, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ============================================================
# EXTRAER DATOS DEL TEXTO OCR
# ============================================================

def extraer_datos_transferencia(texto_psm6, texto_psm11):

    datos = {
        "monto": None,
        "destinatario": None,
        "cuenta_destino": None,
        "cuenta_origen": None,
        "comision": None,
        "concepto": None,
        "tipo_operacion": None,
        "folio": None,
        "fecha": None,
        "hora": None
    }

    lineas6 = [
        linea.strip()
        for linea in texto_psm6.splitlines()
        if linea.strip()
    ]

    lineas11 = [
        linea.strip()
        for linea in texto_psm11.splitlines()
        if linea.strip()
    ]

    # ========================================================
    # MONTO
    # ========================================================

    for i, linea in enumerate(lineas11):

        if "monto" in linea.lower():

            for siguiente in lineas11[i + 1:i + 4]:

                coincidencia = re.search(
                    r'\$\s*([\d,]+\.\d{2})',
                    siguiente
                )

                if coincidencia:

                    try:
                        datos["monto"] = float(
                            coincidencia.group(1).replace(",", "")
                        )
                    except ValueError:
                        pass

                    break

        if datos["monto"] is not None:
            break

    if datos["monto"] is None:

        coincidencia = re.search(
            r'\$\s*([\d,]+\.\d{2})',
            texto_psm11
        )

        if coincidencia:

            try:
                datos["monto"] = float(
                    coincidencia.group(1).replace(",", "")
                )
            except ValueError:
                pass

    # ========================================================
    # CUENTA ORIGEN
    # ========================================================

    for linea in lineas6:

        if "origen" in linea.lower():

            numeros = re.findall(
                r'(\d{4})\b',
                linea
            )

            if numeros:
                datos["cuenta_origen"] = numeros[-1]
                break

    # Fallback con PSM11

    if datos["cuenta_origen"] is None:

        for i, linea in enumerate(lineas11):

            if linea.lower() == "origen":

                for siguiente in lineas11[i + 1:i + 3]:

                    numeros = re.findall(
                        r'(\d{4})\b',
                        siguiente
                    )

                    if numeros:
                        datos["cuenta_origen"] = numeros[-1]
                        break

            if datos["cuenta_origen"]:
                break

    if datos["cuenta_origen"] is None:

        for i, linea in enumerate(lineas11):

            if "cuenta origen" in linea.lower():

                for siguiente in lineas11[i + 1:i + 4]:

                    cuenta = re.search(
                        r'(?:\*+|°|-)\s*(\d{3,4})\b',
                        siguiente
                    )

                    if cuenta:
                        datos["cuenta_origen"] = cuenta.group(1)
                        break

                if datos["cuenta_origen"]:
                    break

    if datos["cuenta_origen"] is None:

        for lineas in (lineas6, lineas11):

            for i, linea in enumerate(lineas):

                if "cuenta retiro" in linea.lower():

                    siguientes = lineas[i + 1:i + 4]
                    candidatos = [
                        siguiente
                        for siguiente in siguientes
                        if re.search(
                            r'(?:\*+|°|-)\s*\d{3,4}\b',
                            siguiente
                        )
                    ]

                    candidatos.sort(
                        key=lambda valor: (
                            "banamex" not in valor.lower()
                            and "priority" not in valor.lower(),
                            siguientes.index(valor)
                        )
                    )

                    if candidatos:
                        cuenta = re.search(
                            r'(?:\*+|°|-)\s*(\d{3,4})\b',
                            candidatos[0]
                        )

                        if cuenta:
                            datos["cuenta_origen"] = cuenta.group(1)
                            break

            if datos["cuenta_origen"]:
                break

    # ========================================================
    # DESTINATARIO Y CUENTA DESTINO
    # ========================================================

    for linea in lineas6:

        if "destino" in linea.lower():

            contenido = re.sub(
                r'(?i)destino',
                '',
                linea
            ).strip()

            cuenta = re.search(
                r'(\d{4})\b',
                contenido
            )

            if cuenta:

                datos["cuenta_destino"] = cuenta.group(1)

                nombre = re.sub(
                    r'[-•°*+«]?\s*\d{4}\b',
                    '',
                    contenido
                ).strip()

                if nombre:
                    datos["destinatario"] = nombre

            elif contenido:
                datos["destinatario"] = contenido

            break

    # Fallback con PSM11

    if datos["destinatario"] is None:

        for i, linea in enumerate(lineas11):

            if linea.lower() == "destino":

                if i + 1 < len(lineas11):

                    contenido = lineas11[i + 1]

                    cuenta = re.search(
                        r'(\d{4})\b',
                        contenido
                    )

                    if cuenta:
                        datos["cuenta_destino"] = cuenta.group(1)

                    nombre = re.sub(
                        r'[-•°*+«]?\s*\d{4}\b',
                        '',
                        contenido
                    ).strip()

                    if nombre:
                        datos["destinatario"] = nombre

                break

    destinatarios_invalidos = {
        "cuenta",
        "cuenta destino",
        "cuenta origen",
        "destino",
        "origen"
    }

    if datos["destinatario"] is not None:

        if datos["destinatario"].strip().lower() in destinatarios_invalidos:
            datos["destinatario"] = None

    if (
        datos["destinatario"] is None
        or datos["cuenta_destino"] is None
    ):

        for i, linea in enumerate(lineas11):

            if "cuenta destino" in linea.lower():

                for siguiente in lineas11[i + 1:i + 4]:

                    if siguiente.lower() in destinatarios_invalidos:
                        continue

                    cuenta = re.search(
                        r'(?:\*+|°|-)\s*(\d{3,4})\b',
                        siguiente
                    )

                    if cuenta:
                        datos["cuenta_destino"] = cuenta.group(1)

                        nombre = re.sub(
                            r'\s*(?:\*+|°|-)\s*\d{3,4}\b',
                            '',
                            siguiente
                        ).strip(" -*°•")

                        if nombre.lower() not in destinatarios_invalidos:
                            datos["destinatario"] = nombre

                        break

                break

    if (
        datos["destinatario"] is None
        or datos["cuenta_destino"] is None
    ):

        patron_cuenta_beneficiario = (
            r"cuenta\s+d[ée]p[óo]sito\s+o\s+beneficiario"
        )

        for lineas in (lineas6, lineas11):

            for i, linea in enumerate(lineas):

                if not re.search(
                    patron_cuenta_beneficiario,
                    linea.lower()
                ):
                    continue

                siguientes = lineas[i + 1:i + 6]
                nombre_provisional = None

                for siguiente in siguientes:

                    if siguiente.lower().startswith("nombre:"):
                        nombre_provisional = re.sub(
                            r"(?i)^nombre:\s*",
                            "",
                            siguiente
                        ).strip()
                        break

                for siguiente in siguientes:

                    cuenta = re.search(
                        r'(?:\*+|°|-)\s*(\d{3,4})\b',
                        siguiente
                    )

                    if not cuenta:
                        continue

                    datos["cuenta_destino"] = cuenta.group(1)

                    nombre = re.sub(
                        r'\s*(?:\*+|°|-)\s*\d{3,4}\b',
                        '',
                        siguiente
                    ).strip(" -*°•")

                    nombre = re.sub(
                        r"(?i)^nu\s+mexico\s+",
                        "",
                        nombre
                    ).strip()

                    if len(nombre.split()) > len(
                        (nombre_provisional or "").split()
                    ):
                        nombre_provisional = nombre

                    if nombre_provisional:
                        datos["destinatario"] = (
                            nombre_provisional.strip()
                        )

                    break

                if datos["cuenta_destino"]:
                    break

            if datos["cuenta_destino"]:
                break

    if datos["destinatario"] is None:

        for i, linea in enumerate(lineas6):

            if linea == "AL" and i + 1 < len(lineas6):

                posible_nombre = lineas6[i + 1]
                texto_invalido = (
                    "clabe",
                    "cuenta",
                    "banco",
                    "fecha",
                    "rfc"
                )

                if not any(
                    palabra in posible_nombre.lower()
                    for palabra in texto_invalido
                ):
                    datos["destinatario"] = posible_nombre
                    break

    if datos["cuenta_destino"] is None:

        for lineas in (lineas6, lineas11):

            for linea in lineas:

                if (
                    "clabe" in linea.lower()
                    and "clabe emisor" not in linea.lower()
                ):

                    cuenta = re.search(
                        r'(?:\*+|°|-)\s*(\d{3,4})\b',
                        linea
                    )

                    if cuenta:
                        datos["cuenta_destino"] = cuenta.group(1)
                        break

            if datos["cuenta_destino"]:
                break

    # ========================================================
    # COMISIÓN
    # ========================================================

    for linea in lineas6:

        if "comisi" in linea.lower():

            coincidencia = re.search(
                r'\$\s*([\d,]+\.\d{2})',
                linea
            )

            if coincidencia:

                try:
                    datos["comision"] = float(
                        coincidencia.group(1).replace(",", "")
                    )
                except ValueError:
                    pass

                break

    # ========================================================
    # CONCEPTO
    # ========================================================

    for i, linea in enumerate(lineas6):

        if "concepto de pago" in linea.lower():

            contenido = re.sub(
                r"(?i)^.*?concepto\s+de\s+pago\s*",
                "",
                linea
            ).strip()

            if contenido:
                datos["concepto"] = contenido

            elif i + 1 < len(lineas6):
                datos["concepto"] = lineas6[i + 1]

            break

    if datos["concepto"] is None:

        for i, linea in enumerate(lineas11):

            if "concepto de pago" in linea.lower():

                contenido = re.sub(
                    r"(?i)^.*?concepto\s+de\s+pago\s*",
                    "",
                    linea
                ).strip()

                if contenido:
                    datos["concepto"] = contenido

                elif i + 1 < len(lineas11):
                    datos["concepto"] = lineas11[i + 1]

                break

    if datos["concepto"] is None:

        for lineas in (lineas6, lineas11):

            for i, linea in enumerate(lineas):

                if "por el concepto" not in linea.lower():
                    continue

                contenido = re.sub(
                    r"(?i)^.*?por\s+el\s+concepto\s*",
                    "",
                    linea
                ).strip()

                if not contenido and i + 1 < len(lineas):
                    contenido = lineas[i + 1].strip()

                contenido = contenido.strip(
                    ' \t\"\'“”‘’.'
                )

                if contenido:
                    datos["concepto"] = contenido
                    break

            if datos["concepto"] is not None:
                break

    if datos["concepto"] is None:

        for i, linea in enumerate(lineas6):

            if "concepto" in linea.lower():

                contenido = re.sub(
                    r'(?i)concepto',
                    '',
                    linea
                ).strip()

                if contenido:
                    datos["concepto"] = contenido

                elif i + 1 < len(lineas6):
                    datos["concepto"] = lineas6[i + 1]

                break

    # ========================================================
    # TIPO DE OPERACIÓN
    # ========================================================

    for i, linea in enumerate(lineas6):

        if "tipo de operaci" in linea.lower():

            contenido = re.sub(
                r'(?i)tipo de operaci[oó]n',
                '',
                linea
            ).strip()

            if contenido:
                datos["tipo_operacion"] = contenido

            elif i + 1 < len(lineas6):
                datos["tipo_operacion"] = lineas6[i + 1]

            break

    # ========================================================
    # FOLIO
    # ========================================================

    for i, linea in enumerate(lineas6):

        if "folio" in linea.lower():

            numeros = re.findall(
                r'\b\d{6,}\b',
                linea
            )

            if numeros:
                datos["folio"] = numeros[-1]

            elif i + 1 < len(lineas6):

                numeros = re.findall(
                    r'\b\d{6,}\b',
                    lineas6[i + 1]
                )

                if numeros:
                    datos["folio"] = numeros[0]

            break

    # Fallback PSM11

    if datos["folio"] is None:

        for i, linea in enumerate(lineas11):

            if "folio" in linea.lower():

                alrededor = lineas11[
                    max(0, i - 2):i + 3
                ]

                for posible in alrededor:

                    numeros = re.findall(
                        r'\b\d{6,}\b',
                        posible
                    )

                    if numeros:
                        datos["folio"] = numeros[0]
                        break

            if datos["folio"]:
                break

    if datos["folio"] is None:

        for lineas in (lineas6, lineas11):

            for i, linea in enumerate(lineas):

                if "ref. supermóvil" in linea.lower() or \
                        "ref. supermovil" in linea.lower():

                    alrededor = lineas[max(0, i - 1):i + 2]

                    for posible in alrededor:

                        numeros = re.findall(
                            r'\b\d{6,}\b',
                            posible
                        )

                        if numeros:
                            datos["folio"] = numeros[0]
                            break

                if datos["folio"]:
                    break

            if datos["folio"]:
                break

    if datos["folio"] is None:

        for etiqueta in (
            "clave de rastreo",
            "número de autorización",
            "numero de autorizacion",
            "referencia numérica",
            "referencia numerica"
        ):

            for i, linea in enumerate(lineas11):

                if etiqueta in linea.lower():

                    alrededor = lineas11[i:i + 4]

                    for posible in alrededor:

                        numeros = re.findall(
                            r'\b\d{6,}\b',
                            posible
                        )

                        if numeros:
                            datos["folio"] = numeros[0]
                            break

                if datos["folio"]:
                    break

            if datos["folio"]:
                break

    # ========================================================
    # FECHA
    # ========================================================

    texto_combinado = texto_psm6 + "\n" + texto_psm11

    fecha = re.search(
        r'\b(\d{1,2}\s+'
        r'(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)'
        r'\s+\d{4})\b',
        texto_combinado,
        re.IGNORECASE
    )

    lineas_fecha_operacion = []

    for i, linea in enumerate(lineas11):

        if "fecha y hora" in linea.lower():
            lineas_fecha_operacion.extend(lineas11[i:i + 3])

    fecha_operacion = re.search(
        r'\b(\d{1,2}\s+'
        r'(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)'
        r'\s+\d{4})\b.{0,80}?'
        r'\b([01]?\d|2[0-3]):([0-5]\d)\b',
        "\n".join(lineas_fecha_operacion),
        re.IGNORECASE | re.DOTALL
    )

    fecha_hora_santander = re.search(
        r'\b(\d{1,2}/'
        r'(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)/'
        r'\d{4})\s*[-–]?\s*'
        r'([01]?\d|2[0-3]):([0-5]\d)\b',
        texto_combinado,
        re.IGNORECASE
    )

    lineas_fecha_hora_santander = []

    for i, linea in enumerate(lineas6 + lineas11):

        if (
            "fecha y hora de operacion" in linea.lower()
            or "fecha y hora de operación" in linea.lower()
        ):
            lineas_fecha_hora_santander.extend(
                (lineas6 + lineas11)[i:i + 3]
            )

    fecha_hora_santander_etiqueta = re.search(
        r'\b(\d{1,2}/'
        r'(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)/'
        r'\d{4})\s*[-–]?\s*'
        r'([01]?\d|2[0-3]):([0-5]\d)\b',
        "\n".join(lineas_fecha_hora_santander),
        re.IGNORECASE
    )

    if fecha_hora_santander_etiqueta:
        fecha_hora_santander = fecha_hora_santander_etiqueta

    if fecha_hora_santander:
        datos["fecha"] = fecha_hora_santander.group(1)
        datos["hora"] = (
            fecha_hora_santander.group(2)
            + ":"
            + fecha_hora_santander.group(3)
        )

    elif fecha_operacion:
        datos["fecha"] = fecha_operacion.group(1)
        datos["hora"] = (
            fecha_operacion.group(2) + ":" + fecha_operacion.group(3)
        )

    if fecha and datos["fecha"] is None:
        datos["fecha"] = fecha.group(1)

    if datos["fecha"] is None:

        fecha_santander = re.search(
            r'\b\d{1,2}/'
            r'(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)/'
            r'\d{4}\b',
            texto_combinado,
            re.IGNORECASE
        )

        if fecha_santander:
            datos["fecha"] = fecha_santander.group(0)

    # ========================================================
    # HORA
    # ========================================================

    hora = re.search(
        r'\b([01]?\d|2[0-3]):([0-5]\d)\b',
        texto_combinado
    )

    if hora and datos["hora"] is None:
        datos["hora"] = (
            hora.group(1) + ":" + hora.group(2)
        )

    return datos


def buscar_tmp_nuevo(archivos_antes, tiempo_maximo=30):
    tiempo_inicio = time.time()

    while time.time() - tiempo_inicio < tiempo_maximo:

        archivos_actuales = set(os.listdir(DOWNLOAD_PATH))
        nuevos = archivos_actuales - archivos_antes

        temporales = [
            archivo
            for archivo in nuevos
            if archivo.lower().endswith(".tmp")
        ]

        if temporales:
            nombre = temporales[0]
            ruta = os.path.join(DOWNLOAD_PATH, nombre)

            if os.path.exists(ruta):
                return ruta

        time.sleep(0.5)

    return None


def esperar_archivo_estable(ruta, tiempo_maximo=60):
    tiempo_inicio = time.time()
    ultimo_tamano = -1
    veces_estable = 0

    while time.time() - tiempo_inicio < tiempo_maximo:

        if not os.path.exists(ruta):
            time.sleep(0.5)
            continue

        tamano_actual = os.path.getsize(ruta)

        print(
            f"Archivo temporal: {tamano_actual:,} bytes"
        )

        if tamano_actual == ultimo_tamano:
            veces_estable += 1
        else:
            veces_estable = 0

        ultimo_tamano = tamano_actual

        if veces_estable >= 4:
            return True

        time.sleep(0.5)

    return False


def esperar_archivo_descargado(
    archivos_antes,
    nombre_esperado,
    tiempo_maximo=15,
    snapshot_antes=None,
    mensaje_id=None,
    suggested_filename=None
):
    tiempo_inicio = time.time()
    tamanos_anteriores = {}
    comprobaciones_estables = {}
    observados = {}

    if snapshot_antes is None:
        snapshot_antes = {
            archivo: (
                os.path.getsize(os.path.join(DOWNLOAD_PATH, archivo)),
                os.path.getmtime(os.path.join(DOWNLOAD_PATH, archivo))
            )
            for archivo in archivos_antes
            if os.path.exists(os.path.join(DOWNLOAD_PATH, archivo))
        }

    while time.time() - tiempo_inicio < tiempo_maximo:

        archivos_actuales = set(os.listdir(DOWNLOAD_PATH))

        candidatos = []

        ruta_esperada = os.path.join(
            DOWNLOAD_PATH,
            nombre_esperado
        )

        if os.path.exists(ruta_esperada):
            estado_anterior = snapshot_antes.get(nombre_esperado)

            try:
                es_nueva_o_modificada = (
                    estado_anterior is None
                    or os.path.getsize(ruta_esperada) != estado_anterior[0]
                    or os.path.getmtime(ruta_esperada) > estado_anterior[1]
                )
            except OSError:
                es_nueva_o_modificada = False

            if es_nueva_o_modificada:
                candidatos.append(ruta_esperada)

        for archivo in archivos_actuales:
            ruta = os.path.join(DOWNLOAD_PATH, archivo)
            estado_anterior = snapshot_antes.get(archivo)

            try:
                modificado = (
                    estado_anterior is None
                    or os.path.getsize(ruta) != estado_anterior[0]
                    or os.path.getmtime(ruta) > estado_anterior[1]
                )
            except OSError:
                continue

            if not modificado:
                continue

            if archivo.lower().endswith((".tmp", ".pdf", ".crdownload")):
                candidatos.append(ruta)

        for ruta in candidatos:

            if not os.path.exists(ruta):
                continue

            try:
                tamano_actual = os.path.getsize(ruta)
            except OSError:
                continue

            if tamano_actual <= 0:
                continue

            if tamanos_anteriores.get(ruta) == tamano_actual:
                comprobaciones_estables[ruta] = (
                    comprobaciones_estables.get(ruta, 0) + 1
                )
            else:
                comprobaciones_estables[ruta] = 1

            tamanos_anteriores[ruta] = tamano_actual

            if comprobaciones_estables[ruta] >= 2:
                try:
                    with open(ruta, "rb") as archivo_pdf:
                        primeros_bytes = archivo_pdf.read(8)

                    print("[DEBUG DOWNLOAD]")
                    print("Archivo:", ruta)
                    print("Tamaño:", tamano_actual)
                    print("Primeros bytes:", primeros_bytes)

                    if primeros_bytes.startswith(b"%PDF"):
                        return ruta
                except (OSError, PermissionError):
                    continue

        for archivo in archivos_actuales:
            ruta = os.path.join(DOWNLOAD_PATH, archivo)
            if ruta in observados or not os.path.exists(ruta):
                continue

            if archivo not in snapshot_antes:
                observados[archivo] = (
                    os.path.splitext(archivo)[1].lower(),
                    os.path.getsize(ruta),
                    os.path.getmtime(ruta)
                )

        time.sleep(0.25)

    print("[ERROR DESCARGA PDF]")
    print("Mensaje:", mensaje_id or "")
    print("Suggested filename:", suggested_filename or "")
    print("ARCHIVOS NUEVOS/MODIFICADOS OBSERVADOS:")

    for archivo, datos in observados.items():
        print(
            "-",
            archivo,
            "|",
            datos[0],
            "|",
            f"{datos[1]:,}",
            "|",
            datos[2]
        )

    return None


# ============================================================
# INICIAR PLAYWRIGHT
# ============================================================

def monitorear_chats_whatsapp(page):
    page.wait_for_selector(
        '[data-testid="chat-list"]',
        timeout=60000
    )

    mensajes_vistos = set()
    estado_chats = {}
    ids_conocidos_por_chat = {}

    def obtener_chats():
        chat_list = page.locator(
            '[data-testid="chat-list"]'
        )

        chats = chat_list.locator(
            '[data-testid^="list-item-"]'
        )

        if chats.count() == 0:
            chats = chat_list.locator(
                '[data-testid="cell-frame-container"]'
            )

        return chats

    def obtener_nombre_chat(fila):
        try:
            titulo = fila.locator(
                '[data-testid="cell-frame-title"]'
            )

            if titulo.count() == 0:
                return ""

            titulo = titulo.first
            spans_con_title = titulo.locator("span[title]")

            for i in range(spans_con_title.count()):
                nombre = normalizar_firma_chat(
                    spans_con_title.nth(i).get_attribute(
                        "title",
                        timeout=700
                    )
                )

                if nombre:
                    return nombre

            spans = titulo.locator("span")
            patron_no_leidos = re.compile(
                r'^\d+\s+mensajes?\s+no\s+leídos?$',
                re.IGNORECASE
            )

            for i in range(spans.count() - 1, -1, -1):
                texto = normalizar_firma_chat(
                    spans.nth(i).inner_text(timeout=700)
                )

                if texto and not patron_no_leidos.fullmatch(texto):
                    return texto

        except PlaywrightTimeoutError:
            return ""

        return ""

    def nombre_visible(chat):
        nombre = obtener_nombre_chat(chat)

        return nombre or "Chat sin nombre"

    def normalizar_firma_chat(texto):
        if texto is None:
            texto = ""

        texto = texto.replace("\r", " ")
        texto = texto.replace("\n", " ")
        texto = texto.replace("\t", " ")

        return " ".join(texto.split()).strip()

    def extraer_hora(texto):
        coincidencia = re.search(
            r'\b(\d{1,2}:\d{2})\s*'
            r'([ap])\.?\s*m\.?',
            texto.lower()
        )

        if coincidencia:
            return (
                coincidencia.group(1)
                + " "
                + coincidencia.group(2)
                + ".m."
            )

        coincidencia = re.search(
            r'\b(\d{1,2}:\d{2})\b',
            texto
        )

        return coincidencia.group(1) if coincidencia else None

    def tipo_esperado_de_firma(firma, preview=None):
        firma_normalizada = firma.lower()
        preview_normalizado = normalizar_firma_chat(
            preview
        ).lower()

        if preview_normalizado == "foto":
            return "IMAGEN"

        if (
            re.search(r'\b[^\s]+\.pdf\b', preview_normalizado)
            or re.search(r'\b[^\s]+\.pdf\b', firma_normalizada)
        ):
            return "PDF"

        return None

    def parece_comprobante_transferencia(texto):
        texto_normalizado = texto.lower()
        senales = (
            r'\btransferencia\b',
            r'\bspei\b',
            r'clave de rastreo',
            r'cuenta (?:origen|destino)',
            r'\bbeneficiario\b',
            r'\b(?:monto|importe)\b\s*\$?\s*[\d,.]+',
            r'\bbanco\b',
            r'\breferencia\b',
            r'\bcomprobante\b',
            r'\boperaci[oó]n\b',
            r'\bclabe\b',
            r'\b(?:enviado|enviaste)\b'
        )
        cantidad_senales = sum(
            bool(re.search(senal, texto_normalizado))
            for senal in senales
        )
        senales_fuertes = sum(
            bool(re.search(senal, texto_normalizado))
            for senal in (
                r'\$\s*[\d,.]+',
                r'cuenta|clabe',
                r'clave de rastreo|referencia',
                r'spei|transferencia'
            )
        )

        return cantidad_senales >= 3 and senales_fuertes >= 1

    def mostrar_datos_comprobante(
        nombre_chat,
        tipo_archivo,
        mensaje_id,
        datos_extraidos
    ):
        print()
        print("====================================")
        print("COMPROBANTE DE TRANSFERENCIA")
        print("====================================")
        print("Chat:", nombre_chat)
        print("Tipo:", tipo_archivo)
        print("Mensaje:", mensaje_id)
        print("Monto:", datos_extraidos["monto"])
        print("Destinatario:", datos_extraidos["destinatario"])
        print("Cuenta destino:", datos_extraidos["cuenta_destino"])
        print("Cuenta origen:", datos_extraidos["cuenta_origen"])
        print("Comisión:", datos_extraidos["comision"])
        print("Concepto:", datos_extraidos["concepto"])
        print("Tipo operación:", datos_extraidos["tipo_operacion"])
        print("Folio:", datos_extraidos["folio"])
        print("Fecha:", datos_extraidos["fecha"])
        print("Hora:", datos_extraidos["hora"])
        print("====================================")

    def debug_page(page, etapa):
        try:
            cerrado = page.is_closed()
            print(
                f"[DEBUG PAGE] {etapa} | "
                f"closed={cerrado} | "
                f"url={page.url if not cerrado else 'CLOSED'}"
            )
        except Exception as error:
            print(f"[DEBUG PAGE] {etapa} | ERROR: {error}")

    def debug_paginas_contexto(context, etapa):
        print()
        print(f"[DEBUG CONTEXT] {etapa}")

        try:
            paginas = context.pages
            print(f"Pages activas: {len(paginas)}")

            for i, pagina in enumerate(paginas):
                try:
                    cerrado = pagina.is_closed()
                    print(
                        f"  PAGE {i}: "
                        f"closed={cerrado} | "
                        f"url={pagina.url if not cerrado else 'CLOSED'}"
                    )
                except Exception as error:
                    print(f"  PAGE {i}: ERROR {error}")

        except Exception as error:
            print(f"[DEBUG CONTEXT ERROR] {error}")

    def buscar_page_whatsapp(context):
        for candidata in context.pages:
            if candidata.is_closed():
                continue

            try:
                if "web.whatsapp.com" in candidata.url:
                    return candidata
            except Exception:
                continue

        return None

    def cerrar_visor_pdf(page):
        try:
            if page.is_closed():
                print(
                    "[DEBUG] No se intenta cerrar visor porque la "
                    "Page original está cerrada."
                )
                return

            visor = page.locator(
                '[data-testid="pdf-viewer-iframe"]'
            )

            if visor.count() == 0 or not visor.first.is_visible():
                return

            botones = page.locator(
                'button[aria-label="Cerrar"], '
                'button[aria-label="Close"]'
            )

            cerrado = False

            for i in range(botones.count()):
                boton = botones.nth(i)

                if boton.is_visible():
                    boton.click(timeout=1000)
                    cerrado = True
                    page.wait_for_timeout(400)
                    break

            if not cerrado:
                for intento_escape in range(2):
                    if page.is_closed():
                        break

                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)

                    if (
                        visor.count() == 0
                        or not visor.first.is_visible()
                    ):
                        break

            if (
                not page.is_closed()
                and (
                    visor.count() == 0
                    or not visor.first.is_visible()
                )
            ):
                print("[PDF] Visor cerrado correctamente")
            else:
                print("[AVISO] Visor PDF continúa abierto")

        except Exception:
            print("[AVISO] No se pudo cerrar el visor PDF")

    def procesar_archivo_detectado(
        page,
        nombre_chat,
        mensaje_id,
        tipo_archivo
    ):
        try:
            debug_page(page, "inicio procesamiento")
            mensaje = page.locator(
                f'[data-testid="{mensaje_id}"]'
            )

            if mensaje.count() == 0:
                raise RuntimeError(
                    "No se encontró el mensaje detectado en el DOM."
                )

            mensaje = mensaje.first

            debug_page(page, "antes procesamiento")

            if tipo_archivo == "IMAGEN":
                imagen_thumb = mensaje.locator(
                    '[data-testid="image-thumb"]'
                )

                if imagen_thumb.count() == 0:
                    raise RuntimeError(
                        "No se encontró image-thumb en el mensaje."
                    )

                imagen_thumb.click()
                page.wait_for_timeout(1500)

                blobs = page.locator('img[src^="blob:"]')
                mejor_imagen = None
                mejor_area = 0

                for i in range(blobs.count()):
                    imagen = blobs.nth(i)
                    informacion = imagen.evaluate(
                        """
                        img => ({
                            naturalWidth: img.naturalWidth,
                            naturalHeight: img.naturalHeight
                        })
                        """
                    )
                    area = (
                        informacion["naturalWidth"]
                        * informacion["naturalHeight"]
                    )

                    if area > mejor_area:
                        mejor_area = area
                        mejor_imagen = imagen

                if mejor_imagen is None:
                    raise RuntimeError(
                        "No se encontró un BLOB de imagen válido."
                    )

                base64_imagen = mejor_imagen.evaluate(
                    """
                    async img => {
                        const response = await fetch(img.src);
                        const blob = await response.blob();
                        return await new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(
                                reader.result.split(',')[1]
                            );
                            reader.onerror = reject;
                            reader.readAsDataURL(blob);
                        });
                    }
                    """
                )
                datos_imagen = base64.b64decode(base64_imagen)
                ruta_original = os.path.join(
                    COMPROBANTES_PATH,
                    "comprobante_original.jpg"
                )

                with open(ruta_original, "wb") as archivo:
                    archivo.write(datos_imagen)

                imagen = Image.open(ruta_original)

                if imagen.mode != "RGB":
                    imagen = imagen.convert("RGB")

                texto_original = pytesseract.image_to_string(
                    imagen,
                    lang="spa+eng",
                    config="--psm 6"
                )
                procesada = ImageEnhance.Contrast(
                    imagen.convert("L")
                ).enhance(2.0)
                procesada = procesada.filter(ImageFilter.SHARPEN)

                if procesada.width < 1500:
                    procesada = procesada.resize(
                        (
                            procesada.width * 2,
                            procesada.height * 2
                        ),
                        Image.Resampling.LANCZOS
                    )

                texto_procesado = pytesseract.image_to_string(
                    procesada,
                    lang="spa+eng",
                    config="--psm 6"
                )
                texto_alternativo = pytesseract.image_to_string(
                    procesada,
                    lang="spa+eng",
                    config="--psm 11"
                )
                texto_clasificacion = (
                    texto_original + "\n"
                    + texto_procesado + "\n"
                    + texto_alternativo
                )

                if not parece_comprobante_transferencia(
                    texto_clasificacion
                ):
                    print("====================================")
                    print("ARCHIVO IGNORADO")
                    print("====================================")
                    print("Chat:", nombre_chat)
                    print("Tipo:", tipo_archivo)
                    print("Mensaje:", mensaje_id)
                    print(
                        "Motivo: no parece comprobante de transferencia"
                    )
                    print("====================================")
                    return

                datos_extraidos = extraer_datos_transferencia(
                    texto_procesado,
                    texto_alternativo
                )
                mostrar_datos_comprobante(
                    nombre_chat,
                    tipo_archivo,
                    mensaje_id,
                    datos_extraidos
                )
                return

            if tipo_archivo == "PDF":
                debug_page(page, "inicio PDF")
                pdf_thumb = mensaje.locator(
                    '[data-testid="document-thumb"], '
                    '[data-testid="document-PDF-icon"]'
                )

                if pdf_thumb.count() == 0:
                    raise RuntimeError(
                        "No se encontró el PDF en el mensaje."
                    )

                debug_page(page, "mensaje localizado")
                pdf_thumb.first.click()
                page.wait_for_timeout(2000)
                debug_page(page, "después click documento")
                debug_page(page, "visor PDF abierto")
                texto_mensaje = mensaje.inner_text()
                nombre_pdf_match = re.search(
                    r'([^\r\n]+?\.pdf)\b',
                    texto_mensaje,
                    re.IGNORECASE
                )

                if nombre_pdf_match:
                    nombre_pdf = nombre_pdf_match.group(1).strip()
                else:
                    nombre_pdf = f"comprobante_{mensaje_id}.pdf"

                nombre_pdf = re.sub(
                    r'[<>:"/\\|?*]',
                    "_",
                    nombre_pdf
                )

                if not nombre_pdf.lower().endswith(".pdf"):
                    nombre_pdf += ".pdf"

                iframe_element = page.locator(
                    '[data-testid="pdf-viewer-iframe"]'
                )

                if (
                    iframe_element.count() == 0
                    or not iframe_element.first.is_visible()
                ):
                    raise RuntimeError(
                        "No se encontró el iframe visible del PDF."
                    )

                pdf_frame = page.frame_locator(
                    '[data-testid="pdf-viewer-iframe"]'
                )

                frame_real = None

                for candidato in page.frames:
                    try:
                        if "webtp.whatsapp.net/pdf-viewer/" in candidato.url:
                            frame_real = candidato
                            break
                    except Exception:
                        continue

                if frame_real is None:
                    raise RuntimeError(
                        "No se encontró el Frame real del visor PDF."
                    )

                print("[DEBUG FRAME]", type(frame_real), "URL:", frame_real.url)
                print("[PDF FRAME]")
                print("URL:", frame_real.url)
                print(
                    "[PDF FRAME DOM] embed[src]:",
                    pdf_frame.locator("embed[src]").count()
                )
                print(
                    "[PDF FRAME DOM] object[data]:",
                    pdf_frame.locator("object[data]").count()
                )
                print(
                    "[PDF FRAME DOM] iframe[src]:",
                    pdf_frame.locator("iframe[src]").count()
                )
                print(
                    "[PDF FRAME DOM] a[href]:",
                    pdf_frame.locator("a[href]").count()
                )
                print(
                    "[PDF FRAME DOM] [src]:",
                    pdf_frame.locator("[src]").count()
                )

                atributos = frame_real.locator(
                    "embed[src], object[data], iframe[src], a[href], "
                    "[src], [data]"
                ).evaluate_all(
                    """
                    elementos => elementos.map(elemento => ({
                        tag: elemento.tagName,
                        src: elemento.getAttribute('src'),
                        href: elemento.getAttribute('href'),
                        data: elemento.getAttribute('data')
                    })).filter(item => item.src || item.href || item.data)
                    """
                )

                valores_relevantes = []

                for item in atributos:
                    for valor in (
                        item.get("src"),
                        item.get("href"),
                        item.get("data")
                    ):
                        if (
                            valor
                            and (
                                valor.startswith("blob:")
                                or ".pdf" in valor.lower()
                                or "whatsapp" in valor.lower()
                                or "media" in valor.lower()
                                or "document" in valor.lower()
                            )
                            and valor not in valores_relevantes
                        ):
                            valores_relevantes.append(valor)

                recursos = frame_real.evaluate(
                    """
                    () => performance.getEntriesByType('resource')
                        .map(entry => entry.name)
                        .filter(name => {
                            const value = name.toLowerCase();
                            return value.includes('pdf')
                                || value.includes('blob:')
                                || value.includes('whatsapp')
                                || value.includes('media')
                                || value.includes('document');
                        })
                        .slice(0, 30)
                    """
                )

                print("[PDF FRAME RESOURCES]")
                for i, recurso in enumerate(recursos, start=1):
                    print(f"{i}. {recurso}")

                blob_urls = [
                    valor for valor in valores_relevantes
                    if valor.startswith("blob:")
                ]

                if not blob_urls:
                    blob_urls = [
                        recurso for recurso in recursos
                        if recurso.startswith("blob:")
                    ]

                for blob_url in blob_urls:
                    print("[PDF BLOB ENCONTRADO]")
                    print(blob_url)

                datos_pdf = None

                for blob_url in blob_urls:
                    try:
                        base64_pdf = frame_real.evaluate(
                            """
                            async blobUrl => {
                                const response = await fetch(blobUrl);
                                const buffer = await response.arrayBuffer();
                                const bytes = new Uint8Array(buffer);
                                const chunk = 0x8000;
                                let binary = '';
                                for (let i = 0; i < bytes.length; i += chunk) {
                                    binary += String.fromCharCode(
                                        ...bytes.subarray(i, i + chunk)
                                    );
                                }
                                return btoa(binary);
                            }
                            """,
                            blob_url
                        )
                        candidato_pdf = base64.b64decode(base64_pdf)

                        if candidato_pdf.startswith(b"%PDF"):
                            datos_pdf = candidato_pdf
                            break
                    except Exception:
                        continue

                if datos_pdf is None:
                    cerrar_visor_pdf(page)
                    return

                ruta_final = os.path.join(
                    COMPROBANTES_PATH,
                    nombre_pdf
                )

                with open(ruta_final, "wb") as archivo_pdf:
                    archivo_pdf.write(datos_pdf)

                print("[PDF EXTRAÍDO DESDE VISOR]")
                print("Nombre:", nombre_pdf)
                print("Tamaño:", len(datos_pdf))
                print("Cabecera:", datos_pdf[:8])
                cerrar_visor_pdf(page)
                debug_page(page, "después cerrar visor")

                documento = pymupdf.open(ruta_final)
                textos_paginas = []
                textos_psm6 = []
                textos_psm11 = []

                try:
                    for pagina in documento:
                        textos_paginas.append(
                            pagina.get_text("text").strip()
                        )

                    texto_digital = "\n".join(textos_paginas).strip()

                    if len(texto_digital) >= 20:
                        texto_para_extraer_6 = texto_digital
                        texto_para_extraer_11 = texto_digital
                    else:
                        for pagina in documento:
                            pix = pagina.get_pixmap(
                                matrix=pymupdf.Matrix(2, 2),
                                alpha=False
                            )
                            imagen_pagina = Image.frombytes(
                                "RGB",
                                [pix.width, pix.height],
                                pix.samples
                            )
                            procesada = ImageEnhance.Contrast(
                                imagen_pagina.convert("L")
                            ).enhance(2.0)
                            procesada = procesada.filter(
                                ImageFilter.SHARPEN
                            )
                            textos_psm6.append(
                                pytesseract.image_to_string(
                                    procesada,
                                    lang="spa+eng",
                                    config="--psm 6"
                                )
                            )
                            textos_psm11.append(
                                pytesseract.image_to_string(
                                    procesada,
                                    lang="spa+eng",
                                    config="--psm 11"
                                )
                            )

                        texto_para_extraer_6 = "\n".join(textos_psm6)
                        texto_para_extraer_11 = "\n".join(textos_psm11)
                finally:
                    documento.close()

                debug_page(page, "después PyMuPDF")

                ruta_resultado_pdf = os.path.join(
                    COMPROBANTES_PATH,
                    "resultado_pdf.txt"
                )

                with open(
                    ruta_resultado_pdf,
                    "w",
                    encoding="utf-8"
                ) as archivo_pdf:
                    archivo_pdf.write(
                        "====================================\n"
                        "TEXTO PDF / PSM 6\n"
                        "====================================\n\n"
                        f"{texto_para_extraer_6}\n\n"
                        "====================================\n"
                        "TEXTO PDF / PSM 11\n"
                        "====================================\n\n"
                        f"{texto_para_extraer_11}\n"
                    )

                texto_clasificacion = (
                    texto_para_extraer_6 + "\n"
                    + texto_para_extraer_11
                )

                if not parece_comprobante_transferencia(
                    texto_clasificacion
                ):
                    print("====================================")
                    print("ARCHIVO IGNORADO")
                    print("====================================")
                    print("Chat:", nombre_chat)
                    print("Tipo:", tipo_archivo)
                    print("Mensaje:", mensaje_id)
                    print(
                        "Motivo: no parece comprobante de transferencia"
                    )
                    print("====================================")
                    debug_page(page, "después clasificación")
                    cerrar_visor_pdf(page)
                    debug_page(page, "después cerrar visor")
                    return

                datos_extraidos = extraer_datos_transferencia(
                    texto_para_extraer_6,
                    texto_para_extraer_11
                )
                mostrar_datos_comprobante(
                    nombre_chat,
                    tipo_archivo,
                    mensaje_id,
                    datos_extraidos
                )
                cerrar_visor_pdf(page)
                debug_page(page, "después cerrar visor")

        except Exception as error:
            print("[ERROR PROCESANDO ARCHIVO]")
            print("Chat:", nombre_chat)
            print("Mensaje:", mensaje_id)
            print("Error:", error)
            cerrar_visor_pdf(page)
            debug_page(page, "después cerrar visor")

    def revisar_chat(
        nombre,
        firma_actual,
        preview_actual=None,
        encabezado_archivo="NUEVO ARCHIVO DETECTADO"
    ):
        page.wait_for_selector(
            '[data-testid="conversation-panel-messages"]',
            timeout=5000
        )

        page.wait_for_timeout(500)

        controles = page.locator(
            'button, [role="button"]'
        )
        botones_candidatos = []

        for i in range(controles.count()):
            control = controles.nth(i)

            try:
                if not control.is_visible():
                    continue

                aria_label = control.get_attribute("aria-label") or ""
                title = control.get_attribute("title") or ""
                data_testid = control.get_attribute("data-testid") or ""
            except Exception:
                continue

            atributos = (
                aria_label + " " + title + " " + data_testid
            ).lower()

            palabras_scroll = (
                "abajo",
                "down",
                "bottom",
                "último",
                "ultimo",
                "scroll",
                "mensaje nuevo",
                "new message"
            )

            if not any(
                palabra in atributos
                for palabra in palabras_scroll
            ):
                continue

            botones_candidatos.append(control)

        boton_nativo = None

        if botones_candidatos:
            boton_nativo = botones_candidatos[0]

        for intento_scroll in range(1, 4):
            if boton_nativo is not None:
                try:
                    boton_nativo.click()
                    page.wait_for_timeout(800)

                    mensajes_despues = page.locator(
                        '[data-testid^="conv-msg-"]'
                    )
                    cantidad_despues = mensajes_despues.count()
                    ultimo_despues = None

                    if cantidad_despues > 0:
                        ultimo_despues = (
                            mensajes_despues.nth(
                                cantidad_despues - 1
                            ).get_attribute("data-testid")
                        )

                    continue

                except Exception:
                    boton_nativo = None

            mensajes_scroll = page.locator(
                '[data-testid^="conv-msg-"]'
            )

            if mensajes_scroll.count() == 0:
                break

            metricas_scroll = mensajes_scroll.nth(0).evaluate(
                """
                element => {
                    let actual = element.parentElement;

                    while (actual) {
                        const estilo = getComputedStyle(actual);
                        const desplazable = (
                            actual.scrollHeight > actual.clientHeight
                            && (
                                estilo.overflowY === 'auto'
                                || estilo.overflowY === 'scroll'
                                || actual.scrollHeight > actual.clientHeight
                            )
                        );

                        if (desplazable) {
                            const antes = actual.scrollTop;
                            actual.scrollTop = actual.scrollHeight;
                            actual.dispatchEvent(
                                new Event('scroll', {bubbles: true})
                            );

                            return {
                                encontrado: true,
                                scrollHeight: actual.scrollHeight,
                                clientHeight: actual.clientHeight,
                                scrollTopAntes: antes,
                                scrollTopDespues: actual.scrollTop
                            };
                        }

                        actual = actual.parentElement;
                    }

                    return {encontrado: false};
                }
                """
            )

            if not metricas_scroll["encontrado"]:
                break

            page.wait_for_timeout(800)

            mensajes_despues = page.locator(
                '[data-testid^="conv-msg-"]'
            )
            cantidad_despues = mensajes_despues.count()
            ultimo_despues = None

            if cantidad_despues > 0:
                ultimo_despues = mensajes_despues.nth(
                    cantidad_despues - 1
                ).get_attribute("data-testid")


        tipo_esperado = tipo_esperado_de_firma(
            firma_actual,
            preview_actual
        )

        if tipo_esperado is None:
            return

        hora_firma = extraer_hora(firma_actual)

        mensajes = page.locator(
            '[data-testid^="conv-msg-"]'
        )

        cantidad_mensajes = mensajes.count()

        print(
            "[CHAT ABIERTO]",
            nombre,
            "| mensajes visibles:",
            cantidad_mensajes
        )

        candidatos = []
        inicio = max(0, cantidad_mensajes - 10)

        for i in range(inicio, cantidad_mensajes):
            mensaje = mensajes.nth(i)

            meta_locator = mensaje.locator(
                '[data-testid="msg-meta"]'
            )
            meta = ""

            if meta_locator.count() > 0:
                meta = meta_locator.first.inner_text().strip()

            hora_mensaje = extraer_hora(meta)

            if hora_mensaje is None:
                pre_plain = mensaje.get_attribute(
                    "data-pre-plain-text"
                ) or ""
                hora_mensaje = extraer_hora(pre_plain)

            imagen = mensaje.locator(
                '[data-testid="image-thumb"]'
            )

            pdf = mensaje.locator(
                '[data-testid="document-thumb"], '
                '[data-testid="document-PDF-icon"]'
            )

            if imagen.count() > 0:
                tipo_mensaje = "IMAGEN"
            elif pdf.count() > 0:
                tipo_mensaje = "PDF"
            else:
                tipo_mensaje = "OTRO"

            if (
                hora_firma
                and hora_mensaje
                and hora_mensaje.split()[0] == hora_firma.split()[0]
                and tipo_mensaje == tipo_esperado
            ):
                candidatos.append(
                    (mensaje, mensaje.get_attribute("data-testid"))
                )

        if not candidatos:
            print(
                "[AVISO] Actividad de archivo detectada en",
                nombre,
                "pero no se encontró un mensaje reciente coincidente."
            )
            return

        mensaje, id_mensaje = candidatos[-1]

        if not id_mensaje or id_mensaje in mensajes_vistos:
            return

        mensajes_vistos.add(id_mensaje)

        print()
        print("====================================")
        print(encabezado_archivo)
        print("====================================")
        print("Chat:", nombre)
        print("Tipo:", tipo_esperado)
        print("Mensaje:", id_mensaje)
        print("Hora:", hora_firma)
        print("====================================")

        print(
            f"[DEBUG PAGE] antes procesamiento | "
            f"closed={page.is_closed()}"
        )

        procesar_archivo_detectado(
            page,
            nombre,
            id_mensaje,
            tipo_esperado
        )

        print(
            f"[DEBUG PAGE] después procesamiento | "
            f"closed={page.is_closed()}"
        )

        return

        mensajes = page.locator(
            '[data-testid^="conv-msg-"]'
        )

        cantidad_mensajes = mensajes.count()

        print(
            "[CHAT ABIERTO]",
            nombre,
            "| mensajes visibles:",
            cantidad_mensajes
        )

        ids_conocidos_por_chat[nombre] = set()

        for i in range(cantidad_mensajes):
            mensaje_id = mensajes.nth(i).get_attribute("data-testid")

            if mensaje_id:
                ids_conocidos_por_chat[nombre].add(mensaje_id)

        firma_horas = re.findall(
            r'\b\d{1,2}:\d{2}\b',
            firma_actual
        )

        hora_firma = firma_horas[-1] if firma_horas else None

        inicio_debug = max(0, cantidad_mensajes - 5)

        for i in range(inicio_debug, cantidad_mensajes):
            mensaje = mensajes.nth(i)
            mensaje_id = mensaje.get_attribute("data-testid")

            pre_plain = mensaje.get_attribute(
                "data-pre-plain-text"
            )

            if not pre_plain:
                pre_plain_locator = mensaje.locator(
                    "[data-pre-plain-text]"
                )

                if pre_plain_locator.count() > 0:
                    pre_plain = pre_plain_locator.first.get_attribute(
                        "data-pre-plain-text"
                    )

            meta_locator = mensaje.locator(
                '[data-testid="msg-meta"]'
            )
            meta = ""

            if meta_locator.count() > 0:
                meta = meta_locator.first.inner_text().strip()

            texto = mensaje.inner_text().strip()
            texto = " ".join(texto.split())[:200]

            imagen = mensaje.locator(
                '[data-testid="image-thumb"]'
            )

            pdf = mensaje.locator(
                '[data-testid="document-thumb"], '
                '[data-testid="document-PDF-icon"]'
            )

            if imagen.count() > 0:
                tipo = "IMAGEN"
            elif pdf.count() > 0:
                tipo = "PDF"
            else:
                tipo = "OTRO"

            print("------------------------------------")
            print("[DEBUG MENSAJE]")
            print("ID:", mensaje_id)
            print("PRE-PLAIN:", pre_plain or "")
            print("META:", meta)
            print("TEXTO:", texto)
            print("TIPO:", tipo)
            print("------------------------------------")

            metadatos = (pre_plain or "") + " " + meta

            if hora_firma and hora_firma in metadatos:
                print(">>> CANDIDATO POR HORA <<<")

    def obtener_snapshot(fila):
        try:
            primary_locator = fila.locator(
                '[data-testid="cell-frame-primary-detail"]'
            )
            secondary_locator = fila.locator(
                '[data-testid="cell-frame-secondary"]'
            )
            unread_locator = fila.locator(
                '[data-testid="icon-unread-count"]'
            )

            primary = ""
            secondary = ""
            no_leidos = ""

            if primary_locator.count() > 0:
                primary = normalizar_firma_chat(
                    primary_locator.first.inner_text(timeout=700)
                )

            if secondary_locator.count() > 0:
                secondary = normalizar_firma_chat(
                    secondary_locator.first.inner_text(timeout=700)
                )

            if unread_locator.count() > 0:
                no_leidos = normalizar_firma_chat(
                    unread_locator.first.inner_text(timeout=700)
                )

            nombre = obtener_nombre_chat(fila)
            texto_completo = normalizar_firma_chat(
                fila.inner_text(timeout=700)
            )

            return {
                "nombre": nombre,
                "hora": primary,
                "preview": secondary,
                "no_leidos": no_leidos,
                "texto_completo": texto_completo
            }

        except PlaywrightTimeoutError:
            raise

    def firma_monitor(snapshot):
        nombre = normalizar_firma_chat(snapshot.get("nombre"))
        hora = normalizar_firma_chat(snapshot.get("hora"))
        preview = normalizar_firma_chat(snapshot.get("preview"))

        preview = re.sub(
            r'\b\d+\s+mensajes?\s+no\s+leídos?\b',
            "",
            preview,
            flags=re.IGNORECASE
        )

        preview = normalizar_firma_chat(preview)

        return normalizar_firma_chat(
            nombre + " " + hora + " " + preview
        )

    def mostrar_lista(valores):
        if not valores:
            return ""

        return " | ".join(valores)

    print("WhatsApp Web abierto.")
    print("Preparando estado inicial de chats...")

    # DEBUG TEMPORAL: snapshot inicial sin abrir ningún chat.
    snapshot_chats = {}
    orden_anterior = []

    chats = page.locator(
        '[data-testid="cell-frame-container"]'
    )

    for i in range(chats.count()):
        try:
            fila = chats.nth(i)
            nombre = nombre_visible(fila)
            snapshot = obtener_snapshot(fila)
            estado_chats[nombre] = snapshot
            snapshot_chats[nombre] = snapshot
            orden_anterior.append(nombre)
        except Exception:
            continue

    print("Preparando revisión inicial de chats no leídos...")

    def localizar_fila_por_nombre(nombre_buscado):
        filas_actuales = page.locator(
            '[data-testid="cell-frame-container"]'
        )

        for i in range(filas_actuales.count()):
            fila = filas_actuales.nth(i)
            nombre_fila = obtener_nombre_chat(fila)

            if (
                normalizar_firma_chat(nombre_fila).casefold()
                == normalizar_firma_chat(nombre_buscado).casefold()
            ):
                return fila

        return None

    def confirmar_chat_abierto(nombre_buscado):
        try:
            page.wait_for_selector(
                '[data-testid="conversation-panel-messages"]',
                timeout=5000
            )
        except Exception:
            return False

        return True

    def revisar_no_leidos_iniciales():
        filas_iniciales = page.locator(
            '[data-testid="cell-frame-container"]'
        )
        no_leidos = []

        for i in range(filas_iniciales.count()):
            fila = filas_iniciales.nth(i)
            nombre_chat = obtener_nombre_chat(fila)
            indicador = fila.locator(
                '[data-testid="icon-unread-count"]'
            )

            if (
                not nombre_chat
                or nombre_chat.lower() == "archivados"
                or indicador.count() == 0
                or not indicador.first.is_visible()
            ):
                continue

            contador = normalizar_firma_chat(
                indicador.first.inner_text()
            )

            if not contador:
                contador = (
                    indicador.first.get_attribute("aria-label")
                    or "1"
                )

            snapshot = obtener_snapshot(fila)
            no_leidos.append(
                {
                    "nombre": nombre_chat,
                    "contador": contador,
                    "firma": snapshot["texto_completo"],
                    "preview": snapshot["preview"]
                }
            )

        print("====================================")
        print("REVISIÓN INICIAL")
        print("====================================")
        print("Chats visibles:", filas_iniciales.count())
        print("Chats con mensajes no leídos:", len(no_leidos))

        for chat_no_leido in no_leidos:
            print(
                "[NO LEÍDO]",
                chat_no_leido["nombre"],
                "|",
                chat_no_leido["contador"]
            )

        print("====================================")

        for chat_no_leido in no_leidos:
            nombre = chat_no_leido["nombre"]
            fila = localizar_fila_por_nombre(nombre)

            if fila is None:
                print(
                    "[AVISO] No se encontró actualmente la fila del chat:",
                    nombre
                )
                continue

            if nombre.lower() == "archivados":
                continue

            nombre_encontrado = obtener_nombre_chat(fila)

            print("[VALIDACIÓN]")
            print("Buscado:", nombre)
            print("Encontrado:", nombre_encontrado)
            print(
                "Coincide:",
                normalizar_firma_chat(nombre_encontrado).casefold()
                == normalizar_firma_chat(nombre).casefold()
            )

            print("[ABRIENDO CHAT]", nombre)
            fila.click()

            if not confirmar_chat_abierto(nombre):
                print(
                    "[ERROR] No se pudo confirmar que se abrió el chat:",
                    nombre
                )
                continue

            print("[CHAT ABIERTO]", nombre)

            if tipo_esperado_de_firma(
                chat_no_leido["firma"],
                chat_no_leido["preview"]
            ) is None:
                print(
                    "[AVISO] Chat",
                    nombre,
                    "tiene mensajes no leídos, pero no se pudo asociar "
                    "con seguridad un archivo nuevo."
                )
                continue

            revisar_chat(
                nombre,
                chat_no_leido["firma"],
                chat_no_leido["preview"],
                "ARCHIVO PENDIENTE DETECTADO"
            )

    def diagnosticar_titulos_no_leidos():
        filas = page.locator(
            '[data-testid="cell-frame-container"]'
        )

        for i in range(filas.count()):
            fila = filas.nth(i)
            indicador = fila.locator(
                '[data-testid="icon-unread-count"]'
            )

            if (
                indicador.count() == 0
                or not indicador.first.is_visible()
            ):
                continue

            titulo = fila.locator(
                '[data-testid="cell-frame-title"]'
            )

            if titulo.count() == 0:
                continue

            texto_titulo = titulo.first.inner_text().strip()

            if "archivados" in texto_titulo.lower():
                continue

            print("====================================")
            print("[DEBUG TITULO CHAT]")
            print("====================================")
            print("INNER_TEXT:")
            print(titulo.first.inner_text())
            print("TEXT_CONTENT:")
            print(titulo.first.text_content())
            print(
                "ARIA-LABEL DEL TITULO:",
                titulo.first.get_attribute("aria-label")
            )
            print(
                "TITLE DEL TITULO:",
                titulo.first.get_attribute("title")
            )

            hijos = titulo.first.locator("*")

            for j in range(hijos.count()):
                hijo = hijos.nth(j)
                informacion = hijo.evaluate(
                    """
                    elemento => ({
                        tagName: elemento.tagName,
                        text: elemento.innerText,
                        textContent: elemento.textContent,
                        aria: elemento.getAttribute('aria-label'),
                        title: elemento.getAttribute('title'),
                        dataTestid: elemento.getAttribute('data-testid'),
                        role: elemento.getAttribute('role')
                    })
                    """
                )

                print()
                print(f"[HIJO {j + 1}]")
                print("TAG:", informacion["tagName"])
                print("TEXT:", informacion["text"])
                print("TEXT_CONTENT:", informacion["textContent"])
                print("ARIA:", informacion["aria"])
                print("TITLE:", informacion["title"])
                print("DATA-TESTID:", informacion["dataTestid"])
                print("ROLE:", informacion["role"])

            print()
            print("[CONTADOR]")
            print(
                "INNER_TEXT:",
                indicador.first.inner_text()
            )
            print(
                "TEXT_CONTENT:",
                indicador.first.text_content()
            )
            print(
                "ARIA:",
                indicador.first.get_attribute("aria-label")
            )
            print(
                "TITLE:",
                indicador.first.get_attribute("title")
            )
            print("====================================")

    def monitor_whatsapp():
        estado_chats.clear()
        filas_actuales = page.locator(
            '[data-testid="cell-frame-container"]'
        )

        for i in range(filas_actuales.count()):
            fila = filas_actuales.nth(i)
            snapshot = obtener_snapshot(fila)
            estado_chats[snapshot["nombre"]] = firma_monitor(snapshot)

        print("====================================")
        print("REVISIÓN INICIAL COMPLETADA")
        print("Iniciando monitor en tiempo real...")
        print("====================================")
        print("MONITOR DE WHATSAPP INICIADO")
        print("Observando todos los chats...")
        print("Esperando mensajes nuevos...")

        while True:
            try:
                if page.is_closed():
                    print(
                        "[ERROR FATAL] La página principal de WhatsApp "
                        "fue cerrada."
                    )
                    break

                filas = page.locator(
                    '[data-testid="cell-frame-container"]'
                )

                for i in range(filas.count()):
                    try:
                        fila = filas.nth(i)
                        snapshot = obtener_snapshot(fila)
                    except PlaywrightTimeoutError:
                        continue

                    nombre = snapshot["nombre"]

                    if nombre not in estado_chats:
                        estado_chats[nombre] = firma_monitor(snapshot)
                        continue

                    snapshot_anterior = estado_chats[nombre]
                    firma_actual = firma_monitor(snapshot)

                    if firma_actual == snapshot_anterior:
                        continue

                    estado_chats[nombre] = firma_actual
                    tipo_esperado = tipo_esperado_de_firma(
                        firma_actual,
                        snapshot["preview"]
                    )

                    if tipo_esperado is None:
                        continue

                    print("[CAMBIO DETECTADO] Chat:", nombre)
                    print(
                        "Antes:",
                        snapshot_anterior
                    )
                    print("Ahora:", firma_actual)

                    fila.click()
                    page.wait_for_timeout(500)
                    revisar_chat(
                        nombre,
                        snapshot["texto_completo"],
                        snapshot["preview"]
                    )

                print(
                    "[MONITOR] activo | chats visibles:",
                    filas.count()
                )
                time.sleep(1)

            except KeyboardInterrupt:
                print()
                print("Monitor detenido por el usuario.")
                return

            except Exception as error:
                mensaje_error = str(error).lower()

                if (
                    "target page" in mensaje_error
                    or "context or browser has been closed"
                    in mensaje_error
                    or "page, context or browser has been closed"
                    in mensaje_error
                ):
                    print(
                        "[ERROR FATAL] Se perdió la sesión de WhatsApp "
                        "Web. Monitor detenido."
                    )
                    break

                print("[ERROR] Monitor:", error)
                time.sleep(1)

    revisar_no_leidos_iniciales()
    monitor_whatsapp()
    return

    # DEBUG TEMPORAL: observar únicamente snapshots estructurados de filas.
    while True:
        try:
            chats = page.locator(
                '[data-testid="cell-frame-container"]'
            )

            for i in range(chats.count()):
                try:
                    fila = chats.nth(i)
                    snapshot = obtener_snapshot(fila)
                    nombre = snapshot["nombre"]

                    if nombre not in estado_chats:
                        estado_chats[nombre] = snapshot

                        if snapshot["no_leidos"] not in ("", "0"):
                            print(
                                "[DEBUG CHAT NUEVO CON NO LEÍDOS]"
                            )
                            print("Chat:", nombre)
                            print("Hora:", snapshot["hora"])
                            print(
                                "Preview:",
                                snapshot["preview"]
                            )
                            print(
                                "No leídos:",
                                snapshot["no_leidos"]
                            )

                        continue

                    snapshot_anterior = estado_chats[nombre]

                    if snapshot == snapshot_anterior:
                        continue

                    print("====================================")
                    print("[DEBUG FILA]")
                    print("Chat:", nombre)
                    print("Hora:", snapshot["hora"])
                    print("Preview:", snapshot["preview"])
                    print("No leídos:", snapshot["no_leidos"])
                    print(
                        "Texto completo:",
                        snapshot["texto_completo"]
                    )
                    print("====================================")

                    estado_chats[nombre] = snapshot

                except Exception:
                    continue

            time.sleep(1)

        except KeyboardInterrupt:
            print()
            print("Monitor detenido por el usuario.")
            return

        except Exception as error:
            print("[ERROR] Diagnóstico de filas:", error)
            time.sleep(1)

    while True:
        try:
            # DEBUG TEMPORAL: consultar las filas desde cero en cada ciclo.
            chats = page.locator(
                '[data-testid="cell-frame-container"]'
            )

            snapshot_actual = {}
            orden_actual = []

            for i in range(chats.count()):
                try:
                    fila = chats.nth(i)
                    nombre = nombre_visible(fila)
                    snapshot = obtener_snapshot(fila)
                    firma_actual = normalizar_firma_chat(
                        fila.inner_text()
                    )

                    firma_normalizada = firma_actual.lower().strip()

                    if (
                        "escribiendo" in firma_normalizada
                        or "grabando audio" in firma_normalizada
                        or "grabando" in firma_normalizada
                    ):
                        continue

                    snapshot_actual[nombre] = snapshot
                    orden_actual.append(nombre)

                    if nombre not in estado_chats:
                        estado_chats[nombre] = firma_actual
                        continue

                    firma_anterior = estado_chats[nombre]

                    if firma_actual == firma_anterior:
                        continue

                    if (
                        normalizar_firma_chat(firma_anterior)
                        == normalizar_firma_chat(firma_actual)
                    ):
                        continue

                    tipo_esperado = tipo_esperado_de_firma(
                        firma_actual
                    )

                    if tipo_esperado is None:
                        estado_chats[nombre] = firma_actual
                        continue

                    estado_chats[nombre] = firma_actual

                    print("[CAMBIO DETECTADO] Chat:", nombre)
                    print("Antes:", firma_anterior)
                    print("Ahora:", firma_actual)

                    fila.click()
                    page.wait_for_timeout(500)
                    revisar_chat(nombre, firma_actual)
                    continue

                    if nombre not in snapshot_chats:
                        print("====================================")
                        print("[DEBUG FILA NUEVA EN DOM]")
                        print("Chat:", nombre)
                        print("Posición:", i)
                        print("Texto:", snapshot["texto"])
                        print(
                            "Data-testids:",
                            mostrar_lista(snapshot["data_testids"])
                        )
                        print(
                            "Aria-labels:",
                            mostrar_lista(snapshot["aria_labels"])
                        )
                        print("====================================")
                        continue

                    anterior = snapshot_chats[nombre]

                    if snapshot == anterior:
                        continue

                    print("====================================")
                    print("[DEBUG FILA MODIFICADA]")
                    print("Chat:", nombre)
                    print("TEXTO ANTES:", anterior["texto"])
                    print("TEXTO AHORA:", snapshot["texto"])
                    print("PRIMARY ANTES:", anterior["primary"])
                    print("PRIMARY AHORA:", snapshot["primary"])
                    print(
                        "SECONDARY ANTES:",
                        anterior["secondary"]
                    )
                    print(
                        "SECONDARY AHORA:",
                        snapshot["secondary"]
                    )
                    print(
                        "DATA-TESTIDS ANTES:",
                        mostrar_lista(anterior["data_testids"])
                    )
                    print(
                        "DATA-TESTIDS AHORA:",
                        mostrar_lista(snapshot["data_testids"])
                    )
                    print(
                        "ARIA ANTES:",
                        mostrar_lista(anterior["aria_labels"])
                    )
                    print(
                        "ARIA AHORA:",
                        mostrar_lista(snapshot["aria_labels"])
                    )
                    print("====================================")

                except Exception:
                    print("[DEBUG] No se pudo leer una fila temporalmente.")

            snapshot_chats = snapshot_actual
            orden_anterior = orden_actual

            print(
                "[MONITOR] activo | chats visibles:",
                len(orden_actual)
            )

            time.sleep(1)

        except KeyboardInterrupt:
            print()
            print("Monitor detenido por el usuario.")
            break

        except Exception:
            print("[MONITOR] DOM actualizado, reintentando...")
            time.sleep(2)

with sync_playwright() as p:

    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_PATH,
        executable_path=CHROME_PATH,
        headless=False,
        viewport={
            "width": 1400,
            "height": 900
        }
    )

    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    context.on(
        "page",
        lambda nueva: print(
            "[EVENTO CONTEXT] NUEVA PAGE:",
            nueva.url
        )
    )

    page.on(
        "close",
        lambda: print(
            "!!!!!!!! PAGE PRINCIPAL CERRADA !!!!!!!!"
        )
    )

    page.goto("https://web.whatsapp.com")

    try:
        monitorear_chats_whatsapp(page)
    finally:
        context.close()

    raise SystemExit

    # ========================================================
    # LOCALIZAR CONVERSACIÓN
    # ========================================================

    conversacion = page.locator(
        '[data-testid="conversation-panel-messages"]'
    )

    mensajes = conversacion.locator(
        '[data-testid^="conv-msg-"]'
    )

    cantidad = mensajes.count()

    print()
    print("Mensajes encontrados:", cantidad)

    # ========================================================
    # BUSCAR ÚLTIMO COMPROBANTE
    # ========================================================

    tipo_comprobante = None
    mensaje_comprobante = None
    imagen_thumb = None
    pdf_thumb = None

    for i in range(cantidad - 1, -1, -1):

        mensaje = mensajes.nth(i)

        imagenes_mensaje = mensaje.locator(
            '[data-testid="image-thumb"]'
        )

        pdf_mensaje = mensaje.locator(
            '[data-testid="document-thumb"], '
            '[data-testid="document-PDF-icon"]'
        )

        if imagenes_mensaje.count() > 0:

            tipo_comprobante = "imagen"
            mensaje_comprobante = mensaje
            imagen_thumb = imagenes_mensaje.first

            print()
            print("====================================")
            print("COMPROBANTE ENCONTRADO")
            print("====================================")
            print("Tipo: IMAGEN")

            print(
                "Mensaje:",
                mensaje.get_attribute("data-testid")
            )

            break

        if pdf_mensaje.count() > 0:

            tipo_comprobante = "pdf"
            mensaje_comprobante = mensaje
            pdf_thumb = pdf_mensaje.first

            print()
            print("====================================")
            print("COMPROBANTE ENCONTRADO")
            print("====================================")
            print("Tipo: PDF")

            print(
                "Mensaje:",
                mensaje.get_attribute("data-testid")
            )

            break

    if mensaje_comprobante is None:

        print("No se encontró ninguna imagen ni PDF.")
        input("Presiona ENTER para cerrar...")
        raise SystemExit

    if tipo_comprobante == "pdf":
        procesando_pdf = False

        try:
            pdf_thumb.click()

            page.wait_for_timeout(2000)

            boton_descargar = page.locator(
                'button[aria-label="Descargar"]'
            )

            if boton_descargar.count() == 0:
                boton_descargar = page.locator(
                    '[data-testid="ic-download"]'
                )

            if boton_descargar.count() == 0:
                raise RuntimeError(
                    "No se encontró el botón de descarga del PDF."
                )

            archivos_antes = set(os.listdir(DOWNLOAD_PATH))

            with page.expect_download(timeout=15000) as download_info:
                boton_descargar.first.click()

            download = download_info.value

            nombre_pdf = download.suggested_filename

            if not nombre_pdf:
                nombre_pdf = "comprobante.pdf"
            elif not nombre_pdf.lower().endswith(".pdf"):
                nombre_pdf += ".pdf"

            ruta_descargada = esperar_archivo_descargado(
                archivos_antes,
                nombre_pdf,
                60
            )

            if ruta_descargada is None:
                raise RuntimeError(
                    "No se pudo localizar el archivo PDF descargado."
                )

            ruta_final = os.path.join(
                COMPROBANTES_PATH,
                nombre_pdf
            )

            if os.path.abspath(ruta_descargada) != os.path.abspath(ruta_final):
                shutil.copy2(
                    ruta_descargada,
                    ruta_final
                )

            if (
                not os.path.exists(ruta_final)
                or os.path.getsize(ruta_final) <= 0
            ):
                raise RuntimeError(
                    "El PDF descargado no es válido o está vacío."
                )

            tamano_final = os.path.getsize(ruta_final)

            print()
            print("====================================")
            print("PDF DESCARGADO CORRECTAMENTE")
            print("====================================")
            print("Nombre:", nombre_pdf)
            print("Ruta:", ruta_final)
            print(f"Tamaño: {tamano_final:,} bytes")

            procesando_pdf = True

            print()
            print("====================================")
            print("ANALIZANDO PDF")
            print("====================================")

            documento = pymupdf.open(ruta_final)
            print("Páginas:", len(documento))

            try:
                textos_paginas = []

                for numero_pagina, pagina in enumerate(documento):

                    texto_pagina = pagina.get_text("text").strip()

                    textos_paginas.append(texto_pagina)

                    print(
                        f"Página {numero_pagina + 1}: "
                        f"{len(texto_pagina)} caracteres de texto digital"
                    )

                texto_digital = "\n".join(textos_paginas).strip()

                if len(texto_digital) >= 20:
                    print()
                    print("====================================")
                    print("TEXTO DIGITAL DETECTADO")
                    print("====================================")
                    print(texto_digital)

                    texto_para_extraer_6 = texto_digital
                    texto_para_extraer_11 = texto_digital

                else:
                    print()
                    print("====================================")
                    print("PDF ESCANEADO - INICIANDO OCR")
                    print("====================================")

                    textos_psm6 = []
                    textos_psm11 = []

                    for pagina in documento:

                        pix = pagina.get_pixmap(
                            matrix=pymupdf.Matrix(2, 2),
                            alpha=False
                        )

                        imagen_pagina = Image.frombytes(
                            "RGB",
                            [pix.width, pix.height],
                            pix.samples
                        )

                        imagen_pagina_procesada = imagen_pagina.convert(
                            "L"
                        )
                        imagen_pagina_procesada = ImageEnhance.Contrast(
                            imagen_pagina_procesada
                        ).enhance(2.0)
                        imagen_pagina_procesada = imagen_pagina_procesada.filter(
                            ImageFilter.SHARPEN
                        )

                        texto_psm6 = pytesseract.image_to_string(
                            imagen_pagina_procesada,
                            lang="spa+eng",
                            config="--psm 6"
                        )

                        texto_psm11 = pytesseract.image_to_string(
                            imagen_pagina_procesada,
                            lang="spa+eng",
                            config="--psm 11"
                        )

                        textos_psm6.append(texto_psm6)
                        textos_psm11.append(texto_psm11)

                    texto_para_extraer_6 = "\n".join(textos_psm6)
                    texto_para_extraer_11 = "\n".join(textos_psm11)

                    print()
                    print("====================================")
                    print("TEXTO PDF / PSM 6")
                    print("====================================")
                    print(texto_para_extraer_6)

                    print()
                    print("====================================")
                    print("TEXTO PDF / PSM 11")
                    print("====================================")
                    print(texto_para_extraer_11)

            finally:
                documento.close()

            ruta_resultado_pdf = os.path.join(
                COMPROBANTES_PATH,
                "resultado_pdf.txt"
            )

            with open(
                ruta_resultado_pdf,
                "w",
                encoding="utf-8"
            ) as archivo_pdf:
                archivo_pdf.write(
                    "====================================\n"
                    "TEXTO PDF / PSM 6\n"
                    "====================================\n\n"
                    f"{texto_para_extraer_6}\n\n"
                    "====================================\n"
                    "TEXTO PDF / PSM 11\n"
                    "====================================\n\n"
                    f"{texto_para_extraer_11}\n"
                )

            print()
            print(">>> INICIANDO EXTRACTOR PARA PDF <<<")

            datos_extraidos = extraer_datos_transferencia(
                texto_para_extraer_6,
                texto_para_extraer_11
            )

            print()
            print("====================================")
            print("DATOS EXTRAÍDOS DEL PDF")
            print("====================================")
            print("Monto:", datos_extraidos["monto"])
            print("Destinatario:", datos_extraidos["destinatario"])
            print("Cuenta destino:", datos_extraidos["cuenta_destino"])
            print("Cuenta origen:", datos_extraidos["cuenta_origen"])
            print("Comisión:", datos_extraidos["comision"])
            print("Concepto:", datos_extraidos["concepto"])
            print("Tipo operación:", datos_extraidos["tipo_operacion"])
            print("Folio:", datos_extraidos["folio"])
            print("Fecha:", datos_extraidos["fecha"])
            print("Hora:", datos_extraidos["hora"])

        except Exception as error:
            print()
            if procesando_pdf:
                print("ERROR PROCESANDO PDF:")
            else:
                print("ERROR DESCARGANDO PDF:")
            print(error)

        input("Presiona ENTER para cerrar...")
        raise SystemExit

    # ========================================================
    # ABRIR IMAGEN
    # ========================================================

    print()
    print("Abriendo imagen...")

    imagen_thumb.click()

    page.wait_for_timeout(3000)

    print("Imagen abierta.")

    # ========================================================
    # BUSCAR BLOB
    # ========================================================

    imagenes_blob = page.locator(
        'img[src^="blob:"]'
    )

    print()
    print(
        "Imágenes BLOB encontradas:",
        imagenes_blob.count()
    )

    mejor_imagen = None
    mejor_area = 0

    for i in range(imagenes_blob.count()):

        img = imagenes_blob.nth(i)

        try:

            informacion = img.evaluate(
                """
                img => ({
                    src: img.src,
                    naturalWidth: img.naturalWidth,
                    naturalHeight: img.naturalHeight,
                    width: img.width,
                    height: img.height
                })
                """
            )

            natural_width = informacion["naturalWidth"]
            natural_height = informacion["naturalHeight"]

            area = natural_width * natural_height

            print()
            print(
                f"BLOB {i}: "
                f"{natural_width}x{natural_height}"
            )

            if area > mejor_area:
                mejor_area = area
                mejor_imagen = img

        except Exception as error:

            print(
                "Error inspeccionando imagen:",
                error
            )

    if mejor_imagen is None:

        print()
        print("No encontramos una imagen BLOB válida.")

        input("Presiona ENTER para cerrar...")

        raise SystemExit

    # ========================================================
    # EXTRAER IMAGEN ORIGINAL
    # ========================================================

    print()
    print("====================================")
    print("EXTRAYENDO IMAGEN ORIGINAL")
    print("====================================")

    try:

        base64_imagen = mejor_imagen.evaluate(
            """
            async img => {

                const response = await fetch(img.src);

                const blob = await response.blob();

                return await new Promise(
                    (resolve, reject) => {

                        const reader = new FileReader();

                        reader.onloadend = () => {
                            resolve(
                                reader.result.split(',')[1]
                            );
                        };

                        reader.onerror = reject;

                        reader.readAsDataURL(blob);
                    }
                );
            }
            """
        )

        datos_imagen = base64.b64decode(
            base64_imagen
        )

        ruta_original = os.path.join(
            COMPROBANTES_PATH,
            "comprobante_original.jpg"
        )

        with open(ruta_original, "wb") as archivo:
            archivo.write(datos_imagen)

        print(
            "Imagen original guardada:"
        )

        print(ruta_original)

    except Exception as error:

        print()
        print("ERROR EXTRAYENDO BLOB:")
        print(error)

        input("Presiona ENTER para cerrar...")
        raise SystemExit

    # ========================================================
    # ABRIR IMAGEN
    # ========================================================

    imagen = Image.open(
        ruta_original
    )

    print()
    print("====================================")
    print("RESOLUCIÓN ORIGINAL")
    print("====================================")

    print(imagen.size)

    if imagen.mode != "RGB":
        imagen = imagen.convert("RGB")

    # ========================================================
    # OCR 1 - ORIGINAL
    # ========================================================

    print()
    print("====================================")
    print("OCR 1 - IMAGEN ORIGINAL")
    print("====================================")

    texto_original = pytesseract.image_to_string(
        imagen,
        lang="spa+eng",
        config="--psm 6"
    )

    print()
    print(texto_original)

    # ========================================================
    # PREPROCESAR
    # ========================================================

    print()
    print("====================================")
    print("PREPARANDO IMAGEN PARA OCR")
    print("====================================")

    gris = imagen.convert("L")

    contraste = ImageEnhance.Contrast(
        gris
    )

    procesada = contraste.enhance(
        2.0
    )

    procesada = procesada.filter(
        ImageFilter.SHARPEN
    )

    ancho, alto = procesada.size

    if ancho < 1500:

        factor = 2

        procesada = procesada.resize(
            (
                ancho * factor,
                alto * factor
            ),
            Image.Resampling.LANCZOS
        )

    ruta_procesada = os.path.join(
        COMPROBANTES_PATH,
        "comprobante_procesado.png"
    )

    procesada.save(
        ruta_procesada
    )

    print(
        "Resolución procesada:",
        procesada.size
    )

    print(
        "Imagen procesada:",
        ruta_procesada
    )

    # ========================================================
    # OCR 2 - PSM 6
    # ========================================================

    print()
    print("====================================")
    print("OCR 2 - IMAGEN PROCESADA")
    print("====================================")

    texto_procesado = pytesseract.image_to_string(
        procesada,
        lang="spa+eng",
        config="--psm 6"
    )

    print()
    print(texto_procesado)

    # ========================================================
    # OCR 3 - PSM 11
    # ========================================================

    print()
    print("====================================")
    print("OCR 3 - OTRA SEGMENTACIÓN")
    print("====================================")

    texto_alternativo = pytesseract.image_to_string(
        procesada,
        lang="spa+eng",
        config="--psm 11"
    )

    print()
    print(texto_alternativo)

    # ========================================================
    # EXTRAER DATOS
    # ========================================================

    print()
    print(">>> INICIANDO EXTRACTOR <<<")

    datos_extraidos = extraer_datos_transferencia(
        texto_procesado,
        texto_alternativo
    )

    print()
    print("====================================")
    print("DATOS EXTRAÍDOS DEL COMPROBANTE")
    print("====================================")

    print("Monto:", datos_extraidos["monto"])
    print("Destinatario:", datos_extraidos["destinatario"])
    print("Cuenta destino:", datos_extraidos["cuenta_destino"])
    print("Cuenta origen:", datos_extraidos["cuenta_origen"])
    print("Comisión:", datos_extraidos["comision"])
    print("Concepto:", datos_extraidos["concepto"])
    print("Tipo operación:", datos_extraidos["tipo_operacion"])
    print("Folio:", datos_extraidos["folio"])
    print("Fecha:", datos_extraidos["fecha"])
    print("Hora:", datos_extraidos["hora"])

    # ========================================================
    # GUARDAR RESULTADO OCR
    # ========================================================

    ruta_texto = os.path.join(
        COMPROBANTES_PATH,
        "resultado_ocr.txt"
    )

    with open(
        ruta_texto,
        "w",
        encoding="utf-8"
    ) as archivo:

        archivo.write(
            "====================================\n"
        )

        archivo.write(
            "OCR ORIGINAL\n"
        )

        archivo.write(
            "====================================\n\n"
        )

        archivo.write(
            texto_original
        )

        archivo.write(
            "\n\n====================================\n"
        )

        archivo.write(
            "OCR PROCESADO PSM 6\n"
        )

        archivo.write(
            "====================================\n\n"
        )

        archivo.write(
            texto_procesado
        )

        archivo.write(
            "\n\n====================================\n"
        )

        archivo.write(
            "OCR PROCESADO PSM 11\n"
        )

        archivo.write(
            "====================================\n\n"
        )

        archivo.write(
            texto_alternativo
        )

        archivo.write(
            "\n\n====================================\n"
        )

        archivo.write(
            "DATOS EXTRAÍDOS\n"
        )

        archivo.write(
            "====================================\n\n"
        )

        for clave, valor in datos_extraidos.items():
            archivo.write(
                f"{clave}: {valor}\n"
            )

    print()
    print("====================================")
    print("PRUEBA OCR TERMINADA")
    print("====================================")

    print(
        "Resultados guardados en:"
    )

    print(
        ruta_texto
    )

    input(
        "\nPresiona ENTER para cerrar..."
    )

