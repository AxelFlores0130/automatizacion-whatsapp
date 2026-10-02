import re
import time
import math

_HORA_WHATSAPP = re.compile(
    r"(?:0?[1-9]|1[0-2]):[0-5]\d(?:\s*(?:a\.\s*m\.|p\.\s*m\.|am|pm))?"
    r"|(?:[01]?\d|2[0-3]):[0-5]\d",
    re.IGNORECASE,
)


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


def _buscar_filas_exactas(lista_chats, chat_destino):
    titulos = lista_chats.locator('[data-testid="cell-frame-title"]')
    filas = []
    identificadores = set()
    for indice in range(titulos.count()):
        titulo = titulos.nth(indice)
        if not _es_visible(titulo):
            continue

        nombre_exacto = titulo.locator(
            f'span[title="{chat_destino}"]'
        ).count() > 0
        if not nombre_exacto:
            texto = re.sub(r"\s+", " ", titulo.inner_text(timeout=1000)).strip()
            nombre_exacto = texto == chat_destino
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


def _canonicalizar_texto_whatsapp(texto):
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(
        r"(?<!\S)([*_~])(?=\S)([^\n]*?\S)\1(?=$|[\s.,!?;:])",
        r"\2",
        texto,
        flags=re.MULTILINE,
    )
    emojis_iniciales = re.compile(r"^(?:📊|📅|🕐|💵|💳|📦|🧾|💰|🏬)\ufe0f?\s*")
    lineas = []
    for linea in texto.split("\n"):
        linea = re.sub(r"\s+", " ", linea).strip()
        linea = emojis_iniciales.sub("", linea)
        if linea:
            lineas.append(linea)
    return tuple(lineas)


def _textos_equivalentes(texto_esperado, texto_renderizado):
    if texto_renderizado == texto_esperado:
        return True
    if len(texto_renderizado) != len(texto_esperado) + 1:
        return False
    return (
        _HORA_WHATSAPP.fullmatch(texto_renderizado[-1]) is not None
        and texto_renderizado[:-1] == texto_esperado
    )


def _expandir_leer_mas_si_es_necesario(
    candidato,
    contenedor,
    identificador,
    texto_esperado,
    texto_renderizado,
    page,
    expansiones_intentadas,
):
    if _textos_equivalentes(texto_esperado, texto_renderizado):
        return texto_renderizado, True
    if not any("Leer más" in linea for linea in texto_renderizado):
        return texto_renderizado, False

    if identificador in expansiones_intentadas:
        return texto_renderizado, False
    expansiones_intentadas.add(identificador)

    try:
        controles = candidato.get_by_text("Leer más", exact=True)
        if controles.count() != 1:
            return texto_renderizado, False
        control = controles.nth(0)
        if not control.is_visible():
            return texto_renderizado, False
        control.click(timeout=1000)
    except Exception:
        return texto_renderizado, False

    page.wait_for_timeout(200)
    try:
        texto_expandido = _canonicalizar_texto_whatsapp(
            contenedor.inner_text(timeout=1000)
        )
    except Exception:
        return (), False

    return texto_expandido, (
        bool(texto_esperado)
        and _textos_equivalentes(texto_esperado, texto_expandido)
    )


def _alineacion_derecha_segura(rect_contenedor, rect_panel):
    if not isinstance(rect_contenedor, dict) or not isinstance(rect_panel, dict):
        return False

    def valores_rectangulo(rectangulo):
        valores = tuple(rectangulo.get(nombre) for nombre in ("left", "right", "width"))
        if any(
            isinstance(valor, bool)
            or not isinstance(valor, (int, float))
            or not math.isfinite(valor)
            for valor in valores
        ):
            return None
        left, right, width = valores
        if width <= 0 or right <= left:
            return None
        if not math.isclose(width, right - left, abs_tol=1, rel_tol=0):
            return None
        return left, right, width

    contenedor = valores_rectangulo(rect_contenedor)
    panel = valores_rectangulo(rect_panel)
    if contenedor is None or panel is None:
        return False

    contenedor_left, contenedor_right, _ = contenedor
    panel_left, panel_right, _ = panel
    if contenedor_left < panel_left or contenedor_right > panel_right:
        return False

    distancia_izquierda = contenedor_left - panel_left
    distancia_derecha = panel_right - contenedor_right
    return (
        distancia_derecha < distancia_izquierda
        and distancia_izquierda - distancia_derecha > 8
    )


def _determinar_direccion_saliente(
    tail_out,
    rect_contenedor=None,
    rect_panel=None,
):
    if tail_out:
        return True
    return _alineacion_derecha_segura(rect_contenedor, rect_panel)


