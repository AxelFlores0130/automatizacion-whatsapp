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
    "chat_destino": app_config.DEFAULT_CHAT_DESTINO,
}
MYSQL_CONFIG_FIELDS = (
    "host",
    "port",
    "user",
    "password",
    "central_database",
    "dorian_database",
)


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
        self.root.title("Dorian Ventas")
        self.root.geometry("1160x740")
        self.root.minsize(960, 640)
        self.root.configure(background=COLORS["background"])

        self.values = {
            key: tk.StringVar(value=value)
            for key, value in DEFAULT_CONFIG.items()
        }
        self._logo_image = None
        self._schedule_rows = []
        self._schedule_rows_container = None
        self._schedule_summary_label = None
        self._automation_schedule_label = None
        self._verified_config = None
        self._saved_config = None
        self.whatsapp_browser = WhatsAppBrowser()
        self.whatsapp_page = None
        self._automation_thread = None
        self._automation_stop_event = None
        self._automation_events = queue.Queue()
        self._automation_active = False
        self._automation_poll_id = None
        self._startup_thread = None
        self._startup_cancel_event = None
        self._startup_in_progress = False
        self._whatsapp_authenticated = False
        self._closing = False
        self._configure_styles()
        self._build_interface()
        self.root.update_idletasks()
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        screen_x = max(0, (self.root.winfo_screenwidth() - window_width) // 2)
        screen_y = max(0, (self.root.winfo_screenheight() - window_height) // 2)
        self.root.geometry(
            f"{window_width}x{window_height}+{screen_x}+{screen_y}"
        )
        self._load_saved_config()
        self._watch_configuration_changes()
        self._update_whatsapp_availability()
        self._update_automation_controls()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root.after_idle(self._auto_start_saved_configuration)

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
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "Field.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "TEntry",
            padding=(8, 6),
            fieldbackground=COLORS["surface"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.configure(
            "Primary.TButton",
            background=COLORS["green"],
            foreground=COLORS["navy"],
            padding=(14, 7),
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLORS["green_hover"])],
        )
        style.configure(
            "Positive.TButton",
            background=COLORS["surface"],
            foreground=COLORS["success"],
            padding=(14, 7),
            bordercolor=COLORS["green"],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Positive.TButton",
            background=[("active", "#F2F6E4")],
        )
        style.configure(
            "Secondary.TButton",
            background=COLORS["surface"],
            foreground=COLORS["navy"],
            padding=(14, 7),
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
        self._scrollbar = scrollbar
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        shell = ttk.Frame(self._scroll_canvas, padding=(18, 14, 18, 12))
        shell_window = self._scroll_canvas.create_window(
            (0, 0),
            window=shell,
            anchor="nw",
        )

        def update_viewport(_event=None):
            content_height = shell.winfo_reqheight()
            viewport_height = self._scroll_canvas.winfo_height()
            needs_scroll = content_height > viewport_height + 2
            if needs_scroll and not scrollbar.winfo_ismapped():
                scrollbar.pack(side="right", fill="y")
            elif not needs_scroll and scrollbar.winfo_ismapped():
                scrollbar.pack_forget()
            canvas_width = self._scroll_canvas.winfo_width()
            window_height = max(content_height, viewport_height)
            self._scroll_canvas.itemconfigure(
                shell_window,
                width=canvas_width,
                height=window_height,
            )
            self._scroll_canvas.configure(
                scrollregion=(0, 0, canvas_width, window_height)
            )

        shell.bind(
            "<Configure>",
            lambda event: self.root.after_idle(update_viewport, event),
        )
        self._scroll_canvas.bind(
            "<Configure>",
            lambda event: self.root.after_idle(update_viewport, event),
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

        header = tk.Frame(shell, bg=COLORS["surface"], padx=17, pady=8)
        header.pack(fill="x")
        header.grid_columnconfigure(1, weight=1)

        logo_path = resource_path("dorian-logo.png")
        print(f"Ruta logo: {logo_path.resolve()}")
        print(f"Existe logo: {logo_path.exists()}")
        if logo_path.exists():
            try:
                with Image.open(logo_path) as logo:
                    logo.thumbnail((128, 128), Image.Resampling.LANCZOS)
                    self._logo_image = ImageTk.PhotoImage(logo)
                tk.Label(
                    header,
                    image=self._logo_image,
                    bg=COLORS["surface"],
                    borderwidth=0,
                ).grid(row=0, column=0, padx=(0, 14), sticky="w")
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
            text="Dorian Ventas",
            bg=COLORS["surface"],
            fg=COLORS["navy"],
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Sistema automático de resumen de ventas",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(1, 0))
        tk.Label(
            title_block,
            text="Sistema interno · Dorian Muebles",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))
        tk.Frame(
            title_block,
            bg=COLORS["green"],
            height=2,
            width=54,
        ).pack(anchor="w", pady=(6, 0))

        status_strip = tk.Frame(shell, bg=COLORS["surface"], padx=16, pady=10)
        status_strip.pack(fill="x", pady=(9, 11))
        tk.Label(
            status_strip,
            text="ESTADO DEL SISTEMA",
            bg=COLORS["surface"],
            fg=COLORS["navy"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))
        for column in (0, 2, 4):
            status_strip.grid_columnconfigure(
                column,
                weight=1,
                uniform="status",
            )

        def status_cell(column, title, attribute, initial_text):
            cell = tk.Frame(status_strip, bg=COLORS["surface"])
            cell.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0, 10) if column < 2 else (0, 0),
            )
            tk.Label(
                cell,
                text=title.upper(),
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 8, "bold"),
                anchor="w",
            ).pack(anchor="w")
            state = tk.Label(
                cell,
                text=initial_text,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
                wraplength=300,
                justify="left",
            )
            state.pack(anchor="w", fill="x", pady=(2, 0))
            setattr(self, attribute, state)

        status_cell(0, "Base de datos", "status", "○ No verificada")
        tk.Frame(status_strip, bg=COLORS["border"], width=1).grid(
            row=1, column=1, sticky="ns", padx=(0, 10)
        )
        status_cell(2, "WhatsApp", "whatsapp_status", "○ No iniciado")
        tk.Frame(status_strip, bg=COLORS["border"], width=1).grid(
            row=1, column=3, sticky="ns", padx=(0, 10)
        )
        status_cell(4, "Automatización", "automation_status", "○ Detenida")
        self._schedule_summary_label = tk.Label(
            status_strip,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self._schedule_summary_label.grid(
            row=2,
            column=0,
            columnspan=5,
            sticky="w",
            pady=(8, 0),
        )

        main = tk.Frame(shell, bg=COLORS["background"])
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=55, uniform="main")
        main.grid_columnconfigure(1, weight=45, uniform="main")
        main.grid_rowconfigure(0, weight=1)

        connection_panel = ttk.Frame(
            main,
            style="Panel.TFrame",
            padding=(17, 15),
        )
        connection_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        ttk.Label(
            connection_panel,
            text="Conexión a base de datos",
            style="Section.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            connection_panel,
            text="Configuración de acceso al servidor de ventas",
            style="Field.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 1))

        fields = (
            ("Servidor / Host", "host"),
            ("Puerto", "port"),
            ("Usuario", "user"),
            ("Contraseña", "password"),
            ("Base Central", "database_central"),
            ("Base Dorian", "database_dorian"),
        )
        for index, (label, key) in enumerate(fields):
            row = 2 + index // 2
            column = index % 2
            field = ttk.Frame(connection_panel, style="Panel.TFrame")
            field.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 8) if column == 0 else (8, 0),
                pady=(11, 0),
            )
            ttk.Label(field, text=label, style="Field.TLabel").pack(
                anchor="w",
                pady=(0, 5),
            )
            entry_options = {"textvariable": self.values[key], "width": 24}
            if key == "password":
                entry_options["show"] = "*"
            ttk.Entry(field, **entry_options).pack(fill="x")
        for column in (0, 1):
            connection_panel.columnconfigure(column, weight=1, uniform="dbfields")
        ttk.Button(
            connection_panel,
            text="Probar conexión",
            command=self._test_connection,
            style="Secondary.TButton",
        ).grid(row=5, column=0, sticky="w", pady=(14, 0))

        operations_panel = ttk.Frame(
            main,
            style="Panel.TFrame",
            padding=(17, 15),
        )
        operations_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        operations_panel.columnconfigure(0, weight=1)
        ttk.Label(
            operations_panel,
            text="Operación",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            operations_panel,
            text="WHATSAPP",
            style="Field.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(14, 0))
        ttk.Label(
            operations_panel,
            text="Canal de envío de reportes",
            style="Field.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            operations_panel,
            text="Chat o grupo de WhatsApp",
            style="Field.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(8, 5))
        ttk.Entry(
            operations_panel,
            textvariable=self.values["chat_destino"],
        ).grid(row=4, column=0, sticky="ew")

        whatsapp_row = ttk.Frame(operations_panel, style="Panel.TFrame")
        whatsapp_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        whatsapp_row.columnconfigure(0, weight=1)
        self.whatsapp_button = ttk.Button(
            whatsapp_row,
            text="Abrir WhatsApp",
            command=self._open_whatsapp,
            style="Secondary.TButton",
            state="disabled",
        )
        self.whatsapp_button.grid(row=0, column=1, sticky="e")

        ttk.Separator(operations_panel).grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(14, 11),
        )
        ttk.Label(
            operations_panel,
            text="AUTOMATIZACIÓN",
            style="Field.TLabel",
        ).grid(row=7, column=0, sticky="w")
        automation_context = tk.Frame(
            operations_panel,
            bg=COLORS["surface"],
        )
        automation_context.grid(row=8, column=0, sticky="ew", pady=(7, 0))
        automation_context.grid_columnconfigure(0, weight=1)
        automation_context.grid_columnconfigure(1, weight=1)
        tk.Label(
            automation_context,
            text="DESTINO",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            automation_context,
            text="HORARIOS",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        tk.Label(
            automation_context,
            textvariable=self.values["chat_destino"],
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._automation_schedule_label = tk.Label(
            automation_context,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self._automation_schedule_label.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(12, 0),
            pady=(2, 0),
        )

        ttk.Label(
            operations_panel,
            text="HORARIOS DE ENVÍO",
            style="Field.TLabel",
        ).grid(row=9, column=0, sticky="w", pady=(12, 5))
        self._schedule_rows_container = ttk.Frame(
            operations_panel,
            style="Panel.TFrame",
        )
        self._schedule_rows_container.grid(row=10, column=0, sticky="ew")
        self._schedule_rows_container.columnconfigure(0, weight=1)
        for horario in app_config.DEFAULT_HORARIOS_ENVIO:
            hora, minuto = horario.split(":")
            self._add_schedule_row(hora, minuto)
        ttk.Button(
            operations_panel,
            text="+ Agregar horario",
            command=self._add_schedule_row,
            style="Secondary.TButton",
        ).grid(row=11, column=0, sticky="w", pady=(5, 0))

        automation_row = ttk.Frame(operations_panel, style="Panel.TFrame")
        automation_row.grid(row=12, column=0, sticky="ew", pady=(10, 0))
        automation_row.columnconfigure(0, weight=1)
        self.stop_automation_button = ttk.Button(
            automation_row,
            text="Detener automatización",
            command=self._stop_automation,
            style="Secondary.TButton",
            state="disabled",
        )
        self.stop_automation_button.grid(row=0, column=2, padx=(7, 0))
        self.start_automation_button = ttk.Button(
            automation_row,
            text="Iniciar automatización",
            command=self._start_automation,
            style="Positive.TButton",
            state="disabled",
        )
        self.start_automation_button.grid(row=0, column=1)

        actions = ttk.Frame(shell, style="Panel.TFrame", padding=(14, 8))
        actions.pack(fill="x", pady=(10, 0))
        tk.Label(
            actions,
            text="Configuración guardada localmente",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            actions,
            text="Guardar configuración",
            command=self._save_config,
            style="Primary.TButton",
        ).pack(side="right")
        self._refresh_schedule_displays()

    def _add_schedule_row(self, hour=None, minute=None):
        if self._schedule_rows_container is None:
            return
        if hour is None or minute is None:
            occupied = set(self._current_schedule_values())
            start_minute = 0
            if self._schedule_rows:
                last_row = self._schedule_rows[-1]
                start_minute = (
                    int(last_row["hour"].get()) * 60
                    + int(last_row["minute"].get())
                    + 60
                ) % (24 * 60)
            available = next(
                (
                    (
                        candidate_minute // 60,
                        candidate_minute % 60,
                    )
                    for offset in range(24 * 60)
                    for candidate_minute in (
                        (start_minute + offset) % (24 * 60),
                    )
                    if f"{candidate_minute // 60:02d}:"
                    f"{candidate_minute % 60:02d}" not in occupied
                ),
                None,
            )
            if available is None:
                messagebox.showwarning(
                    "No hay más horarios disponibles",
                    "Ya están configurados todos los minutos del día.",
                    parent=self.root,
                )
                return
            hour, minute = available
        hour_var = tk.StringVar(value=f"{int(hour):02d}")
        minute_var = tk.StringVar(value=f"{int(minute):02d}")
        row = {
            "hour": hour_var,
            "minute": minute_var,
            "frame": ttk.Frame(
                self._schedule_rows_container,
                style="Panel.TFrame",
            ),
        }
        row["frame"].columnconfigure(0, weight=0)
        ttk.Spinbox(
            row["frame"],
            values=tuple(f"{value:02d}" for value in range(24)),
            textvariable=hour_var,
            state="readonly",
            wrap=True,
            width=3,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(row["frame"], text=":", style="Field.TLabel").grid(
            row=0,
            column=1,
            padx=3,
        )
        ttk.Spinbox(
            row["frame"],
            values=tuple(f"{value:02d}" for value in range(60)),
            textvariable=minute_var,
            state="readonly",
            wrap=True,
            width=3,
        ).grid(row=0, column=2, sticky="w")
        ttk.Button(
            row["frame"],
            text="Eliminar",
            command=lambda item=row: self._remove_schedule_row(item),
            style="Secondary.TButton",
        ).grid(row=0, column=3, padx=(12, 0))
        hour_var.trace_add("write", self._refresh_schedule_displays)
        minute_var.trace_add("write", self._refresh_schedule_displays)
        self._schedule_rows.append(row)
        self._render_schedule_rows()
        self._refresh_schedule_displays()

    def _remove_schedule_row(self, row):
        if row not in self._schedule_rows:
            return
        row["frame"].destroy()
        self._schedule_rows.remove(row)
        self._render_schedule_rows()
        self._refresh_schedule_displays()

    def _render_schedule_rows(self):
        for index, row in enumerate(self._schedule_rows):
            row["frame"].grid(
                row=index,
                column=0,
                sticky="w",
                pady=(0, 4),
            )

    def _set_schedule_rows(self, horarios):
        for row in self._schedule_rows:
            row["frame"].destroy()
        self._schedule_rows.clear()
        for horario in horarios:
            hora, minuto = horario.split(":")
            self._add_schedule_row(hora, minuto)
        self._refresh_schedule_displays()

    def _current_schedule_values(self):
        return [
            f"{row['hour'].get()}:{row['minute'].get()}"
            for row in self._schedule_rows
        ]

    def _refresh_schedule_displays(self, *_):
        if not self._schedule_rows:
            horarios = "Sin horarios"
        else:
            horarios = " · ".join(self._current_schedule_values())
        if self._schedule_summary_label is not None:
            self._schedule_summary_label.configure(
                text=f"Próximos reportes: {horarios}"
            )
        if self._automation_schedule_label is not None:
            self._automation_schedule_label.configure(text=horarios)

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
            "chat_destino": "chat_destino",
        }
        for field, config_field in field_mapping.items():
            self.values[field].set(str(saved[config_field]))
        self._set_schedule_rows(saved["horarios_envio"])

    def _watch_configuration_changes(self):
        for variable in self.values.values():
            variable.trace_add("write", self._configuration_changed)

    def _configuration_changed(self, *_):
        if self._verified_config is not None:
            try:
                mysql_values = self._current_mysql_values()
            except ValueError:
                mysql_values = None
            if mysql_values != self._verified_config:
                self._verified_config = None
                self.status.configure(
                    text="La configuración cambió; vuelve a probar la conexión.",
                    fg=COLORS["error"],
                )
        self._update_whatsapp_availability()
        self._update_automation_controls()

    @staticmethod
    def _mysql_values(values):
        return {field: values[field] for field in MYSQL_CONFIG_FIELDS}

    def _runtime_mysql_is_verified(self):
        try:
            return self._current_mysql_values() == self._verified_config
        except ValueError:
            return False

    def _current_mysql_values(self):
        values = app_config.validate_connection_config(
            {
                "host": self.values["host"].get(),
                "port": self.values["port"].get(),
                "user": self.values["user"].get(),
                "password": self.values["password"].get(),
                "central_database": self.values["database_central"].get(),
                "dorian_database": self.values["database_dorian"].get(),
                "chat_destino": app_config.DEFAULT_CHAT_DESTINO,
            }
        )
        return self._mysql_values(values)

    def _current_values(self):
        values = app_config.validate_connection_config(
            {
                "host": self.values["host"].get(),
                "port": self.values["port"].get(),
                "user": self.values["user"].get(),
                "password": self.values["password"].get(),
                "central_database": self.values["database_central"].get(),
                "dorian_database": self.values["database_dorian"].get(),
                "chat_destino": self.values["chat_destino"].get(),
            }
        )
        values["horarios_envio"] = app_config.validate_horarios_envio(
            self._current_schedule_values()
        )
        return values

    @staticmethod
    def _verify_mysql_connection(values):
        import mysql.connector

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
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                if connection is not None:
                    connection.close()

    @staticmethod
    def _mysql_values_from_config(config):
        return {
            field: config[field]
            for field in MYSQL_CONFIG_FIELDS
        }

    @staticmethod
    def _whatsapp_session_state(page):
        chat_list = page.locator('[data-testid="chat-list"]')
        if chat_list.count() and chat_list.is_visible():
            return "ready"
        for selector in (
            '[data-testid="qrcode"]',
            'canvas[aria-label*="QR" i]',
        ):
            qr = page.locator(selector)
            if qr.count() and qr.is_visible():
                return "login"
        return "connecting"

    def _auto_start_saved_configuration(self):
        if self._closing or self._startup_in_progress or self._automation_active:
            return
        if self._saved_config is None:
            self.status.configure(
                text="Falta configuración válida; completa y guarda los datos.",
                fg=COLORS["error"],
            )
            self.automation_status.configure(
                text="Automatización: ○ Configuración requerida",
                fg=COLORS["muted"],
            )
            return

        try:
            saved_config = app_config.validate_connection_config(
                self._saved_config
            )
        except app_config.ConfigurationError as error:
            self.status.configure(
                text=f"Configuración inválida: {error}",
                fg=COLORS["error"],
            )
            return

        self._startup_in_progress = True
        self._startup_cancel_event = threading.Event()
        self.status.configure(
            text="Base de datos: ○ Verificando configuración guardada",
            fg=COLORS["muted"],
        )
        self.whatsapp_status.configure(text="Estado: ○ Conectando...")
        self.automation_status.configure(
            text="Automatización: ○ Iniciando",
            fg=COLORS["muted"],
        )
        self._update_automation_controls()
        self._schedule_automation_poll()
        self._startup_thread = threading.Thread(
            target=self._auto_start_worker,
            args=(saved_config, self._startup_cancel_event),
            name="DorianVentasAutoStart",
            daemon=True,
        )
        self._startup_thread.start()

    def _auto_start_worker(self, saved_config, cancel_event):
        try:
            self._verify_mysql_connection(saved_config)
        except ImportError:
            self._automation_events.put(
                (
                    "auto_start_error",
                    ("database", "MySQL: falta mysql-connector-python."),
                )
            )
            return
        except Exception as error:
            self._automation_events.put(
                (
                    "auto_start_error",
                    (
                        "database",
                        self._connection_error_message(error, saved_config),
                    ),
                )
            )
            return

        mysql_config = self._mysql_values_from_config(saved_config)
        self._automation_events.put(("auto_database_connected", mysql_config))
        if cancel_event.is_set():
            self._automation_events.put(("auto_start_cancelled", None))
            return

        try:
            page = self.whatsapp_browser.open_whatsapp()
        except Exception as error:
            self._automation_events.put(
                ("auto_start_error", ("whatsapp", str(error)))
            )
            return

        last_state = None
        while not cancel_event.is_set():
            try:
                session_state = self.whatsapp_browser.run_on_browser_thread(
                    self._whatsapp_session_state
                )
            except Exception as error:
                self._automation_events.put(
                    ("auto_start_error", ("whatsapp", str(error)))
                )
                return

            if session_state == "ready":
                self._automation_events.put(
                    ("auto_start_ready", (page, mysql_config))
                )
                return
            if session_state != last_state:
                self._automation_events.put(
                    ("auto_whatsapp_state", (session_state, page))
                )
                last_state = session_state
            if cancel_event.wait(2):
                break
        self._automation_events.put(("auto_start_cancelled", None))

    def _test_connection(self):
        self._verified_config = None
        try:
            values = self._current_mysql_values()
        except ValueError as error:
            messagebox.showwarning("Revisa la configuración", str(error), parent=self.root)
            return

        try:
            self._verify_mysql_connection(values)
        except ImportError:
            messagebox.showerror(
                "Conector no disponible",
                "No se encontró mysql-connector-python en este entorno de Python.",
                parent=self.root,
            )
            return
        except ValueError as error:
            messagebox.showerror("Nombre de base no válido", str(error), parent=self.root)
            return
        except Exception as error:
            messagebox.showerror(
                "No se pudo establecer la conexión",
                self._connection_error_message(error, values),
                parent=self.root,
            )
            return

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
        mysql_values = self._mysql_values(values)
        saved_chat_destino = (
            self._saved_config.get(
                "chat_destino",
                app_config.DEFAULT_CHAT_DESTINO,
            )
            if self._saved_config is not None
            else app_config.DEFAULT_CHAT_DESTINO
        )
        if values["chat_destino"] != saved_chat_destino:
            return False
        return (
            mysql_values == self._verified_config
            or (
                self._saved_config is not None
                and mysql_values == self._mysql_values(self._saved_config)
            )
        )

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
        if self._startup_in_progress:
            self.whatsapp_status.configure(
                text="Estado: ○ Conectando automáticamente; completa el inicio de sesión en Chrome si se solicita."
            )
            return

        try:
            page = self.whatsapp_browser.open_whatsapp()
            session_state = self.whatsapp_browser.run_on_browser_thread(
                self._whatsapp_session_state
            )
        except ChromeNotFoundError as error:
            self.whatsapp_page = None
            self._whatsapp_authenticated = False
            self.whatsapp_status.configure(text="Estado: ○ No iniciado")
            self._update_automation_controls()
            messagebox.showerror("Google Chrome no encontrado", str(error), parent=self.root)
            return
        except BrowserDependencyError as error:
            self.whatsapp_page = None
            self._whatsapp_authenticated = False
            self.whatsapp_status.configure(text="Estado: ○ No iniciado")
            self._update_automation_controls()
            messagebox.showerror("Playwright no disponible", str(error), parent=self.root)
            return
        except Exception as error:
            self.whatsapp_page = None
            self._whatsapp_authenticated = False
            state = "Navegador abierto" if self.whatsapp_browser.is_open else "○ No iniciado"
            self.whatsapp_status.configure(text=f"Estado: {state}")
            self._update_automation_controls()
            messagebox.showerror("No se pudo abrir WhatsApp Web", str(error), parent=self.root)
            return

        self.whatsapp_page = page
        self._whatsapp_authenticated = session_state == "ready"
        if session_state == "ready":
            self.whatsapp_status.configure(text="Estado: ✓ Listo")
        elif session_state == "login":
            self.whatsapp_status.configure(
                text="Estado: ○ Requiere inicio de sesión (completa el QR en Chrome)"
            )
        else:
            self.whatsapp_status.configure(text="Estado: ○ Conectando...")
        self._update_automation_controls()

    def _update_automation_controls(self):
        if not hasattr(self, "start_automation_button"):
            return
        ready = (
            self._whatsapp_configuration_ready()
            and self._runtime_mysql_is_verified()
            and self._whatsapp_authenticated
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
        if self._automation_active or (
            self._automation_thread is not None
            and self._automation_thread.is_alive()
        ):
            self.automation_status.configure(
                text="Automatización: ✓ Ya está activa",
                fg=COLORS["success"],
            )
            return
        if not self.values["chat_destino"].get().strip():
            messagebox.showwarning(
                "Destino de WhatsApp obligatorio",
                "Escribe el nombre del chat o grupo de WhatsApp.",
                parent=self.root,
            )
            return
        if not (
            self._whatsapp_configuration_ready()
            and self._runtime_mysql_is_verified()
            and self._whatsapp_authenticated
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
            elif event == "auto_database_connected":
                try:
                    current_mysql = self._current_mysql_values()
                except ValueError:
                    current_mysql = None
                if current_mysql == detail:
                    self._verified_config = detail.copy()
                    self.status.configure(
                        text="Base de datos: ✓ Conectada",
                        fg=COLORS["success"],
                    )
                else:
                    self._verified_config = None
                    self.status.configure(
                        text="La configuración MySQL cambió durante el inicio; vuelve a probarla.",
                        fg=COLORS["error"],
                    )
                self._update_whatsapp_availability()
                self._update_automation_controls()
            elif event == "auto_whatsapp_state":
                state, page = detail
                self.whatsapp_page = page
                self._whatsapp_authenticated = False
                if state == "login":
                    self.whatsapp_status.configure(
                        text="Estado: ○ Requiere inicio de sesión (completa el QR en Chrome)"
                    )
                    self.automation_status.configure(
                        text="Automatización: ○ Esperando inicio de sesión",
                        fg=COLORS["muted"],
                    )
                else:
                    self.whatsapp_status.configure(
                        text="Estado: ○ Conectando..."
                    )
                self._update_whatsapp_availability()
                self._update_automation_controls()
            elif event == "auto_start_ready":
                if self._closing:
                    if self._startup_cancel_event is not None:
                        self._startup_cancel_event.set()
                    continue
                page, mysql_config = detail
                try:
                    current_mysql = self._current_mysql_values()
                except ValueError:
                    current_mysql = None
                self.whatsapp_page = page
                self._whatsapp_authenticated = True
                self._startup_in_progress = False
                if current_mysql == mysql_config:
                    self._verified_config = mysql_config.copy()
                    self.status.configure(
                        text="Base de datos: ✓ Conectada",
                        fg=COLORS["success"],
                    )
                    self.whatsapp_status.configure(text="Estado: ✓ Listo")
                    self._update_whatsapp_availability()
                    self._update_automation_controls()
                    if self._whatsapp_configuration_ready():
                        self._start_automation()
                    else:
                        self.automation_status.configure(
                            text="Automatización: ○ Guarda el destino vigente para iniciar",
                            fg=COLORS["muted"],
                        )
                else:
                    self._verified_config = None
                    self.status.configure(
                        text="La configuración MySQL cambió durante el inicio; vuelve a probarla.",
                        fg=COLORS["error"],
                    )
                    self.whatsapp_status.configure(text="Estado: ✓ Listo")
                    self._update_whatsapp_availability()
                    self._update_automation_controls()
            elif event == "auto_start_error":
                component, detail = detail
                self._startup_in_progress = False
                if component == "database":
                    self._verified_config = None
                    self.status.configure(
                        text=f"Base de datos: Error. {detail}",
                        fg=COLORS["error"],
                    )
                    self.whatsapp_status.configure(text="Estado: ○ No iniciado")
                else:
                    self.whatsapp_status.configure(
                        text="Estado: ○ Error al iniciar"
                    )
                    self.status.configure(
                        text=f"WhatsApp: Error. {detail}",
                        fg=COLORS["error"],
                    )
                self._automation_active = False
                self.automation_status.configure(
                    text="Automatización: ○ No iniciada",
                    fg=COLORS["error"],
                )
                self._update_whatsapp_availability()
                self._update_automation_controls()
            elif event == "auto_start_cancelled":
                self._startup_in_progress = False
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

        if self._automation_active or self._startup_in_progress:
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
        if self._startup_cancel_event is not None:
            self._startup_cancel_event.set()
        if self._automation_active:
            self._stop_automation()
            return
        self._finish_close()

    def _finish_close(self):
        if (
            self._startup_thread is not None
            and self._startup_thread.is_alive()
        ):
            self.root.after(100, self._finish_close)
            return
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
        if self._verified_config != self._mysql_values(values):
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

        self._set_schedule_rows(values["horarios_envio"])
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