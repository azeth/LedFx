import datetime
import json
import logging
import os
import shutil
import sys

import voluptuous as vol

from ledfx.consts import CONFIGURATION_VERSION

CONFIG_DIRECTORY = ".ledfx"
CONFIG_FILE_NAME = "config.json"
PRESETS_FILE_NAME = "presets.json"

CORE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("host", default="0.0.0.0"): str,
        vol.Optional("port", default=8888): int,
        vol.Optional("dev_mode", default=False): bool,
        vol.Optional("devices", default=[]): list,
        vol.Optional("displays", default=[]): list,
        vol.Optional("ledfx_presets", default={}): dict,
        vol.Optional("user_presets", default={}): dict,
        vol.Optional("scenes", default={}): dict,
        vol.Optional("integrations", default=[]): list,
        vol.Optional("scan_on_startup", default=False): bool,
        vol.Optional(
            "wled_preferences",
            default={
                "wled_preferred_mode": {
                    "setting": "",
                    "user_enabled": False,
                },
                "realtime_gamma_enabled": {
                    "setting": False,
                    "user_enabled": False,
                },
                "force_max_brightness": {
                    "setting": False,
                    "user_enabled": False,
                },
                "realtime_dmx_mode": {
                    "setting": "MultiRGB",
                    "user_enabled": False,
                },
                "start_universe_setting": {
                    "setting": 1,
                    "user_enabled": False,
                },
                "dmx_address_start": {
                    "setting": 1,
                    "user_enabled": False,
                },
                "inactivity_timeout": {
                    "setting": 1,
                    "user_enabled": False,
                },
            },
        ): dict,
        vol.Optional(
            "configuration_version", default=CONFIGURATION_VERSION
        ): str,
    },
    extra=vol.ALLOW_EXTRA,
)


def load_logger():
    global _LOGGER
    _LOGGER = logging.getLogger(__name__)


def get_default_config_directory() -> str:
    """Get the default configuration directory"""

    base_dir = (
        os.getenv("APPDATA") if os.name == "nt" else os.path.expanduser("~")
    )
    return os.path.join(base_dir, CONFIG_DIRECTORY)


def get_config_file(config_dir: str) -> str:
    """Finds a supported configuration file in the provided directory"""

    json_path = os.path.join(config_dir, CONFIG_FILE_NAME)
    if os.path.isfile(json_path) is False:  # Can't find a JSON file
        return None  # No Valid Configs, return None to build another one
    return json_path  # Return the JSON file if we find one.


def get_preset_file(config_dir: str) -> str:
    """Finds a supported preset file in the provided directory"""

    json_path = os.path.join(config_dir, PRESETS_FILE_NAME)
    if os.path.isfile(json_path) is False:  # Can't find a JSON file
        return None  # No Valid Configs, return None to build another one
    return json_path  # Return the JSON file if we find one.


def get_profile_dump_location() -> str:
    config_dir = get_default_config_directory()
    date_time = datetime.datetime.now().strftime("%d-%m-%y_%H-%M-%S")
    return os.path.join(config_dir, f"LedFx_{date_time}.profile")


def get_log_file_location():
    config_dir = get_default_config_directory()
    log_file_path = os.path.abspath(os.path.join(config_dir, "LedFx.log"))
    return log_file_path


def create_default_config(config_dir: str) -> str:
    """Creates a default configuration in the provided directory"""

    config_path = os.path.join(config_dir, CONFIG_FILE_NAME)
    try:
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(
                CORE_CONFIG_SCHEMA({}),
                file,
                ensure_ascii=False,
                sort_keys=True,
                indent=4,
            )
        return config_path

    except OSError:
        print(f"Unable to create default configuration file {config_path}.")

        return None


def ensure_config_file(config_dir: str) -> str:
    """Checks if a config file exists, and otherwise creates one"""

    ensure_config_directory(config_dir)
    config_path = get_config_file(config_dir)
    if config_path is None:
        config_path = create_default_config(config_dir)

    return config_path


