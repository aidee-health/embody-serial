"""Specific exceptions for package."""
from embodycodec import codec


class NackError(Exception):
    """Exception for nack messages."""

    def __init__(self, nackmsg: codec.NackResponse) -> None:
        """Override init."""
        self.nackmsg = nackmsg

    def __str__(self):
        """Override to string method."""
        return f"Nack Response code {self.nackmsg.response_code} ({self.nackmsg.error_message()})"


class MissingResponseError(Exception):
    """Error when no response is received."""

    ...


class CrcError(Exception):
    """Error when invalid crc is received for message from device."""

    ...


class TimeoutError(Exception):
    """Error when invalid crc is received for message from device."""

    ...
