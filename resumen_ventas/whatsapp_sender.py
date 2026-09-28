import re
import time

from .settings import CHAT_DESTINO


def _es_visible(elemento):
    return elemento.is_visible()


def _encontrar_visible(page, locators, timeout=10):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        for locator in locators:
            for indice in range(locator.count()):
                candidato = locator.nth(indice)
                if _es_visible(candidato):
                    return candidato
        page.wait_for_timeout(200)
    raise RuntimeError("No se encontró el control visible requerido en WhatsApp Web.")


def _buscar_filas_exactas(lista_chats):
    titulos = lista_chats.locator('[data-testid="cell-frame-title"]')
    filas = []
    identificadores = set()
    for indice in range(titulos.count()):
        titulo = titulos.nth(indice)
        if not _es_visible(titulo):
            continue

        nombre_exacto = titulo.locator(
            f'span[title="{CHAT_DESTINO}"]'
        ).count() > 0
        if not nombre_exacto:
            texto = re.sub(r"\s+", " ", titulo.inner_text(timeout=1000)).strip()
            nombre_exacto = texto == CHAT_DESTINO
        if not nombre_exacto:
            continue

        fila = titulo.locator(
            "xpath=ancestor::*[@data-testid and "
            "(starts-with(@data-testid, 'list-item-') or "
            "@data-testid='cell-frame-container')][1]"
        )
        if fila.count() == 0 or not _es_visible(fila):
            continue

        seccion = fila.locator(
            "xpath=preceding::*[normalize-space(.)='Chats' or "
            "normalize-space(.)='Mensajes' or "
            "normalize-space(.)='Messages'][1]"
        )
        if seccion.count() == 0:
            continue
        en_lista_chats = seccion.locator(
            "xpath=ancestor-or-self::*[@data-testid='chat-list']"
        ).count() > 0
        if not en_lista_chats:
            continue
        if seccion.inner_text(timeout=1000).strip().casefold() != "chats":
            continue

        identificador = fila.get_attribute("data-testid", timeout=1000)
        if identificador not in identificadores:
            identificadores.add(identificador)
            filas.append(fila)
    return filas


def _ids_mensajes_visibles(page):
    mensajes = page.locator(
        '[data-testid="conversation-panel-messages"] '
        '[data-testid^="conv-msg-"]'
    )
    ids_visibles = set()
    for indice in range(mensajes.count()):
        mensaje = mensajes.nth(indice)
        if not mensaje.is_visible():
            continue
        identificador = mensaje.get_attribute("data-testid", timeout=1000)
        if identificador:
            ids_visibles.add(identificador)
    return ids_visibles


def _capturar_mensajes_con_id_dom(page):
    conversacion = page.locator(
        '[data-testid="conversation-panel-messages"]'
    )
    mensajes = conversacion.locator('[data-testid^="conv-msg-"]')
    encontrados = {}
    for indice in range(mensajes.count()):
        mensaje = mensajes.nth(indice)
        try:
            if not mensaje.is_visible():
                continue
            identificador = mensaje.get_attribute("data-testid", timeout=500)
            if identificador:
                encontrados[identificador] = mensaje
        except Exception:
            continue
    return encontrados


def _texto_normalizado(elemento):
    try:
        return re.sub(r"\s+", " ", elemento.inner_text(timeout=500)).strip()
    except Exception:
        return ""


def _diagnosticar_post_envio(
    page,
    editor,
    ids_antes,
    ids_reportados,
    firma_anterior,
    editor_vacio_anterior,
):
    mensajes_actuales = _capturar_mensajes_con_id_dom(page)
    ids_actuales = set(mensajes_actuales)
    ids_nuevos = ids_actuales - ids_antes
    firma = (tuple(sorted(ids_actuales)), tuple(sorted(ids_nuevos)))

    if firma != firma_anterior:
        pass

    for identificador in sorted(ids_nuevos - ids_reportados):
        mensaje = mensajes_actuales[identificador]
        try:
            visible = mensaje.is_visible()
            tail_out = mensaje.locator('[data-testid="tail-out"]').count() > 0
            contenedor = mensaje.locator('[data-testid="msg-container"]')
            tiene_msg_container = contenedor.count() > 0
            tail_out_en_contenedor = (
                tiene_msg_container
                and contenedor.locator('[data-testid="tail-out"]').count() > 0
            )
            data_testids = mensaje.locator("[data-testid]")
            valores_data_testid = []
            for indice in range(data_testids.count()):
                valor = data_testids.nth(indice).get_attribute(
                    "data-testid",
                    timeout=500,
                )
                if valor:
                    valores_data_testid.append(valor)
            if not tiene_msg_container:
                contenedor = mensaje
            texto = _texto_normalizado(contenedor)
        except Exception:
            visible = False
            tail_out = False
            tiene_msg_container = False
            tail_out_en_contenedor = False
            valores_data_testid = []
            texto = ""
        ids_reportados.add(identificador)

    try:
        editor_vacio = not editor.inner_text(timeout=500).strip()
    except Exception:
        editor_vacio = False
    if editor_vacio != editor_vacio_anterior:
        pass
    return firma, editor_vacio


