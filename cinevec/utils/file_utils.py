from pathlib import Path

import yaml
from box import ConfigBox

from cinevec.logging import logger


def path_exists(path: str) -> bool:
    """
    Check if a given path exists.

    Args:
        path (str): The path to check.

    Returns:
        bool: True if the path exists, False otherwise.
    """
    return Path(path).exists()


def create_path(path: str) -> Path:
    """
    Ensure that a given path exists. If it does not exist, create it.
    """
    p = Path(path)

    if p.suffix:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
    else:
        p.mkdir(parents=True, exist_ok=True)

    return p


def open_yaml_file(path: str) -> ConfigBox:
    """
    Open a YAML file and return its contents as a ConfigBox.
    """

    with open(path) as f:
        data = yaml.safe_load(f)

    logger.info(f"Loaded YAML file from {path}")

    return ConfigBox(data)


def load_config_file(path: str = "config/config.yaml") -> ConfigBox:
    """
    Load a configuration file (YAML) and return its contents as a ConfigBox.
    """
    return open_yaml_file(path)
