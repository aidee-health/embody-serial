import logging
import serial
import struct
from concurrent.futures import ThreadPoolExecutor
import threading
from embodycodec import codec, attributes, types

# TODO: Use single ThreadPoolExecutors: https://superfastpython.com/threadpoolexecutor-in-python
# for sending and all listener callbacks (max_workers=1)
# classes:
# interfaces: MessageListener, MessageResponseListener, ConnectionListener
# use a latch to handle response messages from receiver thread
# use a thread for receiving messages (package in a SerialReader) - handle IO-errors and shutdown
# dynamically add/remove listeners
# consider having a connection worker that handles reconnection (ie. if cable is unplugged/plugged)
# add logging
# Move message handling to reader class, and add communicator as listener instead. Use a latch to handle send/receive


class MessageListener:
    """Listener interface for receiving incoming messages"""

    def message_received(self, msg: codec.Message):
        """Process received message"""
        pass


class ResponseMessageListener:
    """Listener interface for receiving incoming response messages"""

    def response_message_received(self, msg: codec.Message):
        """Process received response message"""
        pass


class EmbodySerialCommunicator:

    def __init__(self, serial_port: str, msg_listener: MessageListener, rsp_msg_listener: ResponseMessageListener):
        # todo: determine proper port (by input or automatically determine)
        self._lock = threading.Lock()
        self.__serial = serial.Serial(port=serial_port, baudrate=115200)
        self.__connected = True
        # setup executors
        self.__send_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="send-worker")
        self.__message_listener_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rcv-worker")
        self.__response_message_listener_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rsp-worker")
        self.__message_listeners = []
        if msg_listener:
            self.__message_listeners.append(msg_listener)
        self.__response_message_listeners = []
        if rsp_msg_listener:
            self.__response_message_listeners.append(rsp_msg_listener)
        reader_thread = ReaderThread(serial_instance=self.__serial, serial_comm=self)
        reader_thread.start()

    def send_message(self, msg: codec.Message):
        # TODO: Submit to send worker
        if not self.__connected:
            return
        logging.debug(f"Sending message: {msg}, encoded: {msg.encode().hex()}")
        self.__serial.write(msg.encode())

    def send_message_and_wait_for_response(self):
        # TODO: use future, handle exceptions as well
        return

    def shutdown(self):
        # shutdown serial connection
        # shutdown all threads/executors
        with self._lock:
            if not self.__connected:
                return
            self.__connected = False
            self.__send_executor.shutdown(wait=False, cancel_futures=False)
            self.__message_listener_executor.shutdown(wait=False, cancel_futures=False)
            self.__response_message_listener_executor.shutdown(wait=False, cancel_futures=False)
            self.__serial.close()
        return

    def handle_incoming_message(self, msg: codec.Message):
        if msg.msg_type < 0x80:
            self._handle_message(msg)
        else:
            self._handle_response_message(msg)

    def _handle_message(self, msg: codec.Message):
        logging.info(f"New message received: {msg}")
        if len(self.__message_listeners) == 0:
            return
        for listener in self.__message_listeners:
            self.__message_listener_executor.submit(EmbodySerialCommunicator._notify_message_listeners, listener, msg)

    @staticmethod
    def _notify_message_listeners(listener: MessageListener, msg: codec.Message):
        try:
            listener.message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {e.message}", exc_info=True)

    def _handle_response_message(self, msg: codec.Message):
        logging.info(f"New response message received: {msg}")
        if len(self.__response_message_listeners) == 0:
            return
        for listener in self.__response_message_listeners:
            self.__response_message_listener_executor.submit(EmbodySerialCommunicator._notify_rsp_message_listeners,
                                                             listener, msg)

    @staticmethod
    def _notify_rsp_message_listeners(listener: ResponseMessageListener, msg: codec.Message):
        try:
            listener.response_message_received(msg)
        except Exception as e:
            logging.warning(f"Error notifying listener: {e.message}", exc_info=True)

    def handle_disconnected(self, error: Exception):
        logging.info(f"Handle disconnected")
        # todo (Espen - 20220726): consider notifying clients with a connection listener
        self.shutdown()


class ReaderThread(threading.Thread):
    """\
    Implement a serial port read loop and dispatch incoming messages to subscribers/listeners.
    Calls to close() will close the serial port it is also possible to just
    stop() this thread and continue the serial port instance otherwise.
    """

    def __init__(self, serial_instance: serial.Serial, serial_comm: EmbodySerialCommunicator):
        """Initialize thread."""
        super(ReaderThread, self).__init__()
        self.daemon = True
        self.setName("reader")
        self.serial = serial_instance
        self.communicator = serial_comm
        self.alive = True

    def stop(self):
        """Stop the reader thread"""
        if not self.alive:
            return
        self.alive = False
        if hasattr(self.serial, 'cancel_read'):
            self.serial.cancel_read()
        self.join(2)

    def run(self):
        """Reader loop"""
        if not hasattr(self.serial, 'cancel_read'):
            self.serial.timeout = 300
        error = None
        while self.alive and self.serial.is_open:
            try:
                # read all that is there or wait for one byte (blocking)
                raw_header = self.serial.read(3)
                logging.debug(f"RECEIVE: Received header {raw_header.hex()}")
                msg_type, length, = struct.unpack(">BH", raw_header)
                logging.debug(f"RECEIVE: Received msg type: {msg_type}, length: {length}")
                raw_message = raw_header + self.serial.read(size=length - 3)
                logging.debug(f"RECEIVE: Received raw msg: {raw_message.hex()}")
            except serial.SerialException as e:
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                logging.warning(f"Error reading from socket", exc_info=False)
                error = e
                break
            except OSError as ose:
                logging.warning(f"Error reading from socket", exc_info=False)
                break
            else:
                if raw_message:
                    try:
                        msg = codec.decode(raw_message)
                        if msg:
                            self.communicator.handle_incoming_message(msg)
                    except Exception as e:
                        logging.warning(f"Error processing raw message {raw_message}, error: {e.message}",
                                        exc_info=True)
                        continue
        self.alive = False
        self.communicator.handle_disconnected(error)


if __name__ == "__main__":
    """Main method for demo and testing"""
    import time

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(thread)d/%(threadName)s] %(message)s")

    class DemoMessageListener(MessageListener, ResponseMessageListener):

        def message_received(self, msg: codec.Message):
            logging.info(f"Message received: {msg}")

        def response_message_received(self, msg: codec.Message):
            logging.info(f"Response message received: {msg}")

    logging.info("Setting up communicator")
    communicator = EmbodySerialCommunicator(serial_port="/dev/tty.usbmodem3101", msg_listener=DemoMessageListener(),
                                            rsp_msg_listener=DemoMessageListener())
    communicator.send_message(codec.ListFiles())
    time.sleep(30)
    communicator.shutdown()
