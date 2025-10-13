"""Test connection and disconnection handling."""

from embodyserial import embodyserial as serialcomm
from tests.test_embodyserial import DummySerial


class TestConnectionHandling:
    """Test connection state management."""

    def test_download_aborts_when_disconnected(self):
        """Verify download_file_with_retries returns None when disconnected."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        # Simulate immediate disconnection
        with communicator._EmbodySerial__shutdown_lock:
            communicator._EmbodySerial__connected = False

        result = communicator.download_file_with_retries(file_name="test.bin", file_size=1024, retries=3)

        assert result is None
        communicator.shutdown()

    def test_empty_file_download(self):
        """Verify empty file download returns immediately."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        # Empty file should return temp file path immediately
        result = communicator.download_file(file_name="empty.bin", size=0, timeout=1)

        assert result is not None
        assert result.startswith("/")  # Should be absolute path
        communicator.shutdown()

    def test_shutdown_with_closed_serial(self):
        """Verify shutdown handles already closed serial port."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        # Close serial port before shutdown
        serial.is_open = False

        # Should not raise exception
        communicator.shutdown()
