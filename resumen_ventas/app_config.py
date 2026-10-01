import json
import os
import tempfile
from pathlib import Path


CONFIG_FILENAME = "ventas_config.json"
CONFIG_DIRECTORY = "DorianMuebles"


class ConfigurationError(ValueError):
    pass


def config_path():
    app_data = os.environ.get("APPDATA")
    if app_data:
        base_directory = Path(app_data)
    elif os.name == "nt":
        base_directory = Path.home() / "AppData" / "Roaming"
    else:
        base_directory = Path.home() / ".config"
    return base_directory / CONFIG_DIRECTORY / CONFIG_FILENAME


def _read_password(config):
    password = config.get("password")
    if not isinstance(password, str):
        raise ConfigurationError("El campo contraseña debe ser texto.")
    return password


def _write_password(config, password):
    config["password"] = password


def validate_connection_config(config):
    if not isinstance(config, dict):
        raise ConfigurationError("La configuración debe ser un objeto.")

    for field in ("host", "user", "central_database", "dorian_database"):
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"El campo {field} es obligatorio.")
        if "\x00" in value:
            raise ConfigurationError(f"El campo {field} no es válido.")

    password = _read_password(config)
    port_value = config.get("port")
    if (
        isinstance(port_value, bool)
        or not isinstance(port_value, (str, int))
        or (isinstance(port_value, str) and not port_value.strip().isdecimal())
    ):
        raise ConfigurationError("El puerto debe ser un número entre 1 y 65535.")
    try:
        port = int(port_value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "El puerto debe ser un número entre 1 y 65535."
        ) from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("El puerto debe ser un número entre 1 y 65535.")

    return {
        "host": config["host"],
        "port": port,
        "user": config["user"],
        "password": password,
        "central_database": config["central_database"],
        "dorian_database": config["dorian_database"],
    }


def load_config():
    path = config_path()
    try:
        with path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ConfigurationError(
            "El archivo de configuración no contiene JSON válido."
        ) from error

    if not isinstance(config, dict):
        raise ConfigurationError("El archivo de configuración debe ser un objeto.")

    if "central_database" not in config and "database_central" in config:
        config["central_database"] = config["database_central"]
    if "dorian_database" not in config and "database_dorian" in config:
        config["dorian_database"] = config["database_dorian"]
    return validate_connection_config(config)


def get_connection_config():
    config = load_config()
    if config is None:
        raise ConfigurationError("No existe una configuración de conexión guardada.")
    return config


def save_config(config):
    validated = validate_connection_config(config)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "host": validated["host"],
        "port": validated["port"],
        "user": validated["user"],
        "central_database": validated["central_database"],
        "dorian_database": validated["dorian_database"],
    }
    _write_password(payload, validated["password"])

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{CONFIG_FILENAME}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return validated