def _campo_busqueda_vacio(campo_busqueda):
    if not campo_busqueda.is_visible():
        return True
    try:
        valor = campo_busqueda.input_value(timeout=500)
    except Exception:
        valor = campo_busqueda.inner_text(timeout=500)
    return not valor.strip()


def _hay_resultados_mensajes(lista_chats):
    for encabezado in ("Mensajes", "Messages"):
        resultados = lista_chats.get_by_text(encabezado, exact=True)
        for indice in range(resultados.count()):
            if resultados.nth(indice).is_visible():
                return True
    return False


def _lista_normal_visible(lista_chats):
    if not lista_chats.is_visible():
        return False
    filas = lista_chats.locator(
        '[data-testid^="list-item-"], '
        '[data-testid="cell-frame-container"]'
    )
    return any(
        filas.nth(indice).is_visible()
        for indice in range(filas.count())
    )


def _restaurar_busqueda(page, campo_busqueda, lista_chats):
    if campo_busqueda is not None:
        try:
            if campo_busqueda.is_visible():
                campo_busqueda.fill("")
                campo_busqueda.press("Escape", timeout=1000)
        except Exception:
            pass

    try:
        cierres_busqueda = page.get_by_role(
            "button",
            name=re.compile(r"cerrar búsqueda|close search", re.IGNORECASE),
        )
        cierres_visibles = [
            cierres_busqueda.nth(indice)
            for indice in range(cierres_busqueda.count())
            if cierres_busqueda.nth(indice).is_visible()
        ]
        if len(cierres_visibles) == 1:
            cierres_visibles[0].click(timeout=1000)
    except Exception:
        pass

    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        buscador_limpio = (
            campo_busqueda is None
            or _campo_busqueda_vacio(campo_busqueda)
        )
        resultados_cerrados = not _hay_resultados_mensajes(lista_chats)
        if (
            buscador_limpio
            and resultados_cerrados
            and _lista_normal_visible(lista_chats)
        ):
            return True
        page.wait_for_timeout(200)
    return False


def _hay_nuevo_saliente(page, ids_antes, mensaje, editor):
    mensajes = page.locator(
        '[data-testid="conversation-panel-messages"] '
        '[data-testid^="conv-msg-"]'
    )
    lineas = [
        re.sub(r"\s+", " ", linea).strip()
        for linea in mensaje.splitlines()
        if linea.strip()
    ]

    for indice in range(mensajes.count()):
        candidato = mensajes.nth(indice)
        if not candidato.is_visible():
            continue

        identificador = candidato.get_attribute("data-testid", timeout=1000)
        if not identificador or identificador in ids_antes:
            continue

        contenedor = candidato.locator('[data-testid="msg-container"]')
        if contenedor.count() == 0:
            contenedor = candidato
        if not contenedor.is_visible():
            continue

        texto = re.sub(r"\s+", " ", contenedor.inner_text(timeout=1000)).strip()
        texto_esperado = all(linea in texto for linea in lineas)
        editor_vacio = not editor.inner_text(timeout=1000).strip()
        if texto_esperado and editor_vacio:
            print(
                "[VENTAS] Envío confirmado por nuevo conv-msg "
                "y contenido esperado"
            )
            return True
    return False


def _identificar_boton_enviar(footer):
    controles = footer.locator('button, [role="button"]')
    candidatos = []
    patron_envio = re.compile(r"send|enviar", re.IGNORECASE)

    for indice in range(controles.count()):
        control = controles.nth(indice)
        if not control.is_visible() or not control.is_enabled():
            continue
        if control.get_attribute("aria-disabled") == "true":
            continue

        atributos = (
            ("aria-label", control.get_attribute("aria-label")),
            ("data-testid", control.get_attribute("data-testid")),
            ("title", control.get_attribute("title")),
        )
        evidencia = next(
            (
                (nombre, valor)
                for nombre, valor in atributos
                if valor and patron_envio.search(valor)
            ),
            None,
        )

        if evidencia is None:
            iconos = control.locator("[data-testid], [data-icon]")
            for icono_indice in range(iconos.count()):
                icono = iconos.nth(icono_indice)
                for nombre in ("data-testid", "data-icon"):
                    valor = icono.get_attribute(nombre)
                    if valor and patron_envio.search(valor):
                        evidencia = (nombre, valor)
                        break
                if evidencia is not None:
                    break

        if evidencia is not None:
            candidatos.append((control, evidencia[0], evidencia[1]))

    if len(candidatos) != 1:
        return None
    return candidatos[0]


