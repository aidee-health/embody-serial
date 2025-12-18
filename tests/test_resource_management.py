"""Test resource management and cleanup."""

from unittest.mock import MagicMock, patch

from serial.serialutil import SerialException

from embodyserial import embodyserial as serialcomm
from tests.test_embodyserial import DummySerial


class TestPortManagement:
    """Test serial port resource management."""

    def test_port_closes_on_detection_error(self):
        """Verify port is closed even when detection fails."""
        with patch("serial.Serial") as mock_serial:
            mock_instance = MagicMock()
            mock_instance.is_open = True
            mock_instance.in_waiting = 0
            mock_instance.write.side_effect = SerialException("Port error")
            mock_serial.return_value = mock_instance

            mock_port = MagicMock()
            mock_port.device = "/dev/ttyUSB0"

            result = serialcomm.EmbodySerial._EmbodySerial__port_is_alive(mock_port)  # type: ignore[attr-defined]

            assert result is False
            mock_instance.close.assert_called_once()

    def test_port_closes_on_detection_success(self):
        """Verify port is closed after successful detection."""
        with patch("serial.Serial") as mock_serial:
            mock_instance = MagicMock()
            mock_instance.is_open = True
            mock_instance.in_waiting = 0
            mock_instance.read.return_value = bytes.fromhex("8100059053")
            mock_serial.return_value = mock_instance

            mock_port = MagicMock()
            mock_port.device = "/dev/ttyUSB0"

            result = serialcomm.EmbodySerial._EmbodySerial__port_is_alive(mock_port)  # type: ignore[attr-defined]

            assert result is True
            mock_instance.close.assert_called_once()


class TestShutdownResilience:
    """Test graceful shutdown handling."""

    def test_shutdown_handles_serial_errors(self):
        """Verify shutdown completes even with serial errors."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        # Mock serial to raise on buffer operations
        with patch.object(serial, "reset_input_buffer", side_effect=OSError("Error")):
            with patch.object(serial, "reset_output_buffer", side_effect=OSError("Error")):
                with patch.object(serial, "close", side_effect=SerialException("Error")):
                    # Should not raise
                    communicator.shutdown()

    def test_double_shutdown_is_safe(self):
        """Verify calling shutdown twice doesn't cause issues."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        communicator.shutdown()
        # Second shutdown should be no-op
        communicator.shutdown()

    def test_shutdown_with_disconnected_port(self):
        """Verify shutdown handles already disconnected ports."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        # Simulate disconnection
        serial.is_open = False

        # Should handle gracefully
        communicator.shutdown()


class TestThreadExecutorManagement:
    """Test thread executor separation for starvation prevention."""

    def test_three_separate_executors(self):
        """Verify three separate executors exist to prevent callback starvation."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        reader = communicator._EmbodySerial__reader  # type: ignore[attr-defined]

        # Should have three separate executors
        assert hasattr(reader, "_ReaderThread__message_listener_executor")
        assert hasattr(reader, "_ReaderThread__response_message_listener_executor")
        assert hasattr(reader, "_ReaderThread__file_download_listener_executor")

        # Verify they are different instances
        assert (
            reader._ReaderThread__message_listener_executor != reader._ReaderThread__response_message_listener_executor
        )
        assert reader._ReaderThread__message_listener_executor != reader._ReaderThread__file_download_listener_executor
        assert (
            reader._ReaderThread__response_message_listener_executor
            != reader._ReaderThread__file_download_listener_executor
        )

        communicator.shutdown()

    def test_executors_cleanup_on_stop(self):
        """Verify all executors are properly shut down."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        reader = communicator._EmbodySerial__reader  # type: ignore[attr-defined]
        msg_executor = reader._ReaderThread__message_listener_executor
        rsp_executor = reader._ReaderThread__response_message_listener_executor
        file_executor = reader._ReaderThread__file_download_listener_executor

        communicator.shutdown()

        # All executors should be shut down
        assert msg_executor._shutdown is True
        assert rsp_executor._shutdown is True
        assert file_executor._shutdown is True
