import os
import re
import time
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


CHAT_DESTINO = "Trabajos"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = PROJECT_ROOT / "chrome_profile"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
load_dotenv(PROJECT_ROOT / ".env")


def obtener_resumen():
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
        mensaje = "\n".join(
            (
                "RESUMEN DE VENTAS",
                f"Fecha: {fecha:%d/%m/%Y}",
                f"Ventas realizadas: {cantidad_ventas}",
                f"Total vendido: ${total_vendido:,.2f}",
            )
        )
        return mensaje
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def verificar_chat_abierto(page):
    titulo_chat = page.locator("header").get_by_text(
        CHAT_DESTINO,
        exact=True,
    )
    titulo_chat.wait_for(state="visible", timeout=15000)
    return any(
        titulo_chat.nth(indice).is_visible()
        for indice in range(titulo_chat.count())
    )


def encontrar_locator_visible(page, locators, timeout=15000, filtro=None):
    limite = time.monotonic() + timeout / 1000

    while time.monotonic() < limite:
        for locator in locators:
            for indice in range(locator.count()):
                candidato = locator.nth(indice)
                if not candidato.is_visible():
                    continue
                if filtro is None or candidato.evaluate(filtro):
                    return candidato
        page.wait_for_timeout(250)

    raise PlaywrightTimeoutError(
        "No se encontró un elemento visible con los selectores disponibles."
    )


def encontrar_filas_chat_exactas(lista_chats):
    titulos = lista_chats.locator(
        f'span[title="{CHAT_DESTINO}"]'
    )
    titulos_visibles = [
        titulos.nth(indice)
        for indice in range(titulos.count())
        if titulos.nth(indice).is_visible()
    ]

    if not titulos_visibles:
        titulos = lista_chats.locator('[data-testid="cell-frame-title"]')
        indices_exactos = titulos.evaluate_all(
            """(elementos, nombre) => elementos.flatMap((elemento, indice) => {
                const estilo = getComputedStyle(elemento);
                const caja = elemento.getBoundingClientRect();
                const visible = estilo.visibility !== "hidden"
                    && estilo.display !== "none"
                    && caja.width > 0
                    && caja.height > 0;
                const texto = (elemento.innerText || elemento.textContent || "")
                    .replace(/\\s+/g, " ")
                    .trim();
                return visible && texto === nombre ? [indice] : [];
            })""",
            CHAT_DESTINO,
        )
        titulos_visibles = [titulos.nth(indice) for indice in indices_exactos]

    filas_exactas = []
    for titulo in titulos_visibles:
        fila = titulo.locator(
            "xpath=ancestor::*[@data-testid and "
            "(starts-with(@data-testid, 'list-item-') or "
            "@data-testid='cell-frame-container')][1]"
        )
        if fila.count() == 0:
            fila = titulo.locator(
                "xpath=ancestor::*[@role='listitem' or @role='button'][1]"
            )
        if fila.count() > 0 and fila.is_visible():
            filas_exactas.append(fila)

    return filas_exactas


def normalizar_lineas(texto):
    return [
        linea.strip()
        for linea in texto.replace("\r", "").split("\n")
        if linea.strip()
    ]


def contar_mensajes_salientes(page, mensaje):
    panel = page.locator('[data-testid="conversation-panel-messages"]')
    return panel.evaluate(
        """(panel, objetivo) => {
            const normalizar = texto => (texto || "")
                .replace(/\\s+/g, " ")
                .trim();
            const lineasObjetivo = objetivo.split(/\\r?\\n/)
                .map(normalizar)
                .filter(Boolean);
            const esVisible = elemento => {
                const estilo = getComputedStyle(elemento);
                const caja = elemento.getBoundingClientRect();
                return estilo.display !== "none"
                    && estilo.visibility !== "hidden"
                    && caja.width > 0
                    && caja.height > 0;
            };
            return [...panel.querySelectorAll('[data-testid^="conv-msg-"]')]
                .filter(mensaje => {
                    const contenedor = mensaje.querySelector(
                        '[data-testid="msg-container"]'
                    ) || mensaje;
                    if (!esVisible(mensaje) || !esVisible(contenedor)
                        || !mensaje.querySelector('[data-testid="tail-out"]')) {
                        return false;
                    }
                    const texto = normalizar(contenedor.innerText);
                    return lineasObjetivo.every(linea => texto.includes(linea));
                }).length;
        }""",
        mensaje,
    )


