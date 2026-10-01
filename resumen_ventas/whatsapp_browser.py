import os
from pathlib import Path
import queue
import shutil
import sys
import threading


WHATSAPP_URL = "https://web.whatsapp.com"


class ChromeNotFoundError(RuntimeError):
    pass


class BrowserDependencyError(RuntimeError):
    pass


def find_chrome_executable():
    candidates = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        directory = os.environ.get(variable)
        if directory:
            candidates.append(
                Path(directory) / "Google" / "Chrome" / "Application" / "chrome.exe"
            )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    for executable in ("chrome.exe", "chrome"):
        located = shutil.which(executable)
        if located:
            return Path(located)
    return None


def persistent_profile_path():
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base_directory = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        profile = base_directory / "DorianMuebles" / "chrome_profile"
    else:
        development_profile = (
            Path(__file__).resolve().parent.parent / "chrome_profile"
        )
        if development_profile.is_dir():
            return development_profile
        local_app_data = os.environ.get("LOCALAPPDATA")
        base_directory = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        profile = base_directory / "DorianMuebles" / "chrome_profile"

    profile.mkdir(parents=True, exist_ok=True)
    return profile


class WhatsAppBrowser:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self._thread = None
        self._commands = queue.Queue()
        self._startup_complete = threading.Event()
        self._shutdown_requested = threading.Event()
        self._page_available = threading.Event()
        self._startup_error = None

    @property
    def is_open(self):
        return self.context is not None

    @property
    def has_page(self):
        return self._page_available.is_set()

    def open_whatsapp(self):
        chrome_path = find_chrome_executable()
        if chrome_path is None:
            raise ChromeNotFoundError(
                "No se encontró Google Chrome en las ubicaciones habituales. "
                "Instala Chrome o verifica su instalación."
            )

        if self._thread is not None and self._thread.is_alive():
            return self.run_on_browser_thread(self._open_or_focus_page)

        self._startup_error = None
        self._startup_complete.clear()
        self._shutdown_requested.clear()
        self._page_available.clear()
        self._commands = queue.Queue()
        self._thread = threading.Thread(
            target=self._browser_thread_main,
            args=(chrome_path,),
            name="DorianWhatsAppBrowser",
            daemon=True,
        )
        self._thread.start()
        if not self._startup_complete.wait(timeout=60):
            self.close(timeout=5)
            raise TimeoutError("Chrome tardó demasiado en abrir WhatsApp Web.")
        if self._startup_error is not None:
            error = self._startup_error
            self._thread.join(timeout=5)
            raise error
        return self.page

    def run_on_browser_thread(self, callback):
        if threading.current_thread() is self._thread:
            return callback(self.page)
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError("El hilo propietario de Chrome no está activo.")

        command = {
            "callback": callback,
            "completed": threading.Event(),
            "result": None,
            "error": None,
        }
        self._commands.put(command)
        command["completed"].wait()
        if command["error"] is not None:
            raise command["error"]
        return command["result"]

    def _browser_thread_main(self, chrome_path):
        try:
            self._launch_browser(chrome_path)
        except Exception as error:
            self._startup_error = error
            self._startup_complete.set()
            self._cleanup_browser()
            return

        self._startup_complete.set()
        try:
            while not self._shutdown_requested.is_set():
                try:
                    command = self._commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                if command is None:
                    break
                try:
                    command["result"] = command["callback"](self.page)
                except Exception as error:
                    command["error"] = error
                finally:
                    command["completed"].set()
        finally:
            self._fail_pending_commands()
            self._cleanup_browser()

    def _launch_browser(self, chrome_path):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserDependencyError(
                "Playwright no está disponible en este entorno de Python."
            ) from error

        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(persistent_profile_path()),
            executable_path=str(chrome_path),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )
        self._open_or_focus_page()

    def _open_or_focus_page(self, _page=None):
        if self.page is None or self.page.is_closed():
            pages = [page for page in self.context.pages if not page.is_closed()]
            self.page = pages[0] if pages else self.context.new_page()
            self.page.on("close", lambda *_: self._page_available.clear())
            self._page_available.set()
        self.page.bring_to_front()
        if self.page.url != WHATSAPP_URL:
            self.page.goto(WHATSAPP_URL)
        return self.page

    def _fail_pending_commands(self):
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            if command is not None:
                command["error"] = RuntimeError("El navegador se está cerrando.")
                command["completed"].set()

    def _cleanup_browser(self):
        context = self.context
        playwright = self.playwright
        self.context = None
        self.playwright = None
        self.page = None
        self._page_available.clear()
        try:
            if context is not None:
                context.close()
        finally:
            if playwright is not None:
                playwright.stop()

    def close(self, timeout=10):
        thread = self._thread
        if thread is None:
            return
        self._shutdown_requested.set()
        self._commands.put(None)
        if thread is threading.current_thread():
            return
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise TimeoutError("Chrome/Playwright no terminó de cerrarse a tiempo.")
        self._thread = None