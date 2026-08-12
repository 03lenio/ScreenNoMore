import os
from pathlib import Path

from dotenv import load_dotenv
from backend.config.exceptions import SettingIsNoneException

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        load_dotenv(Path.cwd() / ".env")
        self._initialized = True

    @staticmethod
    def get_setting(setting: str, default: str = None) -> list[str] | str:
        loaded_setting = os.getenv(setting)
        if loaded_setting is None and default is None:
            raise SettingIsNoneException(setting)
        elif loaded_setting is None:
            loaded_setting = default
        if loaded_setting.startswith("LIST:"):
            return [
                item.strip()
                for item in loaded_setting.removeprefix("LIST:").split(",")
            ]
        return loaded_setting
