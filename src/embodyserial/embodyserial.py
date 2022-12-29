"""Communicator module to communicate with an EmBody device over the serial ports.

Allows for both sending messages synchronously and asynchronously, receiving response messages
and subscribing for incoming messages from the device.
"""
import concurrent.futures
import logging
import struct
import sys
import tempfile
import threading
import time
from abc import ABC
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError
from dataclasses import dataclass
from typing import Optional

import serial
import serial.tools.list_ports
from embodycodec import codec
from embodycodec import crc
from embodycodec import types
from serial.serialutil import SerialBase
from serial.serialutil import SerialException
from serial.tools import list_ports_common

from embodyserial.exceptions import CrcError
from embodyserial.exceptions import MissingResponseError
from embodyserial.listeners import ConnectionListener
from embodyserial.listeners import FileDownloadListener
from embodyserial.listeners import MessageListener
from embodyserial.listeners import ResponseMessageListener


class EmbodySender(ABC):
    """Listener interface for being notified of incoming messages."""

    @abstractmethod
    def send_async(self, msg: codec.Message) -> None:
        """Send a message. do not wait for a response"""
        pass

    @abstractmethod
    def send(
        self, msg: codec.Message, timeout: Optional[int] = 30
    ) -> Optional[codec.Message]:
        """Send a message. wait for a response or timeout"""
        return None


class EmbodySerial(ConnectionListener, EmbodySender):
    """Main class for setting up communication with an EmBody device.

    If serial_port is not set, the first port identified with proper manufacturer name is used.
    """

    def __init__(
        self,
        serial_port: Optional[str] = None,
        msg_listener: Optional[MessageListener] = None,
        serial_instance: Optional[SerialBase] = None,
    ) -> None:
        if serial_port:
            self.__port = serial_port
            logging.info(f"Using serial port {self.__port}")
        elif not serial_instance:
            self.__port = EmbodySerial.__find_serial_port()
            logging.info(f"Using serial port {self.__port}")
        self.__shutdown_lock = threading.Lock()
        if serial_instance:
            self.__serial = serial_instance
        else:
            self.__serial = serial.Serial(port=self.__port, baudrate=115200)
        self.__connected = True
        self.__sender = _MessageSender(self.__serial)
        self.__reader = _ReaderThread(serial_instance=self.__serial)
        self.__reader.add_connection_listener(self)
        self.__reader.add_response_message_listener(self.__sender)
        if msg_listener:
            self.__reader.add_message_listener(msg_listener)
        self.__reader.start()

    def send_async(self, msg: codec.Message) -> None:
        """Send a message. do not wait for a response"""
        self.__sender.send_message(msg)

    def send(
        self, msg: codec.Message, timeout: Optional[int] = 30
    ) -> Optional[codec.Message]:
        """Send a message. Wait for a response or timeout"""
        return self.__sender.send_message_and_wait_for_response(msg, timeout)

    def add_message_listener(self, listener: MessageListener) -> None:
        """Register message listener."""
        self.__reader.add_message_listener(listener)

    def shutdown(self) -> None:
        """Shutdown serial connection and all threads/executors."""
        with self.__shutdown_lock:
            if not self.__connected:
                return
            self.__connected = False
            self.__serial.close()
            self.__reader.stop()
            self.__sender.shutdown()

    def on_connected(self, connected: bool) -> None:
        """Implement connection listener interface and handle disconnect events"""
        logging.debug(f"Connection event: {connected}")
        if not connected:
            self.shutdown()

    def download_file(
        self,
        file_name: str,
        size: int,
        download_listener: Optional[FileDownloadListener] = None,
        timeout: int = 300,
        delay: float = 0.0,
    ) -> str:
        """Download file from device and write to temporary file.

        Raises:
          MissingResponseError if no response.
          CrcError if invalid crc.
        """
        if size == 0:
            return tempfile.NamedTemporaryFile(delete=False).name
        self.send_async(codec.GetFileUart(types.File(file_name)))
        return self.__reader.download_file(
            file_name, size, download_listener, timeout, delay
        )

    @staticmethod
    def __find_serial_port() -> str:
        """Find first matching serial port name."""
        manufacturers = ["Datek", "Aidee"]
        descriptions = ["IsenseU", "G3", "EmBody"]
        all_available_ports = serial.tools.list_ports.comports()
        if len(all_available_ports) == 0:
            raise SerialException("No available serial ports")
        for port in all_available_ports:
            candidate: Optional[list_ports_common.ListPortInfo] = None
            if any(description in port.description for description in descriptions):
                candidate = port
            elif port.manufacturer and any(
                manufacturer in port.manufacturer for manufacturer in manufacturers
            ):
                candidate = port
            elif sys.platform == "win32":
                candidate = port
            if candidate and EmbodySerial.__port_is_alive(port):
                return port.device
        raise SerialException("No matching serial ports found")

    @staticmethod
    def __port_is_alive(port: SerialBase) -> bool:
        """Check if port has an active embody device."""
        logging.info(f"Checking candidate port: {port}")
        try:
            ser = serial.Serial(port=port.device, baudrate=115200, timeout=3)
            ser.write(codec.Heartbeat().encode())
            expected_response = codec.HeartbeatResponse().encode()
            response = ser.read(len(expected_response))
            ser.close()
            return response == expected_response
        except Exception as e:
            logging.info(f"Exception raised for port check: {e}")
            return False


