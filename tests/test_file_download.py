"""Test file download functionality for small files."""

import struct
import threading
import time

import pytest
from embodycodec import crc

from embodyserial import embodyserial as serialcomm
from tests.conftest import DummySerial


def _create_file_data_with_crc(file_content: bytes) -> bytes:
    """Create file data with appended CRC."""
    file_crc = struct.pack(">H", crc.crc16(file_content))
    return file_content + file_crc


@pytest.mark.api
class TestSmallFileDownload:
    """Test small file download edge cases."""

    def test_1_byte_file_download(self):
        """Verify 1-byte file downloads correctly (Bug #2 fix)."""
        # For 1-byte file: first_bytes will contain [file_byte, crc_byte_1, crc_byte_2]
        file_content = b"\x42"
        full_data = _create_file_data_with_crc(file_content)

        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        def set_data_after_delay():
            time.sleep(0.1)
            serial.set_read_data(full_data)

        threading.Thread(target=set_data_after_delay, daemon=True).start()

        result = communicator.download_file(file_name="tiny.bin", size=1, timeout=5)

        assert result is not None
        with open(result, "rb") as f:
            downloaded_content = f.read()
        assert downloaded_content == file_content
        communicator.shutdown()

    def test_2_byte_file_download(self):
        """Verify 2-byte file downloads correctly (Bug #2 fix)."""
        # For 2-byte file: first_bytes will contain [file_byte_1, file_byte_2, crc_byte_1]
        # Need to read 1 more byte for crc_byte_2
        file_content = b"\x42\x43"
        full_data = _create_file_data_with_crc(file_content)

        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        def set_data_after_delay():
            time.sleep(0.1)
            serial.set_read_data(full_data)

        threading.Thread(target=set_data_after_delay, daemon=True).start()

        result = communicator.download_file(file_name="tiny2.bin", size=2, timeout=5)

        assert result is not None
        with open(result, "rb") as f:
            downloaded_content = f.read()
        assert downloaded_content == file_content
        communicator.shutdown()

    def test_3_byte_file_boundary(self):
        """Verify 3-byte file (boundary case) downloads correctly."""
        # For 3-byte file: first_bytes contains all file data, CRC read separately
        file_content = b"\x42\x43\x44"
        full_data = _create_file_data_with_crc(file_content)

        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        def set_data_after_delay():
            time.sleep(0.1)
            serial.set_read_data(full_data)

        threading.Thread(target=set_data_after_delay, daemon=True).start()

        result = communicator.download_file(file_name="boundary.bin", size=3, timeout=5)

        assert result is not None
        with open(result, "rb") as f:
            downloaded_content = f.read()
        assert downloaded_content == file_content
        communicator.shutdown()

    def test_60_byte_file_download(self):
        """Verify 60-byte file downloads without timeout (Bug #1 scenario)."""
        file_content = bytes(range(60))
        full_data = _create_file_data_with_crc(file_content)

        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        def set_data_after_delay():
            time.sleep(0.1)
            serial.set_read_data(full_data)

        threading.Thread(target=set_data_after_delay, daemon=True).start()

        result = communicator.download_file(file_name="small.bin", size=60, timeout=5)

        assert result is not None
        with open(result, "rb") as f:
            downloaded_content = f.read()
        assert downloaded_content == file_content
        communicator.shutdown()

    def test_100_byte_file_download(self):
        """Verify 100-byte file downloads correctly."""
        file_content = bytes(range(100))
        full_data = _create_file_data_with_crc(file_content)

        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        def set_data_after_delay():
            time.sleep(0.1)
            serial.set_read_data(full_data)

        threading.Thread(target=set_data_after_delay, daemon=True).start()

        result = communicator.download_file(file_name="medium.bin", size=100, timeout=5)

        assert result is not None
        with open(result, "rb") as f:
            downloaded_content = f.read()
        assert downloaded_content == file_content
        communicator.shutdown()
