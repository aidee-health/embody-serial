"""Communicator module to communicate with an EmBody device over the serial ports.

Allows for both sending messages synchronously and asynchronously, receiving response messages
and subscribing for incoming messages from the device.
"""
import concurrent.futures
import logging
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import serial
import serial.tools.list_ports
from embodycodec import codec
from serial.serialutil import SerialException


class MessageListener:
    """Listener interface for receiving incoming messages"""

    def message_received(self, msg: codec.Message) -> None:
        """Process received message"""
        pass


class ResponseMessageListener:
    """Listener interface for receiving incoming response messages"""

    def response_message_received(self, msg: codec.Message) -> None:
        """Process received response message"""
        pass


class EmbodySerialCommunicator:
    """Main class for setting up communication with an EmBody device.

    If serial_port is not set, the first port identified with proper manufacturer name is used.
    """

    def __init__(
        self,
        serial_port: str = None,
        msg_listener: MessageListener = None,
        rsp_msg_listener: ResponseMessageListener = None,
    ) -> None:
        if serial_port:
            self._port = serial_port
        else:
            self._port = EmbodySerialCommunicator._find_serial_port()
        logging.info(f"Using serial port {self._port}")
        # todo: determine proper port (by input or automatically determine)
        self._connection_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self.__serial = serial.Serial(port=self._port, baudrate=115200)
        self.__connected = True
        self.__response_event = threading.Event()
        self.__current_response_message: codec.Message = None
        # setup executors
        self.__send_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="send-worker"
        )
        self.__message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rcv-worker"
        )
        self.__response_message_listener_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rsp-worker"
        )
        self.__message_listeners = []
        if msg_listener:
            self.__message_listeners.append(msg_listener)
        self.__response_message_listeners = []
        if rsp_msg_listener:
            self.__response_message_listeners.append(rsp_msg_listener)
        reader_thread = ReaderThread(serial_instance=self.__serial, serial_comm=self)
        reader_thread.start()

    def send_message(self, msg: codec.Message) -> None:
        self._send_async(msg, False)

    def send_message_and_wait_for_response(
        self, msg: codec.Message, timeout: int = 30
    ) -> codec.Message:
        future = self._send_async(msg, True)
        try:
            return future.result(timeout)
        except TimeoutError:
            logging.warning(f"No response received for message: {msg}", exc_info=False)
            return None

    def _send_async(
        self, msg: codec.Message, wait_for_response: bool = True
    ) -> concurrent.futures.Future[codec.Message]:
        return self.__send_executor.submit(self._do_send, msg, wait_for_response)

    def _do_send(
        self, msg: codec.Message, wait_for_response: bool = True
    ) -> codec.Message:
        with self._send_lock:
            if not self.__connected:
                return None
            logging.debug(f"Sending message: {msg}, encoded: {msg.encode().hex()}")
            try:
                self.__response_event.clear()
                self.__serial.write(msg.encode())
            except serial.SerialException as e:
                logging.warning(f"Error sending message: {str(e)}", exc_info=False)
                return None
            if wait_for_response:
                if self.__response_event.wait(30):
                    return self.__current_response_message
            return None

    def shutdown(self) -> None:
        # shutdown serial connection
        # shutdown all threads/executors
        with self._connection_lock:
            if not self.__connected:
                return
            self.__connected = False
            self.__send_executor.shutdown(wait=False, cancel_futures=False)
            self.__message_listener_executor.shutdown(wait=False, cancel_futures=False)
            self.__response_message_listener_executor.shutdown(
                wait=False, cancel_futures=False
            )
            self.__serial.close()

    def handle_incoming_message(self, msg: codec.Message) -> None:
        if msg.msg_type < 0x80:
            self._handle_message(msg)
        else:
            self._handle_response_message(msg)

    def _handle_message(self, msg: codec.Message) -> None:
        logging.info(f"New message received: {msg}")
        if len(self.__message_listeners) == 0:
            return
        for listener in self.__message_listeners:
            self.__message_listener_executor.submit(
                EmbodySerialCommunicator._notify_message_listeners, listener, msg
            )

    @staticmethod
    def _notify_message_listeners(
        listener: MessageListener, msg: codec.Message
    ) -> None:
        try:
            listener.message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {str(e)}", exc_info=True)

    def _handle_response_message(self, msg: codec.Message) -> None:
        logging.info(f"New response message received: {msg}")
        self.__current_response_message = msg
        self.__response_event.set()
        if len(self.__response_message_listeners) == 0:
            return
        for listener in self.__response_message_listeners:
            self.__response_message_listener_executor.submit(
                EmbodySerialCommunicator._notify_rsp_message_listeners, listener, msg
            )

    @staticmethod
    def _notify_rsp_message_listeners(
        listener: ResponseMessageListener, msg: codec.Message
    ) -> None:
        try:
            listener.response_message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {str(e)}", exc_info=True)

    def handle_disconnected(self) -> None:
        logging.info("Handle disconnected")
        # todo (Espen - 20220726): consider notifying clients with a connection listener
        self.shutdown()

    @staticmethod
    def _find_serial_port() -> str:
        """Find first matching serial port name."""
        manufacturers = ["Datek", "Aidee"]
        all_available_ports = serial.tools.list_ports.comports()
        if len(all_available_ports) == 0:
            raise SerialException("No available serial ports")
        for port in all_available_ports:
            if not port.manufacturer:
                continue
            if any(manufacturer in port.manufacturer for manufacturer in manufacturers):
                return port.device
        raise SerialException("No matching serial ports found")


class ReaderThread(threading.Thread):
    """Implement a serial port read loop and dispatch incoming messages to subscribers/listeners.

    Calls to close() will close the serial port it is also possible to just
    stop() this thread and continue the serial port instance otherwise.
    """

    def __init__(
        self, serial_instance: serial.Serial, serial_comm: EmbodySerialCommunicator
    ) -> None:
        """Initialize thread."""
        super().__init__()
        self.daemon = True
        self.setName("reader")
        self.serial = serial_instance
        self.communicator = serial_comm
        self.alive = True

    def stop(self) -> None:
        """Stop the reader thread"""
        if not self.alive:
            return
        self.alive = False
        if hasattr(self.serial, "cancel_read"):
            self.serial.cancel_read()
        self.join(2)

    def run(self) -> None:
        """Reader loop"""
        if not hasattr(self.serial, "cancel_read"):
            self.serial.timeout = 300
        while self.alive and self.serial.is_open:
            try:
                raw_header = self.serial.read(3)
                logging.debug(f"RECEIVE: Received header {raw_header.hex()}")
                (
                    msg_type,
                    length,
                ) = struct.unpack(">BH", raw_header)
                logging.debug(
                    f"RECEIVE: Received msg type: {msg_type}, length: {length}"
                )
                raw_message = raw_header + self.serial.read(size=length - 3)
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
                            self.communicator.handle_incoming_message(msg)
                    except Exception as e:
                        logging.warning(
                            f"Error processing raw message {raw_message}, error: {str(e)}",
                            exc_info=True,
                        )
                        continue
        self.alive = False
        self.communicator.handle_disconnected()


if __name__ == "__main__":
    """Main method for demo and testing"""
    import time

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
    communicator = EmbodySerialCommunicator(
        msg_listener=DemoMessageListener(), rsp_msg_listener=DemoMessageListener()
    )
    response = communicator.send_message_and_wait_for_response(codec.ListFiles())
    logging.info(f"Response received directly: {response}")
    time.sleep(10)
    communicator.shutdown()
