"""Test error handling and validation improvements."""

from unittest.mock import MagicMock, patch

import pytest
from embodycodec import codec
from serial.serialutil import SerialException

from embodyserial.exceptions import MissingResponseError, NackError
from embodyserial.helpers import EmbodySendHelper
from tests.conftest import DummySerial
from embodyserial import embodyserial as serialcomm


@pytest.mark.error_handling
@pytest.mark.fast
class TestHelperValidation:
    """Test helper method validation improvements."""

    def test_raises_missing_response_error(self):
        """Verify MissingResponseError is raised when no response."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        with patch.object(communicator, "send", return_value=None):
            with pytest.raises(MissingResponseError):
                helper.get_serial_no()

            with pytest.raises(MissingResponseError):
                helper.get_vendor()

            with pytest.raises(MissingResponseError):
                helper.get_model()

        communicator.shutdown()

    def test_raises_nack_error(self):
        """Verify NackError is raised for NACK responses."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        nack_response = codec.NackResponse(response_code=1)
        with patch.object(communicator, "send", return_value=nack_response):
            with pytest.raises(NackError):
                helper.get_files()

            with pytest.raises(NackError):
                helper.delete_file("test.bin")

            with pytest.raises(NackError):
                helper.reformat_disk()

        communicator.shutdown()

    def test_raises_value_error_for_none_values(self):
        """Verify ValueError is raised instead of assertion for None values."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        # Create mock attribute with None formatted_value
        mock_attribute = MagicMock()
        mock_attribute.formatted_value.return_value = None

        mock_response = MagicMock(spec=codec.GetAttributeResponse)
        mock_response.value = mock_attribute

        with patch.object(communicator, "send", return_value=mock_response):
            with pytest.raises(ValueError, match="Serial number not available"):
                helper.get_serial_no()

            with pytest.raises(ValueError, match="Vendor information not available"):
                helper.get_vendor()

            with pytest.raises(ValueError, match="Model information not available"):
                helper.get_model()

            with pytest.raises(ValueError, match="Bluetooth MAC address not available"):
                helper.get_bluetooth_mac()

            with pytest.raises(ValueError, match="Firmware version not available"):
                helper.get_firmware_version()

        communicator.shutdown()

    def test_raises_type_error_for_wrong_response_type(self):
        """Verify TypeError is raised for incorrect response types."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        # Return wrong response type
        wrong_response = codec.HeartbeatResponse()
        with patch.object(communicator, "send", return_value=wrong_response):
            with pytest.raises(TypeError, match="Expected ListFilesResponse"):
                helper.get_files()

            with pytest.raises(TypeError, match="Expected DeleteFileResponse"):
                helper.delete_file("test.bin")

            with pytest.raises(TypeError, match="Expected ReformatDiskResponse"):
                helper.reformat_disk()

            with pytest.raises(TypeError, match="Expected DeleteAllFilesResponse"):
                helper.delete_all_files()

            with pytest.raises(TypeError, match="Expected GetAttributeResponse"):
                helper.get_serial_no()

        communicator.shutdown()


@pytest.mark.error_handling
class TestExceptionSpecificity:
    """Test specific exception handling instead of generic catches."""

    def test_delete_file_handles_specific_exceptions(self):
        """Verify delete_file_with_retries handles specific exceptions."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        # Test SerialException handling
        with patch.object(helper, "delete_file", side_effect=SerialException("Port error")):
            result = helper.delete_file_with_retries("test.bin", retries=1, timeout_seconds_per_retry=0.01)
            assert result is False

        # Test NackError handling
        nack_error = NackError(codec.NackResponse(response_code=1))
        with patch.object(helper, "delete_file", side_effect=nack_error):
            result = helper.delete_file_with_retries("test.bin", retries=1, timeout_seconds_per_retry=0.01)
            assert result is False

        # Test MissingResponseError handling
        with patch.object(helper, "delete_file", side_effect=MissingResponseError("No response")):
            result = helper.delete_file_with_retries("test.bin", retries=1, timeout_seconds_per_retry=0.01)
            assert result is False

        communicator.shutdown()

    def test_temperature_type_validation(self):
        """Verify get_temperature validates attribute type."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        helper = EmbodySendHelper(sender=communicator, timeout=1)

        # Mock wrong attribute type
        wrong_attribute = MagicMock()
        wrong_attribute.__class__.__name__ = "WrongAttribute"

        mock_response = MagicMock(spec=codec.GetAttributeResponse)
        mock_response.value = wrong_attribute

        with patch.object(communicator, "send", return_value=mock_response):
            with pytest.raises(TypeError, match="Expected TemperatureAttribute, got WrongAttribute"):
                helper.get_temperature()

        communicator.shutdown()