def identificar_boton_enviar(footer):
    controles = footer.locator('button, [role="button"]')
    candidatos = controles.evaluate_all(
        """controles => controles.flatMap((control, indice) => {
            const estilo = getComputedStyle(control);
            const caja = control.getBoundingClientRect();
            const visible = estilo.display !== "none"
                && estilo.visibility !== "hidden"
                && caja.width > 0
                && caja.height > 0;
            const habilitado = !control.matches(':disabled')
                && control.getAttribute('aria-disabled') !== 'true';
            if (!visible || !habilitado) return [];

            const elementos = [control, ...control.querySelectorAll(
                '[data-testid], [data-icon]'
            )];
            const atributos = [
                ['aria-label', control.getAttribute('aria-label')],
                ['data-testid', control.getAttribute('data-testid')],
                ['title', control.getAttribute('title')],
                ...elementos.slice(1).flatMap(elemento => [
                    ['data-testid', elemento.getAttribute('data-testid')],
                    ['data-icon', elemento.getAttribute('data-icon')]
                ])
            ];
            const evidencia = atributos.find(([, valor]) => (
                valor && /send|enviar/i.test(valor)
            ));
            return evidencia
                ? [{indice, atributo: evidencia[0], valor: evidencia[1]}]
                : [];
        })"""
    )
    if len(candidatos) != 1:
        return None, None

    candidato = candidatos[0]
    boton = controles.nth(candidato["indice"])
    if not boton.is_visible() or not boton.is_enabled():
        return None, None
    return boton, (candidato["atributo"], candidato["valor"])


