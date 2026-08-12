"""Hold exceptions related to services."""

class ServicesNotFoundError(Exception):
    """Exception raised when a service is not found or the services.json file is missing."""