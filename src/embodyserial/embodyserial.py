"""Communicator module to communicate with an EmBody device over the serial ports.

Allows for both sending messages synchronously and asynchronously, receiving response messages
and subscribing for incoming messages from the device.
"""
import concurrent.futures
import logging
import os
import re
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
from operator import attrgetter
from typing import Optional

import serial
import serial.tools.list_ports
from embodycodec import codec
from embodycodec import crc
from embodycodec import types
from serial.serialutil import SerialBase
from serial.serialutil import SerialException

import embodyserial.exceptions as embodyexceptions
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
            if os.name == "nt":  # sys.platform == 'win32':
                self.__serial.set_buffer_size(rx_size=128 * 1024, tx_size=12800)
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
            self.__reader.stop()
            self.__sender.shutdown()
            if self.__serial.is_open:
                try:
                    self.__serial.reset_input_buffer()
                except Exception as e:
                    logging.debug(f"Failed to reset input buffer: {e}")
                try:
                    self.__serial.reset_output_buffer()
                except Exception as e:
                    logging.debug(f"Failed to reset output buffer: {e}")
                try:
                    self.__serial.close()
                except Exception as e:
                    logging.warn(f"Failed to close port: {e}")

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
        ignore_crc_error=False,
    ) -> str:
        """Download file from device and write to temporary file.

        Raises:
          MissingResponseError if no response.
          CrcError if invalid crc.
        """
        if size == 0:
            return tempfile.NamedTemporaryFile(delete=False).name

        # lock send to prevent sending other messages while downloading
        with self.__sender._send_lock:
            return self.__reader.download_file(
                file_name, size, download_listener, timeout, delay, ignore_crc_error
            )

    def download_file_with_retries(
        self,
        file_name: str,
        file_size: int,
        listener: Optional[FileDownloadListener] = None,
        retries=3,
        timeout_seconds_per_retry=1,
        timeout: int = 300,
        delay: float = 0.0,
    ) -> Optional[str]:
        for retry in range(1, retries + 1):
            try:
                stored_file = self.download_file(
                    file_name, file_size, listener, timeout, delay
                )
                if stored_file:
                    logging.info(f"File {file_name} downloaded to: {stored_file}")
                    return stored_file
                logging.warn(f"Download failed for {file_name} (attempt: {retry})")
                time.sleep(timeout_seconds_per_retry)
                continue
            except Exception as e:
                logging.warn(f"Download failed for {file_name} (attempt: {retry}): {e}")
                time.sleep(timeout_seconds_per_retry)
                continue
        return None

    @staticmethod
    def __find_serial_port() -> str:
        """Find first matching serial port name."""
        all_available_ports = serial.tools.list_ports.comports()
        if not all_available_ports:
            raise SerialException("No available serial ports")

        all_available_ports.sort(key=attrgetter("device"))
        for port in all_available_ports:
            if (
                not re.search("Datek|Aidee", str(port.manufacturer))
                and not re.search("IsenseU|G3|EmBody", str(port.description))
                and sys.platform != "win32"
            ):
                continue

            if EmbodySerial.__port_is_alive(port):
                return port.device
        raise SerialException("No matching serial ports found")

    @staticmethod
    def __port_is_alive(port: SerialBase) -> bool:
        """Check if port has an active embody device."""
        logging.info(f"Checking candidate port: {port}")
        try:
            ser = serial.Serial(port=port.device, baudrate=115200, timeout=1)
            in_waiting = ser.in_waiting
            if in_waiting and in_waiting > 0:
                logging.info(f"Flushing input buffer ({in_waiting} bytes)")
                ser.read(in_waiting)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(codec.Heartbeat().encode())
            expected_response = codec.HeartbeatResponse().encode()
            response = ser.read(len(expected_response))
            logging.debug(
                f"Response: {response.hex()} (expected: {expected_response.hex()})"
            )
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
        self._send_lock = threading.Lock()
        self.__response_event = threading.Event()
        self.__current_response_message: Optional[codec.Message] = None
        self.__send_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="send-worker"
        )

    def shutdown(self) -> None:
        self.__send_executor.shutdown(wait=True, cancel_futures=False)

    def response_message_received(self, msg: codec.Message) -> None:
        """Invoked when response message is received by Message reader.

        Sets the local response message and notifies the waiting sender thread
        """
        logging.debug(f"Response message received: {msg}")
        self.__current_response_message = msg
        self.__response_event.set()

    def send_message(self, msg: codec.Message) -> None:
        self.__send_async(msg)

    def send_message_and_wait_for_response(
        self, msg: codec.Message, timeout: Optional[int] = 30
    ) -> Optional[codec.Message]:
        future = self.__send_async(msg, timeout)
        try:
            return future.result(timeout + 1 if timeout else 1)
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
        with self._send_lock:
            if not self.__serial.is_open:
                return None
            logging.debug(f"Sending message: {msg}, encoded: {msg.encode().hex()}")
            try:
                self.__response_event.clear()
                self.__serial.write(msg.encode())
            except serial.SerialException as e:
                logging.warning(f"Error sending message: {str(e)}", exc_info=False)
                return None
            if wait_for_response_secs and wait_for_response_secs > 0:
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
    ignore_crc_error: bool = False


