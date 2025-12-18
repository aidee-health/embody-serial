"""Shared test fixtures and utilities."""

import threading
import time

from serial.serialutil import SerialBase


class DummySerial(SerialBase):
    """Serial port implementation for testing."""

    def __init__(self, response_data: bytes | None = None) -> None:
        self.__response_data_available = threading.Event()
        self.__response_data = response_data
        self.__response_data_pos = 0
        if response_data:
            self.set_read_data(response_data)
        self.is_open = True

    def set_read_data(self, data: bytes) -> None:
        """Set data used for read method"""
        self.__response_data = data
        self.__response_data_pos = 0
        self.__response_data_available.set()

    def read(self, size=1):
        """Uses __response_data buffer to return requested data."""
        time.sleep(0.5)
        if not self.__response_data or self.__response_data_pos + size > len(self.__response_data):
            self.__response_data_available.clear()
            self.__response_data_available.wait()
        part = self.__response_data[self.__response_data_pos : self.__response_data_pos + size]  # type: ignore[index]
        self.__response_data_pos += size
        return part

    def write(self, data):
        """Dummy write method."""
        return len(data)

    def _reconfigure_port(self):
        """Implement unimplemented SerialBase method."""
        pass

    def reset_input_buffer(self):
        """Reset input buffer."""
        pass

    def reset_output_buffer(self):
        """Reset output buffer."""
        pass

    def close(self):
        """Close port."""
        self.is_open = False