def _es_saliente(candidato, page):
    tail_out = candidato.locator('[data-testid="tail-out"]').count() > 0
    if tail_out:
        return _determinar_direccion_saliente(tail_out)

    contenedor = candidato.locator('[data-testid="msg-container"]')
    panel = page.locator('[data-testid="conversation-panel-messages"]')
    if contenedor.count() == 0 or panel.count() == 0:
        return False
    try:
        rect_contenedor = contenedor.evaluate(
            """elemento => {
                const rect = elemento.getBoundingClientRect();
                return {left: rect.left, right: rect.right, width: rect.width};
            }"""
        )
        rect_panel = panel.evaluate(
            """elemento => {
                const rect = elemento.getBoundingClientRect();
                return {left: rect.left, right: rect.right, width: rect.width};
            }"""
        )
    except Exception:
        return False
    return _determinar_direccion_saliente(
        False,
        rect_contenedor,
        rect_panel,
    )


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


def _hay_nuevo_saliente(
    page,
    ids_antes,
    mensaje,
    editor,
    expansiones_intentadas,
):
    mensajes = page.locator(
        '[data-testid="conversation-panel-messages"] '
        '[data-testid^="conv-msg-"]'
    )
    texto_esperado = _canonicalizar_texto_whatsapp(mensaje)
    cantidad_mensajes = mensajes.count()

    for indice in range(cantidad_mensajes):
        candidato = mensajes.nth(indice)
        visible = candidato.is_visible()
        identificador = candidato.get_attribute("data-testid", timeout=1000)
        if not identificador or identificador in ids_antes:
            continue

        if not visible:
            continue
        if not _es_saliente(candidato, page):
            continue

        contenedor = candidato.locator('[data-testid="msg-container"]')
        tiene_contenedor = contenedor.count() > 0
        if not tiene_contenedor:
            contenedor = candidato
        contenedor_visible = contenedor.is_visible()
        if not contenedor_visible:
            continue

        texto_renderizado = _canonicalizar_texto_whatsapp(
            contenedor.inner_text(timeout=1000)
        )
        texto_equivalente = bool(texto_esperado) and _textos_equivalentes(
            texto_esperado,
            texto_renderizado,
        )
        if not texto_equivalente:
            texto_renderizado, texto_equivalente = (
                _expandir_leer_mas_si_es_necesario(
                    candidato,
                    contenedor,
                    identificador,
                    texto_esperado,
                    texto_renderizado,
                    page,
                    expansiones_intentadas,
                )
            )
        editor_vacio = not editor.inner_text(timeout=1000).strip()
        if texto_equivalente and editor_vacio:
            print(
                "[VENTAS] Envío confirmado por nuevo mensaje saliente, "
                "contenido completo y editor vacío"
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


def enviar_resumen_whatsapp(page, mensaje, chat_destino):
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
        campo_busqueda.fill(chat_destino)

        limite = time.monotonic() + 15
        filas = []
        while time.monotonic() < limite:
            filas = _buscar_filas_exactas(lista_chats, chat_destino)
            if filas:
                page.wait_for_timeout(400)
                filas = _buscar_filas_exactas(lista_chats, chat_destino)
                break
            page.wait_for_timeout(250)

        if len(filas) != 1:
            raise RuntimeError(
                "No se encontró un único chat exacto llamado "
                f"'{chat_destino}'."
            )
        filas = _buscar_filas_exactas(lista_chats, chat_destino)
        if len(filas) != 1:
            raise RuntimeError(
                "El chat dejó de ser único antes de abrir "
                f"'{chat_destino}'."
            )
        print(f"[VENTAS] Abriendo chat: {chat_destino}")
        filas[0].click(timeout=5000)
        titulos_chat = page.locator("header").get_by_text(
            chat_destino,
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
            chat_destino,
            exact=True,
        )
        if not any(
            titulos_chat.nth(indice).is_visible()
            for indice in range(titulos_chat.count())
        ):
            raise RuntimeError("El chat abierto dejó de coincidir con el destino.")

        ids_mensajes_antes = _ids_mensajes_visibles(page)
        click_intentado = True
        boton.click(timeout=3000)
        page.wait_for_timeout(2000)
        limite = time.monotonic() + 12
        expansiones_intentadas = set()
        while time.monotonic() < limite:
            if _hay_nuevo_saliente(
                page,
                ids_mensajes_antes,
                mensaje,
                editor,
                expansiones_intentadas,
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
