"""Hold exceptions that may occur during config loading."""

class SettingIsNoneException(Exception):
    """Exception raised when setting a setting is None."""

    def __init__(self, setting) -> None:
        super().__init__(f"Required setting '{setting}' is not configured.")