def check_preset_file(config_dir: str) -> str:

    ensure_config_directory(config_dir)
    presets_path = get_preset_file(config_dir)
    if presets_path is None:
        return None

    return presets_path


def ensure_config_directory(config_dir: str) -> None:
    """Validate that the config directory is valid."""

    # If an explicit path is provided simply check if it exist and failfast
    # if it doesn't. Otherwise, if we have the default directory attempt to
    # create the file
    if not os.path.isdir(config_dir):
        if config_dir != get_default_config_directory():
            print(
                ("Error: Invalid configuration directory {}").format(
                    config_dir
                )
            )
            sys.exit(1)

        try:
            os.mkdir(config_dir)
        except OSError:
            print(
                ("Error: Unable to create configuration directory {}").format(
                    config_dir
                )
            )
            sys.exit(1)


def load_config(config_dir: str) -> dict:
    """Validates and loads the configuration file in the provided directory"""

    config_file = ensure_config_file(config_dir)
    print(
        f"Loading configuration file: {os.path.join(config_dir, CONFIG_FILE_NAME)}"
    )
    try:

        with open(config_file, encoding="utf-8") as file:
            config_json = json.load(file)
            try:
                # If there's no config version in the config, it's pre-1.0.0 and won't work
                # Probably scope to iterate through it and create a display for every device, but that's beyond me
                _LOGGER.info(
                    f"LedFx Configuration Version: {config_json['configuration_version']}"
                )
                return CORE_CONFIG_SCHEMA(config_json)
            except KeyError:
                create_backup(config_dir, config_file, "VERSION")
                return CORE_CONFIG_SCHEMA({})
    except json.JSONDecodeError:
        create_backup(config_dir, config_file, "DECODE")
        return CORE_CONFIG_SCHEMA({})
    except OSError:
        create_backup(config_dir, config_file, "OSERROR")
        return CORE_CONFIG_SCHEMA({})


def create_backup(config_dir, config_file, errortype):
    """This function creates a backup of the current configuration file - it uses the format dd-mm-yyyy_hh-mm-ss for the backup file.

    Args:
        config_dir (path): The path to the current configuration directory
        config_file (path): The path to the current configuration file
        errortype (string): The type of error we encounter to allow for better logging
    """

    date = datetime.datetime.now().strftime("%d-%m-%y_%H-%M-%S")
    backup_location = os.path.join(config_dir, f"config.json.backup.{date}")
    try:
        os.rename(config_file, backup_location)
    except OSError:
        shutil.copy2(config_file, backup_location)

    if errortype == "DECODE":
        _LOGGER.warning(
            "Error loading configuration. Backup created, empty configuration used."
        )

    if errortype == "VERSION":
        _LOGGER.warning(
            "Incompatible Configuration Detected. Backup Created, empty configuration used."
        )

    if errortype == "OSERROR":
        _LOGGER.warning(
            "Unable to Open Configuration. Backup Created, empty configuration used."
        )

    _LOGGER.warning(f"Backup Located at: {backup_location}")


def save_config(config: dict, config_dir: str) -> None:
    """Saves the configuration to the provided directory"""

    config_file = ensure_config_file(config_dir)
    _LOGGER.info(("Saving configuration file to {}").format(config_dir))
    config["configuration_version"] = CONFIGURATION_VERSION
    config_view = dict(config)
    unneeded_keys = ["ledfx_presets"]
    for key in [key for key in config_view if key in unneeded_keys]:
        del config_view[key]

    with open(config_file, "w", encoding="utf-8") as file:
        json.dump(
            config_view, file, ensure_ascii=False, sort_keys=True, indent=4
        )


def save_presets(config: dict, config_dir: str) -> None:
    """Saves the configuration to the provided directory"""

    presets_file = check_preset_file(config_dir)
    _LOGGER.info(("Saving user presets to {}").format(config_dir))

    config_view = dict(config)
    for key in [key for key in config_view if key != "user_presets"]:
        del config_view[key]

    with open(presets_file, "w", encoding="utf-8") as file:
        json.dump(
            config_view, file, ensure_ascii=False, sort_keys=True, indent=4
        )
