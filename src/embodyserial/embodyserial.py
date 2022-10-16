"""Communicator module to communicate with an EmBody device over the serial ports.

Allows for both sending messages synchronously and asynchronously, receiving response messages
and subscribing for incoming messages from the device.
"""
import concurrent.futures
import logging
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import serial
import serial.tools.list_ports
from embodycodec import codec
from serial.serialutil import SerialBase
from serial.serialutil import SerialException

from embodyserial.listeners import ConnectionListener
from embodyserial.listeners import MessageListener
from embodyserial.listeners import ResponseMessageListener


class EmbodySerial(ConnectionListener):
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

    def send_message(self, msg: codec.Message) -> None:
        self.__sender.send_message(msg)

    def send_message_and_wait_for_response(
        self, msg: codec.Message, timeout: int = 30
    ) -> Optional[codec.Message]:
        return self.__sender.send_message_and_wait_for_response(msg, timeout)

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

    @staticmethod
    def __find_serial_port() -> str:
        """Find first matching serial port name."""
        manufacturers = ["Datek", "Aidee"]
        descriptions = ["IsenseU", "G3"]
        all_available_ports = serial.tools.list_ports.comports()
        if len(all_available_ports) == 0:
            raise SerialException("No available serial ports")
        for port in all_available_ports:
            for description in descriptions:
                if description in port.description:
                    return port.device
            if not port.manufacturer:
                continue
            if any(manufacturer in port.manufacturer for manufacturer in manufacturers):
                return port.device
        raise SerialException("No matching serial ports found")


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
        self, msg: codec.Message, timeout: int = 30
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
        self.__message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rcv-worker"
        )
        self.__response_message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rsp-worker"
        )
        self.__message_listeners: list[MessageListener] = []
        self.__response_message_listeners: list[ResponseMessageListener] = []
        self.__connection_listeners: list[ConnectionListener] = []
        self.alive = True

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
        self.join(2)

    def run(self) -> None:
        """Reader loop"""
        if not hasattr(self.__serial, "cancel_read"):
            self.__serial.timeout = 300
        while self.alive and self.__serial.is_open:
            try:
                raw_header = self.__serial.read(3)
                logging.debug(f"RECEIVE: Received header {raw_header.hex()}")
                (
                    msg_type,
                    length,
                ) = struct.unpack(">BH", raw_header)
                logging.debug(
                    f"RECEIVE: Received msg type: {msg_type}, length: {length}"
                )
                raw_message = raw_header + self.__serial.read(size=length - 3)
                logging.debug(f"RECEIVE: Received raw msg: {raw_message.hex()}")
            except serial.SerialException:
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                logging.info("Serial port is closed (SerialException)", exc_info=False)
                break
            except OSError:
                logging.warning(
                    "OS Error reading from socket (OSError)", exc_info=False
                )
                break
            else:
                if raw_message:
                    try:
                        msg = codec.decode(raw_message)
                        if msg:
                            self.__handle_incoming_message(msg)
                    except Exception as e:
                        logging.warning(
                            f"Error processing raw message {raw_message}, error: {str(e)}",
                            exc_info=True,
                        )
                        continue
        self.alive = False
        self.__notify_connection_listeners(connected=False)

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

    def add_connection_listener(self, listener: ConnectionListener) -> None:
        self.__connection_listeners.append(listener)


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
    response = communicator.send_message_and_wait_for_response(codec.ListFiles())
    logging.info(f"Response received directly: {response}")
    communicator.shutdown()
