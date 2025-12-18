"""Test cases for the communicator module."""

import pytest
from embodycodec import codec

from embodyserial import embodyserial as serialcomm
from tests.conftest import DummySerial


@pytest.mark.api
def test_send_receive_sync() -> None:
    """Test a send/receive cycle."""
    heartbeat_response = bytes.fromhex("8100059053")
    serial = DummySerial(heartbeat_response)
    communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
    response = communicator.send(msg=codec.Heartbeat(), timeout=3)
    assert response
    assert isinstance(response, codec.HeartbeatResponse)
