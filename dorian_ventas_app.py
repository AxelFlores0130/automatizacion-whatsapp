import queue
import threading
from pathlib import Path
import sys
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox, ttk

from resumen_ventas import app_config
from resumen_ventas.whatsapp_browser import (
    BrowserDependencyError,
    ChromeNotFoundError,
    WhatsAppBrowser,
)
from resumen_ventas.resumen_scheduler import verificar_resumen_programado
from resumen_ventas.settings import INTERVALO_COMPROBACION_SEGUNDOS


COLORS = {
    "background": "#F3F5F6",
    "surface": "#FFFFFF",
    "navy": "#102D78",
    "green": "#A7BF35",
    "green_hover": "#B6CB50",
    "text": "#233044",
    "muted": "#6C7788",
    "border": "#DCE2E8",
    "success": "#28754B",
    "error": "#A33A36",
}

DEFAULT_CONFIG = {
    "host": "localhost",
    "port": "3306",
    "user": "root",
    "password": "root",
    "database_central": "central",
    "database_dorian": "dorian",
}


def resource_path(relative_path):
    bundle_directory = getattr(sys, "_MEIPASS", None)
    base_directory = (
        Path(bundle_directory)
        if bundle_directory is not None
        else Path(__file__).resolve().parent
    )
    return base_directory / "frontend" / "public" / relative_path


def quote_identifier(identifier):
    if not identifier or "\x00" in identifier:
        raise ValueError("El nombre de la base de datos no puede estar vacío.")
    return f"`{identifier.replace('`', '``')}`"


class DorianVentasApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dorian Muebles | Configuración")
        self.root.geometry("760x880")
        self.root.minsize(680, 820)
        self.root.configure(background=COLORS["background"])

        self.values = {
            key: tk.StringVar(value=value)
            for key, value in DEFAULT_CONFIG.items()
        }
        self._logo_image = None
        self._verified_config = None
        self._saved_config = None
        self.whatsapp_browser = WhatsAppBrowser()
        self.whatsapp_page = None
        self._automation_thread = None
        self._automation_stop_event = None
        self._automation_events = queue.Queue()
        self._automation_active = False
        self._automation_poll_id = None
        self._closing = False
        self._configure_styles()
        self._build_interface()
        self._load_saved_config()
        self._watch_configuration_changes()
        self._update_whatsapp_availability()
        self._update_automation_controls()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure(
            "Panel.TFrame",
            background=COLORS["surface"],
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["navy"],
            font=("Segoe UI", 15, "bold"),
        )
        style.configure(
            "Field.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "TEntry",
            padding=(10, 9),
            fieldbackground=COLORS["surface"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.configure(
            "Primary.TButton",
            background=COLORS["green"],
            foreground=COLORS["navy"],
            padding=(18, 10),
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLORS["green_hover"])],
        )
        style.configure(
            "Secondary.TButton",
            background=COLORS["surface"],
            foreground=COLORS["navy"],
            padding=(18, 10),
            bordercolor=COLORS["border"],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#F0F3F7")],
        )

    def _build_interface(self):
        scroll_host = tk.Frame(self.root, bg=COLORS["background"])
        scroll_host.pack(fill="both", expand=True)
        self._scroll_canvas = tk.Canvas(
            scroll_host,
            background=COLORS["background"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            scroll_host,
            orient="vertical",
            command=self._scroll_canvas.yview,
        )
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        shell = ttk.Frame(self._scroll_canvas, padding=(32, 26, 32, 24))
        shell_window = self._scroll_canvas.create_window(
            (0, 0),
            window=shell,
            anchor="nw",
        )
        shell.bind(
            "<Configure>",
            lambda _event: self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all")
            ),
        )
        self._scroll_canvas.bind(
            "<Configure>",
            lambda event: self._scroll_canvas.itemconfigure(
                shell_window,
                width=event.width,
            ),
        )
        self._scroll_canvas.bind_all(
            "<MouseWheel>",
            self._on_mousewheel,
            add="+",
        )
        self._scroll_canvas.bind_all(
            "<Button-4>",
            self._on_mousewheel,
            add="+",
        )
        self._scroll_canvas.bind_all(
            "<Button-5>",
            self._on_mousewheel,
            add="+",
        )

        header = tk.Frame(shell, bg=COLORS["surface"], padx=20, pady=18)
        header.pack(fill="x")
        header.grid_columnconfigure(1, weight=1)

        logo_path = resource_path("dorian-logo.png")
        print(f"Ruta logo: {logo_path.resolve()}")
        print(f"Existe logo: {logo_path.exists()}")
        if logo_path.exists():
            try:
                with Image.open(logo_path) as logo:
                    logo.thumbnail((110, 110), Image.Resampling.LANCZOS)
                    self._logo_image = ImageTk.PhotoImage(logo)
                tk.Label(
                    header,
                    image=self._logo_image,
                    bg=COLORS["surface"],
                    borderwidth=0,
                ).grid(row=0, column=0, padx=(0, 22), sticky="w")
                print("Logo cargado correctamente con Pillow")
            except Exception as error:
                self._logo_image = None
                print(
                    f"Error exacto al cargar logo {logo_path}: {error}",
                    file=sys.stderr,
                )

        title_block = tk.Frame(header, bg=COLORS["surface"])
        title_block.grid(row=0, column=1, sticky="w")
        tk.Label(
            title_block,
            text="Sistema automático de resumen de ventas",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        card = ttk.Frame(shell, style="Panel.TFrame", padding=(24, 22, 24, 22))
        card.pack(fill="x", pady=(24, 0))
        tk.Frame(card, bg=COLORS["green"], height=3).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 20),
        )
        ttk.Label(
            card,
            text="Conexión a base de datos",
            style="Section.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w")

        fields = (
            ("Servidor / Host", "host"),
            ("Puerto", "port"),
            ("Usuario", "user"),
            ("Contraseña", "password"),
            ("Base Central", "database_central"),
            ("Base Dorian", "database_dorian"),
        )
        for index, (label, key) in enumerate(fields):
            row = 2 + (index // 2) * 2
            column = index % 2
            field = ttk.Frame(card, style="Panel.TFrame")
            field.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 16) if column == 0 else (16, 0),
                pady=(22, 0),
            )
            ttk.Label(field, text=label, style="Field.TLabel").pack(
                anchor="w",
                pady=(0, 7),
            )
            entry_options = {"textvariable": self.values[key], "width": 30}
            if key == "password":
                entry_options["show"] = "*"
            ttk.Entry(field, **entry_options).pack(fill="x")

        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        buttons = ttk.Frame(shell)
        buttons.pack(fill="x", pady=(20, 0))
        ttk.Button(
            buttons,
            text="Probar conexión",
            command=self._test_connection,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Guardar configuración",
            command=self._save_config,
            style="Primary.TButton",
        ).pack(side="right")

        self.status = tk.Label(
            shell,
            text="",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.status.pack(fill="x", pady=(16, 0))
        whatsapp_panel = ttk.Frame(
            shell,
            style="Panel.TFrame",
            padding=(20, 16),
        )
        whatsapp_panel.pack(fill="x", pady=(16, 0))
        ttk.Label(
            whatsapp_panel,
            text="WhatsApp",
            style="Section.TLabel",
        ).pack(anchor="w")
        whatsapp_row = ttk.Frame(whatsapp_panel, style="Panel.TFrame")
        whatsapp_row.pack(fill="x", pady=(12, 0))
        self.whatsapp_status = tk.Label(
            whatsapp_row,
            text="Estado: ○ No iniciado",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.whatsapp_status.pack(side="left", fill="x", expand=True)
        self.whatsapp_button = ttk.Button(
            whatsapp_row,
            text="Abrir WhatsApp",
            command=self._open_whatsapp,
            style="Primary.TButton",
            state="disabled",
        )
        self.whatsapp_button.pack(side="right")
        automation_panel = ttk.Frame(
            shell,
            style="Panel.TFrame",
            padding=(20, 16),
        )
        automation_panel.pack(fill="x", pady=(12, 0))
        ttk.Label(
            automation_panel,
            text="Automatización",
            style="Section.TLabel",
        ).pack(anchor="w")
        automation_row = ttk.Frame(automation_panel, style="Panel.TFrame")
        automation_row.pack(fill="x", pady=(12, 0))
        self.automation_status = tk.Label(
            automation_row,
            text="Automatización: ○ Detenida",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.automation_status.pack(side="left", fill="x", expand=True)
        self.stop_automation_button = ttk.Button(
            automation_row,
            text="Detener automatización",
            command=self._stop_automation,
            style="Secondary.TButton",
            state="disabled",
        )
        self.stop_automation_button.pack(side="right", padx=(8, 0))
        self.start_automation_button = ttk.Button(
            automation_row,
            text="Iniciar automatización",
            command=self._start_automation,
            style="Primary.TButton",
            state="disabled",
        )
        self.start_automation_button.pack(side="right")
        tk.Label(
            shell,
            text="La configuración se guarda localmente, separada del entorno de desarrollo.",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", side="bottom", pady=(16, 0))

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            delta = getattr(event, "delta", 0)
            units = -int(delta / 120)
            if units == 0 and delta:
                units = -1 if delta > 0 else 1
        if units:
            self._scroll_canvas.yview_scroll(units, "units")
        return "break"

    def _load_saved_config(self):
        try:
            saved = app_config.load_config()
        except (app_config.ConfigurationError, OSError):
            messagebox.showerror(
                "No se pudo cargar la configuración",
                "El archivo local de configuración no se pudo leer o validar.",
                parent=self.root,
            )
            return
        if saved is None:
            return
        self._saved_config = saved.copy()
        field_mapping = {
            "host": "host",
            "port": "port",
            "user": "user",
            "password": "password",
            "database_central": "central_database",
            "database_dorian": "dorian_database",
        }
        for field, config_field in field_mapping.items():
            self.values[field].set(str(saved[config_field]))

    def _watch_configuration_changes(self):
        for variable in self.values.values():
            variable.trace_add("write", self._configuration_changed)

    def _configuration_changed(self, *_):
        if self._verified_config is not None:
            self._verified_config = None
            self.status.configure(
                text="La configuración cambió; vuelve a probar la conexión.",
                fg=COLORS["error"],
            )
        self._update_whatsapp_availability()
        self._update_automation_controls()

    def _current_values(self):
        return app_config.validate_connection_config(
            {
                "host": self.values["host"].get(),
                "port": self.values["port"].get(),
                "user": self.values["user"].get(),
                "password": self.values["password"].get(),
                "central_database": self.values["database_central"].get(),
                "dorian_database": self.values["database_dorian"].get(),
            }
        )

    def _test_connection(self):
        self._verified_config = None
        try:
            values = self._current_values()
        except ValueError as error:
            messagebox.showwarning("Revisa la configuración", str(error), parent=self.root)
            return

        try:
            import mysql.connector
        except ImportError:
            messagebox.showerror(
                "Conector no disponible",
                "No se encontró mysql-connector-python en este entorno de Python.",
                parent=self.root,
            )
            return

        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=values["host"],
                port=values["port"],
                user=values["user"],
                password=values["password"],
                connection_timeout=5,
            )
            cursor = connection.cursor()
            for key in ("central_database", "dorian_database"):
                cursor.execute(f"USE {quote_identifier(values[key])}")
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except ValueError as error:
            messagebox.showerror("Nombre de base no válido", str(error), parent=self.root)
            return
        except mysql.connector.Error as error:
            messagebox.showerror(
                "No se pudo establecer la conexión",
                self._connection_error_message(error, values),
                parent=self.root,
            )
            return
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                if connection is not None:
                    connection.close()

        self._verified_config = values.copy()
        self._update_whatsapp_availability()
        self._update_automation_controls()
        self.status.configure(
            text="Conexión establecida correctamente",
            fg=COLORS["success"],
        )
        messagebox.showinfo(
            "Conexión verificada",
            "Conexión establecida correctamente\n\n"
            "✓ Servidor MySQL accesible\n"
            "✓ Base central accesible\n"
            "✓ Base dorian accesible\n"
            "✓ SELECT 1 ejecutado y consumido",
            parent=self.root,
        )

    @staticmethod
    def _connection_error_message(error, values):
        errno = getattr(error, "errno", None)
        sqlstate = getattr(error, "sqlstate", None)
        detail = getattr(error, "msg", None) or str(error)
        detail = str(detail)
        password = values.get("password", "")
        if password:
            detail = detail.replace(password, "[oculto]")
        return (
            "No se pudo establecer la conexión.\n\n"
            f"Servidor: {values['host']}\n"
            f"Puerto: {values['port']}\n"
            f"Usuario: {values['user']}\n\n"
            f"Código MySQL: {errno if errno is not None else 'no disponible'}\n"
            f"SQLSTATE: {sqlstate if sqlstate else 'no disponible'}\n\n"
            f"Detalle:\n{detail}"
        )

    def _whatsapp_configuration_ready(self):
        try:
            values = self._current_values()
        except ValueError:
            return False
        return values == self._verified_config or values == self._saved_config

    def _update_whatsapp_availability(self):
        if not hasattr(self, "whatsapp_button"):
            return
        state = "normal" if self._whatsapp_configuration_ready() else "disabled"
        self.whatsapp_button.configure(state=state)

    def _open_whatsapp(self):
        if not self._whatsapp_configuration_ready():
            messagebox.showwarning(
                "Configuración pendiente",
                "Primero prueba y guarda una configuración válida de base de datos.",
                parent=self.root,
            )
            return

        try:
            self.whatsapp_page = self.whatsapp_browser.open_whatsapp()
        except ChromeNotFoundError as error:
            self.whatsapp_page = None
            self.whatsapp_status.configure(text="Estado: ○ No iniciado")
            self._update_automation_controls()
            messagebox.showerror("Google Chrome no encontrado", str(error), parent=self.root)
            return
        except BrowserDependencyError as error:
            self.whatsapp_page = None
            self.whatsapp_status.configure(text="Estado: ○ No iniciado")
            self._update_automation_controls()
            messagebox.showerror("Playwright no disponible", str(error), parent=self.root)
            return
        except Exception as error:
            self.whatsapp_page = None
            state = "Navegador abierto" if self.whatsapp_browser.is_open else "○ No iniciado"
            self.whatsapp_status.configure(text=f"Estado: {state}")
            self._update_automation_controls()
            messagebox.showerror("No se pudo abrir WhatsApp Web", str(error), parent=self.root)
            return

        self.whatsapp_status.configure(text="Estado: ✓ WhatsApp Web abierto")
        self._update_automation_controls()

    def _update_automation_controls(self):
        if not hasattr(self, "start_automation_button"):
            return
        ready = (
            self._whatsapp_configuration_ready()
            and self.whatsapp_page is not None
            and self.whatsapp_browser.has_page
        )
        self.start_automation_button.configure(
            state="normal" if ready and not self._automation_active else "disabled"
        )
        self.stop_automation_button.configure(
            state="normal" if self._automation_active else "disabled"
        )

    def _start_automation(self):
        if self._automation_thread is not None and self._automation_thread.is_alive():
            return
        if not (
            self._whatsapp_configuration_ready()
            and self.whatsapp_page is not None
            and self.whatsapp_browser.has_page
        ):
            messagebox.showwarning(
                "Automatización no disponible",
                "Verifica la configuración y abre WhatsApp Web antes de iniciar.",
                parent=self.root,
            )
            return

        self._automation_stop_event = threading.Event()
        self._automation_thread = threading.Thread(
            target=self._automation_loop,
            args=(self._automation_stop_event,),
            name="DorianVentasScheduler",
            daemon=True,
        )
        self._automation_active = True
        self.automation_status.configure(
            text="Automatización: ✓ Activa",
            fg=COLORS["success"],
        )
        self._update_automation_controls()
        self._automation_thread.start()
        self._schedule_automation_poll()

    def _automation_loop(self, stop_event):
        try:
            while not stop_event.is_set():
                if not self.whatsapp_browser.has_page:
                    self._automation_events.put(("error", "La Page de WhatsApp Web ya no está disponible."))
                    break
                try:
                    self.whatsapp_browser.run_on_browser_thread(
                        verificar_resumen_programado
                    )
                except Exception:
                    self._automation_events.put(
                        ("error", "Ocurrió un error durante la comprobación del resumen.")
                    )
                if stop_event.wait(INTERVALO_COMPROBACION_SEGUNDOS):
                    break
        finally:
            self._automation_events.put(("stopped", None))

    def _schedule_automation_poll(self):
        if self._automation_poll_id is None:
            self._automation_poll_id = self.root.after(
                200,
                self._poll_automation_events,
            )

    def _poll_automation_events(self):
        self._automation_poll_id = None
        while True:
            try:
                event, detail = self._automation_events.get_nowait()
            except queue.Empty:
                break
            if event == "error":
                self.status.configure(text=detail, fg=COLORS["error"])
            elif event == "stopped":
                self._automation_active = False
                self.automation_status.configure(
                    text="Automatización: ○ Detenida",
                    fg=COLORS["muted"],
                )
                self._update_automation_controls()
                if self._closing:
                    self._finish_close()
                    return

        if self._automation_active:
            self._schedule_automation_poll()

    def _stop_automation(self):
        if not self._automation_active or self._automation_stop_event is None:
            return
        self._automation_stop_event.set()
        self.automation_status.configure(
            text="Automatización: Deteniendo...",
            fg=COLORS["muted"],
        )
        self._update_automation_controls()
        self._schedule_automation_poll()

    def _close_window(self):
        if self._closing:
            return
        self._closing = True
        if self._automation_active:
            self._stop_automation()
            return
        self._finish_close()

    def _finish_close(self):
        if (
            self._automation_thread is not None
            and self._automation_thread.is_alive()
        ):
            self.root.after(100, self._finish_close)
            return
        try:
            self.whatsapp_browser.close()
        except Exception:
            self._closing = False
            messagebox.showerror(
                "No se pudo cerrar el navegador",
                "Chrome/Playwright no terminó de cerrarse. Intenta cerrar la aplicación nuevamente.",
                parent=self.root,
            )
            return
        self.root.destroy()

    def _save_config(self):
        try:
            values = self._current_values()
        except ValueError as error:
            messagebox.showwarning("Revisa la configuración", str(error), parent=self.root)
            return
        if self._verified_config != values:
            messagebox.showwarning(
                "Conexión no verificada",
                "Prueba la conexión con los valores actuales antes de guardar.",
                parent=self.root,
            )
            return
        try:
            app_config.save_config(values)
        except OSError:
            messagebox.showerror(
                "No se pudo guardar",
                "No fue posible guardar el archivo de configuración local.",
                parent=self.root,
            )
            return

        self._saved_config = values.copy()
        self._update_whatsapp_availability()
        self._update_automation_controls()
        self.status.configure(
            text="Configuración guardada correctamente",
            fg=COLORS["success"],
        )
        messagebox.showinfo(
            "Configuración guardada",
            "Configuración guardada correctamente",
            parent=self.root,
        )


def main():
    root = tk.Tk()
    DorianVentasApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()