class _MessageSender(ResponseMessageListener):
    """All send functionality is handled by this class.

    This includes thread safety, async handling and windowing
    """

    def __init__(self, serial_instance: SerialBase) -> None:
        self.__serial = serial_instance
        self.__send_lock = threading.Lock()
        self.__response_event = threading.Event()
        self.__current_response_message: Optional[codec.Message] = None
        self.__send_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="send-worker"
        )

    def shutdown(self) -> None:
        self.__send_executor.shutdown(wait=False, cancel_futures=False)

    def response_message_received(self, msg: codec.Message) -> None:
        """Invoked when response message is received by Message reader.

        Sets the local response message and notifies the waiting sender thread
        """
        logging.debug(f"Response message received: {msg}")
        self.__current_response_message = msg
        self.__response_event.set()

    def send_message(self, msg: codec.Message) -> None:
        self.__send_async(msg, False)

    def send_message_and_wait_for_response(
        self, msg: codec.Message, timeout: Optional[int] = 30
    ) -> Optional[codec.Message]:
        future = self.__send_async(msg, timeout)
        try:
            return future.result(timeout)
        except TimeoutError:
            logging.warning(
                f"No response received for message within timeout: {msg}",
                exc_info=False,
            )
            return None

    def __send_async(
        self, msg: codec.Message, wait_for_response_secs: Optional[int] = None
    ) -> concurrent.futures.Future[Optional[codec.Message]]:
        return self.__send_executor.submit(self.__do_send, msg, wait_for_response_secs)

    def __do_send(
        self, msg: codec.Message, wait_for_response_secs: Optional[int] = None
    ) -> Optional[codec.Message]:
        with self.__send_lock:
            if not self.__serial.is_open:
                return None
            logging.debug(f"Sending message: {msg}, encoded: {msg.encode().hex()}")
            try:
                self.__response_event.clear()
                self.__serial.write(msg.encode())
            except serial.SerialException as e:
                logging.warning(f"Error sending message: {str(e)}", exc_info=False)
                return None
            if wait_for_response_secs:
                if self.__response_event.wait(wait_for_response_secs):
                    return self.__current_response_message
            return None


@dataclass
class _FileDownload:
    file_size: int = -1
    file_timeout: Optional[int] = None
    original_file_name: Optional[str] = None
    file_name: Optional[str] = None
    file_error: Optional[Exception] = None
    file_download_listener: Optional[FileDownloadListener] = None
    file_delay: float = 0.0