def enviar_resumen_whatsapp(page, mensaje):
    campo_busqueda = None
    lista_chats = page.locator('[data-testid="chat-list"]')
    click_intentado = False
    try:
        campo_busqueda = _encontrar_visible(
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
                page.locator('[contenteditable="true"][data-tab="3"]'),
                page.locator('[contenteditable="true"]'),
            ),
        )
        campo_busqueda.fill("")
        campo_busqueda.fill(CHAT_DESTINO)

        limite = time.monotonic() + 15
        filas = []
        while time.monotonic() < limite:
            filas = _buscar_filas_exactas(lista_chats)
            if filas:
                page.wait_for_timeout(400)
                filas = _buscar_filas_exactas(lista_chats)
                break
            page.wait_for_timeout(250)

        if len(filas) != 1:
            raise RuntimeError(
                "No se encontró un único chat exacto llamado "
                f"'{CHAT_DESTINO}'."
            )
        print(f"[VENTAS] Abriendo chat: {CHAT_DESTINO}")
        filas[0].click(timeout=2000)
        titulos_chat = page.locator("header").get_by_text(
            CHAT_DESTINO,
            exact=True,
        )
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            if any(
                titulos_chat.nth(indice).is_visible()
                for indice in range(titulos_chat.count())
            ):
                break
            page.wait_for_timeout(200)
        else:
            raise RuntimeError("No se verificó el encabezado del chat destino.")

        panel = page.locator('[data-testid="conversation-panel-messages"]')
        panel.wait_for(state="visible", timeout=10000)
        editor = _encontrar_visible(
            page,
            (
                page.locator('footer [contenteditable="true"][data-tab]'),
                page.locator('footer [contenteditable="true"]'),
                page.locator('[contenteditable="true"][role="textbox"]'),
            ),
        )
        if not editor.is_editable():
            raise RuntimeError("El editor de mensajes no está editable.")

        editor.click(timeout=2000)
        editor.focus(timeout=2000)
        if page.locator('[contenteditable="true"]:focus').count() != 1:
            raise RuntimeError("No se pudo enfocar el editor de mensajes.")

        editor.fill(mensaje, timeout=5000)
        contenido = editor.inner_text(timeout=3000)
        normalizar = lambda texto: [
            linea.strip()
            for linea in texto.replace("\r", "").split("\n")
            if linea.strip()
        ]
        if normalizar(contenido) != normalizar(mensaje):
            raise RuntimeError("El mensaje no quedó completo en el editor.")

        boton = _identificar_boton_enviar(page.locator("footer"))
        if boton is None:
            raise RuntimeError(
                "No se pudo identificar de forma segura el botón Enviar."
            )
        boton, atributo, valor = boton
        print(f"[VENTAS] Botón Enviar identificado por {atributo}: {valor}")
        if not boton.is_enabled():
            raise RuntimeError("El botón Enviar no está habilitado.")

        titulos_chat = page.locator("header").get_by_text(
            CHAT_DESTINO,
            exact=True,
        )
        if not any(
            titulos_chat.nth(indice).is_visible()
            for indice in range(titulos_chat.count())
        ):
            raise RuntimeError("El chat abierto dejó de coincidir con el destino.")

        ids_mensajes_antes = _ids_mensajes_visibles(page)
        ids_dom_antes = set(_capturar_mensajes_con_id_dom(page))
        click_intentado = True
        boton.click(timeout=3000)
        page.wait_for_timeout(2000)
        limite = time.monotonic() + 12
        ids_reportados = set()
        firma_anterior = None
        editor_vacio_anterior = None
        while time.monotonic() < limite:
            firma_anterior, editor_vacio_anterior = _diagnosticar_post_envio(
                page,
                editor,
                ids_dom_antes,
                ids_reportados,
                firma_anterior,
                editor_vacio_anterior,
            )
            if _hay_nuevo_saliente(
                page,
                ids_mensajes_antes,
                mensaje,
                editor,
            ):
                return True
            page.wait_for_timeout(300)
        return None
    except Exception:
        if click_intentado:
            print(
                "[VENTAS] Click realizado; confirmación ambigua, "
                "se evita un segundo envío"
            )
            return None
        raise
    finally:
        try:
            if not _restaurar_busqueda(page, campo_busqueda, lista_chats):
                print(
                    "[VENTAS] No se confirmó el restablecimiento de la "
                    "lista normal de chats"
                )
        except Exception as error:
            print(f"[VENTAS] No se pudo restaurar la lista de chats: {error}")
