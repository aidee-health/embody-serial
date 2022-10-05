"""Test cases for the communicator module."""

import threading
import time

from embodycodec import codec
from serial.serialutil import SerialBase

from embodyserial import communicator as serialcomm


def test_send_receive_sync() -> None:
    """Test a send/receive cycle."""
    heartbeat_response = bytes.fromhex("8100059053")
    serial = DummySerial(heartbeat_response)
    communicator = serialcomm.EmbodySerialCommunicator(
        serial_port="Dummy", serial_instance=serial
    )
    response = communicator.send_message_and_wait_for_response(
        msg=codec.Heartbeat(), timeout=3
    )
    assert response
    assert isinstance(response, codec.HeartbeatResponse)


class DummySerial(SerialBase):
    """Serial port implementation for plain sockets."""

    def __init__(self, response_data: bytes = None) -> None:
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
        if not self.__response_data or self.__response_data_pos + size > len(
            self.__response_data
        ):
            self.__response_data_available.clear()
            self.__response_data_available.wait()
        part = self.__response_data[
            self.__response_data_pos : self.__response_data_pos + size
        ]
        self.__response_data_pos += size
        return part

    def write(self, data):
        """Dummy write method."""
        return len(data)

    def _reconfigure_port(self):
        """Implement unimplemented SerialBase method."""
        pass