class _ReaderThread(threading.Thread):
    """Implement a serial port read loop and dispatch incoming messages to subscribers/listeners.

    Calls to close() will close the serial port it is also possible to just
    stop() this thread and continue the serial port instance otherwise.
    """

    def __init__(self, serial_instance: SerialBase) -> None:
        """Initialize thread."""
        super().__init__()
        self.daemon = True
        self.setName("reader")
        self.__serial = serial_instance
        self.__read_timeout: Optional[int] = None
        if hasattr(self.__serial, "timeout"):
            self.__read_timeout = serial_instance.timeout

        self.__message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rcv-worker"
        )
        self.__response_message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rsp-worker"
        )
        self.__file_download_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dwnld-worker"
        )
        self.__message_listeners: list[MessageListener] = []
        self.__response_message_listeners: list[ResponseMessageListener] = []
        self.__connection_listeners: list[ConnectionListener] = []
        self.__file_mode = False
        self.__f: Optional[_FileDownload] = None
        self.__file_event = threading.Event()
        self.alive = True

    def download_file(
        self,
        original_file_name: str,
        size: int,
        download_listener: Optional[FileDownloadListener] = None,
        timeout: int = 300,
        delay=0.0,
    ) -> str:
        """Set reader in file mode and read file."""
        if hasattr(self.__serial, "timeout"):
            self.__serial.timeout = 10
        self.__reset_file_mode()
        f = _FileDownload(
            file_size=size,
            file_timeout=timeout,
            original_file_name=original_file_name,
            file_download_listener=download_listener,
            file_delay=delay,
        )
        self.__f = f
        self.__file_mode = True
        try:
            if not self.__file_event.wait(timeout):
                raise MissingResponseError("No file received within timeout")
            if self.__f.file_error:
                raise self.__f.file_error
            if not self.__f.file_name:
                raise MissingResponseError("No file received")
            return self.__f.file_name
        except Exception as e:
            self.__async_notify_file_download_failed(f, e)
            raise e
        finally:
            self.__reset_file_mode()
            if hasattr(self.__serial, "timeout") and self.__read_timeout:
                self.__serial.timeout = self.__read_timeout

    def __reset_file_mode(self) -> None:
        self.__file_event.clear()
        self.__file_mode = False
        self.__f = None

    def stop(self) -> None:
        """Stop the reader thread"""
        if not self.alive:
            return
        self.alive = False
        if hasattr(self.__serial, "cancel_read"):
            self.__serial.cancel_read()
        self.__message_listener_executor.shutdown(wait=False, cancel_futures=False)
        self.__response_message_listener_executor.shutdown(
            wait=False, cancel_futures=False
        )
        self.__file_download_listener_executor.shutdown(
            wait=False, cancel_futures=False
        )
        self.join(2)

    def run(self) -> None:
        """Reader loop"""
        if not hasattr(self.__serial, "cancel_read"):
            self.__serial.timeout = 300
        while self.alive and self.__serial.is_open:
            try:
                raw_header = self.__serial.read(3)
                if not raw_header or len(raw_header) < 3:
                    logging.info("Interrupted. Exiting reader thread.")
                    break
                if self.__file_mode and self.__f:
                    self.__read_file(raw_header, self.__f)
                else:
                    self.__read_protocol_message(raw_header)
            except serial.SerialException:
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                logging.info("Serial port is closed (SerialException)")
                break
            except OSError:
                logging.info("OS Error reading from socket (OSError)")
                break
        self.alive = False
        self.__notify_connection_listeners(connected=False)

    def __read_file(self, first_bytes: bytes, f: _FileDownload) -> None:
        buffer_size = 2048
        remaining_size = f.file_size - len(first_bytes)
        start = time.time()
        in_memory_buffer = bytearray(first_bytes)
        loop_count = 0
        try:
            while remaining_size > 0 and self.__serial.is_open:
                chunk = self.__serial.read(min(buffer_size, remaining_size))
                if not chunk:
                    raise MissingResponseError("File download failed")
                in_memory_buffer.extend(chunk)
                remaining_size -= len(chunk)
                now = time.time()
                if loop_count % 20 == 0:
                    self.__async_notify_file_download_in_progress(
                        f,
                        f.file_size,
                        round(((f.file_size - remaining_size) / f.file_size) * 100),
                        round(((f.file_size - remaining_size) / 1024) / (now - start)),
                    )
                loop_count += 1
                if f.file_timeout and now - start > f.file_timeout:
                    raise TimeoutError(
                        f"Reading file took too long. Read {f.file_size - remaining_size} bytes"
                    )
                if f.file_delay:
                    time.sleep(f.file_delay)
            raw_crc_received = self.__serial.read(2)
            end = time.time()
            self.__async_notify_file_download_in_progress(
                f,
                f.file_size,
                100,
                round((f.file_size / 1024) / (end - start), 2),
            )
            logging.debug(
                f"Read {round(f.file_size/1024,2)}KB in {end-start} secs "
                f"- {round((f.file_size/1024)/(end-start),2)}KB/s"
            )
            (crc_received,) = struct.unpack(">H", raw_crc_received)
            calculated_crc = crc.crc16(data=in_memory_buffer)
            if not crc_received == calculated_crc:
                f.file_error = CrcError(
                    f"Invalid crc - expected {hex(crc_received)}, received/calculated {hex(calculated_crc)}"
                )
                self.__async_notify_file_download_failed(f, f.file_error)
                return
            tmp = tempfile.NamedTemporaryFile(delete=False)
            tmp.write(in_memory_buffer)
            tmp.flush()
            tmp.close()
            f.file_name = tmp.name
            self.__async_notify_file_download_completed(
                f, round((f.file_size / 1024) / (end - start), 2)
            )
        except Exception as e:
            f.file_error = e
            self.__async_notify_file_download_failed(f, e)
        finally:
            self.__file_event.set()

    def __async_notify_file_download_in_progress(
        self, f: _FileDownload, size: int, progress: float, kbps: float
    ):
        if f.file_download_listener and f.original_file_name:
            self.__file_download_listener_executor.submit(
                _ReaderThread.__notify_file_download_progress,
                f.file_download_listener,
                f.original_file_name,
                size,
                progress,
                kbps,
            )

    def __async_notify_file_download_completed(self, f: _FileDownload, kbps: float):
        if f.file_download_listener and f.original_file_name and f.file_name:
            self.__file_download_listener_executor.submit(
                _ReaderThread.__notify_file_download_complete,
                f.file_download_listener,
                f.original_file_name,
                f.file_name,
                kbps,
            )

    def __async_notify_file_download_failed(self, f: _FileDownload, error: Exception):
        if f.file_download_listener and f.original_file_name:
            self.__file_download_listener_executor.submit(
                _ReaderThread.__notify_file_download_failed,
                f.file_download_listener,
                f.original_file_name,
                error,
            )

    def __read_protocol_message(self, raw_header: bytes) -> None:
        """Read next message from input."""
        logging.debug(f"RECEIVE: Received header {raw_header.hex()}")
        msg_type, length = struct.unpack(">BH", raw_header)
        logging.debug(f"RECEIVE: Received msg type: {msg_type}, length: {length}")
        remaining_length = length - 3
        raw_message = raw_header
        while remaining_length > 0:
            raw_message += self.__serial.read(size=min(remaining_length, 1024))
            remaining_length -= 1024
            time.sleep(0.001)
        if raw_message:
            logging.debug(
                f"RECEIVE: Received raw msg: {raw_message.hex() if len(raw_message) <= 1024 else raw_message[0:1023].hex()}"
            )
            try:
                msg = codec.decode(raw_message)
                if msg:
                    self.__handle_incoming_message(msg)
            except Exception as e:
                logging.warning(
                    f"Error processing protocol message, error: {str(e)}",
                    exc_info=True,
                )

    def __handle_incoming_message(self, msg: codec.Message) -> None:
        if msg.msg_type < 0x80:
            self.__handle_message(msg)
        else:
            self.__handle_response_message(msg)

    def __handle_message(self, msg: codec.Message) -> None:
        logging.debug(f"Handling new message: {msg}")
        if len(self.__message_listeners) == 0:
            return
        for listener in self.__message_listeners:
            self.__message_listener_executor.submit(
                _ReaderThread.__notify_message_listener, listener, msg
            )

    @staticmethod
    def __notify_message_listener(
        listener: MessageListener, msg: codec.Message
    ) -> None:
        try:
            listener.message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {str(e)}", exc_info=True)

    def add_message_listener(self, listener: MessageListener) -> None:
        self.__message_listeners.append(listener)

    def __handle_response_message(self, msg: codec.Message) -> None:
        logging.debug(f"Handling new response message: {msg}")
        if len(self.__response_message_listeners) == 0:
            return
        for listener in self.__response_message_listeners:
            self.__response_message_listener_executor.submit(
                _ReaderThread.__notify_rsp_message_listener, listener, msg
            )

    @staticmethod
    def __notify_rsp_message_listener(
        listener: ResponseMessageListener, msg: codec.Message
    ) -> None:
        try:
            listener.response_message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {str(e)}", exc_info=True)

    def add_response_message_listener(self, listener: ResponseMessageListener) -> None:
        self.__response_message_listeners.append(listener)

    def add_connection_listener(self, listener: ConnectionListener) -> None:
        self.__connection_listeners.append(listener)

    def __notify_connection_listeners(self, connected: bool) -> None:
        if len(self.__connection_listeners) == 0:
            return
        for listener in self.__connection_listeners:
            _ReaderThread.__notify_connection_listener(listener, connected)

    @staticmethod
    def __notify_connection_listener(
        listener: ConnectionListener, connected: bool
    ) -> None:
        try:
            listener.on_connected(connected)
        except Exception as e:
            logging.warning(
                f"Error notifying connection listener: {str(e)}", exc_info=True
            )

    @staticmethod
    def __notify_file_download_progress(
        listener: FileDownloadListener,
        original_file_name: str,
        size: int,
        progress: float,
        kbps: float,
    ) -> None:
        try:
            listener.on_file_download_progress(original_file_name, size, progress, kbps)
        except Exception as e:
            logging.warning(
                f"Error notifying file download listener: {str(e)}", exc_info=True
            )

    @staticmethod
    def __notify_file_download_complete(
        listener: FileDownloadListener, original_file_name: str, path: str, kbps: float
    ) -> None:
        try:
            listener.on_file_download_complete(original_file_name, path, kbps)
        except Exception as e:
            logging.warning(
                f"Error notifying file download listener: {str(e)}", exc_info=True
            )

    @staticmethod
    def __notify_file_download_failed(
        listener: FileDownloadListener, original_file_name: str, error: Exception
    ) -> None:
        try:
            listener.on_file_download_failed(original_file_name, error)
        except Exception as e:
            logging.warning(
                f"Error notifying file download listener: {str(e)}", exc_info=True
            )


if __name__ == "__main__":
    """Main method for demo and testing"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(thread)d/%(threadName)s] %(message)s",
    )

    class DemoMessageListener(MessageListener, ResponseMessageListener):
        """Implement listener callback methods"""

        def message_received(self, msg: codec.Message):
            logging.info(f"Message received: {msg}")

        def response_message_received(self, msg: codec.Message):
            logging.info(f"Response message received: {msg}")

    logging.info("Setting up communicator")
    communicator = EmbodySerial(msg_listener=DemoMessageListener())
    response = communicator.send(codec.ListFiles())
    logging.info(f"Response received directly: {response}")
    communicator.shutdown()