class _ReaderThread(threading.Thread):
    """Implement a serial port read loop and dispatch incoming messages to subscribers/listeners.

    Calls to close() will close the serial port it is also possible to just
    stop() this thread and continue the serial port instance otherwise.
    """

    def __init__(self, serial_instance: SerialBase) -> None:
        """Initialize thread."""
        super().__init__()
        self.daemon = True
        self.name = "reader"
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
        delay: float = 0.0,
        ignore_crc_error=False,
    ) -> str:
        """Set reader in file mode and read file."""
        if hasattr(self.__serial, "timeout"):
            self.__serial.timeout = 10
        f = _FileDownload(
            file_size=size,
            file_timeout=timeout,
            original_file_name=original_file_name,
            file_download_listener=download_listener,
            file_delay=delay,
            ignore_crc_error=ignore_crc_error,
        )
        self.__f = f
        self.__file_mode = True
        try:
            uart = codec.GetFileUart(types.File(original_file_name))
            logging.debug(f"Sending message: {uart}, encoded: {uart.encode().hex()}")
            self.__serial.write(uart.encode())
            if not self.__file_event.wait(timeout):
                raise embodyexceptions.MissingResponseError(
                    "No file received within timeout"
                )
            if self.__f.file_error:
                raise self.__f.file_error
            if not self.__f.file_name:
                raise embodyexceptions.MissingResponseError("No file received")
            return self.__f.file_name
        except Exception as e:
            raise e
        finally:
            if hasattr(self.__serial, "timeout") and self.__read_timeout:
                self.__serial.timeout = 20
            self.__reset_file_mode()

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
            if self.__serial.is_open:
                self.__serial.cancel_read()
        self.__message_listener_executor.shutdown(wait=True, cancel_futures=False)
        self.__response_message_listener_executor.shutdown(
            wait=True, cancel_futures=False
        )
        self.__file_download_listener_executor.shutdown(wait=True, cancel_futures=False)
        self.join(2)

    def run(self) -> None:
        """Reader loop"""
        if not hasattr(self.__serial, "cancel_read"):
            self.__serial.timeout = 300
        while self.alive and self.__serial.is_open:
            try:
                raw_header = self.__serial.read(3)
                if not raw_header or len(raw_header) < 3:
                    continue
                if self.__file_mode and self.__f:
                    self.__read_file(raw_header, self.__f)
                else:
                    self.__read_protocol_message(raw_header)
            except serial.SerialException as ser:
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                logging.info(f"Serial port is closed (SerialException) {str(ser)}")
                break
            except TypeError:
                # read returned empty buffer
                break
            except OSError as ose:
                logging.info(f"OS Error reading from socket (OSError): {str(ose)}")
                break
            except ValueError as ve:
                logging.info(
                    f"ValueError reading from socket (Probably disconnected): {str(ve)}"
                )
                break
            except Exception as e:
                logging.info(f"Exception reading from socket: {str(e)} - disconnecting")
                break
        self.alive = False
        self.__notify_connection_listeners(connected=False)

    def __read_file(self, first_bytes: bytes, f: _FileDownload) -> None:
        self.__serial.timeout = 0
        remaining_size = f.file_size - len(first_bytes)
        start = time.time()
        last = start
        in_memory_buffer = bytearray()
        in_memory_buffer.extend(first_bytes)
        loop_count = 0
        bytes_to_read = 16 * 1024
        try:
            while remaining_size > 0 and self.__serial.is_open:
                chunk = self.__serial.read(min(bytes_to_read, remaining_size))
                if chunk and len(chunk) > 0:
                    curr_len = len(chunk)
                    in_memory_buffer.extend(chunk)
                    remaining_size -= curr_len
                    now = time.time()
                    # logging.warning(f"Loop {str(loop_count)} time {str(now-start)} chunk {str(curr_len)}", exc_info=False)
                    if now > (last + 0.5):  # Update every 500ms
                        self.__async_notify_file_download_in_progress(
                            f,
                            f.file_size,
                            round(((f.file_size - remaining_size) / f.file_size) * 100),
                            round(
                                ((f.file_size - remaining_size) / 1024) / (now - start)
                            ),
                        )
                        last = now
                else:
                    time.sleep(0.005)
                loop_count += 1
                if f.file_timeout and now - start > f.file_timeout:
                    raise embodyexceptions.TimeoutError(
                        f"Reading file took too long. Read {f.file_size - remaining_size} bytes"
                    )
                if f.file_delay > 0:
                    time.sleep(f.file_delay)
                else:
                    if (
                        time.time() - now > 5
                    ):  # More than 5 seconds since we got anything from unit!
                        raise embodyexceptions.TimeoutError(
                            f"Inter-block timeout!. Read {f.file_size - remaining_size} bytes out of {f.file_size}"
                        )
            self.__serial.timeout = 5
            raw_crc_received = self.__serial.read(2)
            end = time.time()
            if not raw_crc_received or len(raw_crc_received) < 2:
                f.file_error = embodyexceptions.CrcError("Missing/too short crc")
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
                if not f.ignore_crc_error:
                    raise embodyexceptions.CrcError(
                        f"Invalid crc - expected {hex(crc_received)}, received/calculated {hex(calculated_crc)}"
                    )
            tmp = tempfile.NamedTemporaryFile(delete=False)
            tmp.write(in_memory_buffer)
            tmp.flush()
            tmp.close()
            f.file_name = tmp.name
            self.__async_notify_file_download_completed(
                f, round((f.file_size / 1024) / (end - start), 2)
            )
        except embodyexceptions.CrcError as e:
            if not f.ignore_crc_error:
                f.file_error = e
        except Exception as e:
            f.file_error = e
        finally:
            if f.file_error:
                self.__async_notify_file_download_failed(f, f.file_error)
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
        if length > 20480:
            raise ValueError(f"Message length too long: {length}")
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