def enviar_resumen(mensaje):
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_PATH),
            executable_path=str(CHROME_PATH),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        try:
            etapa = "abrir WhatsApp Web"
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            page.wait_for_selector('[data-testid="chat-list"]', timeout=60000)
            print("[WHATSAPP] Interfaz cargada")

            etapa = "localizar el buscador de chats"
            print(f"[WHATSAPP] Buscando chat: {CHAT_DESTINO}")
            campo_busqueda = encontrar_locator_visible(
                page,
                (
                    page.get_by_role(
                        "textbox",
                        name=re.compile(r"buscar|search", re.IGNORECASE),
                    ),
                    page.locator(
                        '[contenteditable="true"][aria-label*="Buscar" i], '
                        '[contenteditable="true"][aria-label*="Search" i], '
                        '[role="textbox"][aria-label*="Buscar" i], '
                        '[role="textbox"][aria-label*="Search" i]'
                    ),
                    page.locator(
                        '[contenteditable="true"][data-tab="3"]'
                    ),
                    page.locator('[contenteditable="true"]'),
                ),
                timeout=15000,
                filtro=(
                    'el => !el.closest("footer") && '
                    '!el.closest("[data-testid=\\"conversation-panel-messages\\"]")'
                ),
            )
            campo_busqueda.fill("")
            campo_busqueda.fill(CHAT_DESTINO)

            etapa = "esperar el resultado exacto del chat"
            lista_chats = page.locator('[data-testid="chat-list"]')
            limite = time.monotonic() + 15
            resultados_visibles = []
            while time.monotonic() < limite:
                resultados_visibles = encontrar_filas_chat_exactas(
                    lista_chats
                )
                if resultados_visibles:
                    page.wait_for_timeout(500)
                    resultados_visibles = encontrar_filas_chat_exactas(
                        lista_chats
                    )
                    break
                page.wait_for_timeout(250)

            if not resultados_visibles:
                print(
                    "[WHATSAPP] No se encontró el chat exacto: "
                    f"{CHAT_DESTINO}"
                )
                return
            if len(resultados_visibles) > 1:
                print(
                    "[WHATSAPP] Hay varios resultados exactos visibles: "
                    f"{CHAT_DESTINO}; no se seleccionó ninguno."
                )
                return

            print("[WHATSAPP] Chat encontrado")
            etapa = "abrir el resultado exacto del chat"
            resultados_visibles[0].click(timeout=2000)

            etapa = "verificar el encabezado del chat abierto"
            if not verificar_chat_abierto(page):
                raise RuntimeError(
                    f"El encabezado no corresponde a '{CHAT_DESTINO}'."
                )
            page.wait_for_selector(
                '[data-testid="conversation-panel-messages"]',
                timeout=15000,
            )
            print(
                "[WHATSAPP] Chat abierto y verificado: "
                f"{CHAT_DESTINO}"
            )

            etapa = "localizar el editor del chat"
            filtro_editor = (
                'el => !el.closest("[data-testid=\\"chat-list\\"]") && '
                '!el.closest("header")'
            )
            campo_mensaje = encontrar_locator_visible(
                page,
                (
                    page.locator('footer [contenteditable="true"][data-tab]'),
                    page.locator('footer [contenteditable="true"]'),
                    page.locator(
                        '[contenteditable="true"][data-tab="10"]'
                    ),
                    page.locator(
                        '[contenteditable="true"][data-tab]'
                    ),
                    page.locator(
                        '[contenteditable="true"][role="textbox"]'
                    ),
                    page.get_by_role("textbox"),
                ),
                timeout=15000,
                filtro=filtro_editor,
            )
            print("[WHATSAPP] Editor de mensaje localizado")

            print(f"Chat destino: {CHAT_DESTINO}")
            print("Mensaje:")
            print(mensaje)
            respuesta = input("¿Enviar mensaje? (S/N): ").strip().upper()
            if respuesta != "S":
                print("Envío cancelado; no se envió ningún mensaje.")
                return

            etapa = "escribir y enviar el resumen"
            verificar_chat_abierto(page)
            if not campo_mensaje.is_visible() or not campo_mensaje.is_editable():
                print(
                    "[WHATSAPP] El editor no está visible y editable; "
                    "se canceló la operación."
                )
                return

            campo_mensaje.click(timeout=3000)
            editor_enfocado = campo_mensaje.evaluate(
                "el => document.activeElement === el "
                "|| el.contains(document.activeElement)"
            )
            if not editor_enfocado:
                print(
                    "[WHATSAPP] No se pudo enfocar el editor; "
                    "se canceló la operación."
                )
                return
            print("[WHATSAPP] Editor enfocado")

            mensajes_antes = contar_mensajes_salientes(page, mensaje)
            campo_mensaje.fill(mensaje, timeout=5000)
            texto_editor = campo_mensaje.inner_text(timeout=3000)
            if normalizar_lineas(texto_editor) != normalizar_lineas(mensaje):
                print(
                    "[WHATSAPP] El resumen no se escribió completo en el "
                    "editor; no se intentará enviar."
                )
                return
            print("[WHATSAPP] Mensaje escrito en el editor")

            verificar_chat_abierto(page)
            footer = page.locator("footer")
            boton_enviar, evidencia = identificar_boton_enviar(footer)
            if boton_enviar is None:
                print(
                    "[WHATSAPP] No se pudo identificar de forma segura "
                    "el botón Enviar"
                )
                return

            print(
                "[WHATSAPP] Botón Enviar identificado por "
                f"{evidencia[0]}: {evidencia[1]}"
            )
            verificar_chat_abierto(page)
            boton_enviar.click(timeout=3000)
            print("[WHATSAPP] Click en enviar realizado")

            page.wait_for_timeout(2000)
            limite_verificacion = time.monotonic() + 13
            envio_verificado = False
            editor_vacio = False
            while time.monotonic() < limite_verificacion:
                contenido_editor = campo_mensaje.inner_text(timeout=1000)
                editor_vacio = not contenido_editor.strip()
                mensajes_despues = contar_mensajes_salientes(page, mensaje)
                if editor_vacio and mensajes_despues > mensajes_antes:
                    envio_verificado = True
                    break
                page.wait_for_timeout(300)

            if envio_verificado:
                print("[WHATSAPP] Mensaje enviado y verificado")
            elif editor_vacio:
                print(
                    "[WHATSAPP] El editor se vació, pero no se confirmó "
                    "el mensaje saliente"
                )
            else:
                print(
                    "[WHATSAPP] El mensaje continúa en el editor; "
                    "el envío no se confirmó"
                )
        except Exception as error:
            print(f"[WHATSAPP] Falló en etapa '{etapa}': {error}")
        finally:
            print("[PRUEBA] WhatsApp permanecerá abierto.")
            print(f'[PRUEBA] Revisa visualmente el chat "{CHAT_DESTINO}".')
            input("[PRUEBA] Presiona ENTER para finalizar...")
            context.close()


def main():
    if CHAT_DESTINO == "CAMBIAR_AQUI":
        print("Configura CHAT_DESTINO antes de realizar la prueba.")
        return

    try:
        mensaje = obtener_resumen()
    except Error as error:
        print(f"Error de MySQL: {error}")
        return

    try:
        enviar_resumen(mensaje)
    except PlaywrightTimeoutError as error:
        print(f"No se pudo localizar o verificar el chat: {error}")
    except Exception as error:
        print(f"No fue posible completar la prueba de WhatsApp: {error}")


if __name__ == "__main__":
    main()