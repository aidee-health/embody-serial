"""Test concurrent callback processing with max_workers=3."""

import threading
import time
from unittest.mock import patch

from embodycodec import codec

from embodyserial import embodyserial as serialcomm
from embodyserial.listeners import MessageListener, ResponseMessageListener
from tests.test_embodyserial import DummySerial


class TestConcurrentCallbacks:
    """Test that callbacks can run concurrently without deadlock."""

    def test_message_callbacks_run_serially(self):
        """Verify message callbacks execute serially (single worker)."""
        serial = DummySerial()

        execution_times = []
        lock = threading.Lock()

        class SlowListener(MessageListener):
            def __init__(self, listener_id):
                self.id = listener_id

            def message_received(self, msg: codec.Message) -> None:
                with lock:
                    execution_times.append((self.id, "start", time.time()))

                time.sleep(0.05)  # Simulate processing

                with lock:
                    execution_times.append((self.id, "end", time.time()))

        # Add three listeners
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)
        listeners = [SlowListener(i) for i in range(3)]
        for listener in listeners:
            communicator.add_message_listener(listener)

        # Send one message - all three listeners will be called
        reader = communicator._EmbodySerial__reader
        reader._ReaderThread__handle_message(codec.Heartbeat())

        # Wait for all callbacks to complete
        time.sleep(0.3)

        # Verify all three ran
        start_events = [(id, t) for id, event, t in execution_times if event == "start"]
        end_events = [(id, t) for id, event, t in execution_times if event == "end"]

        assert len(start_events) == 3
        assert len(end_events) == 3

        # Sort events by timestamp to ensure correct order for serial execution check
        start_events_sorted = sorted(start_events, key=lambda x: x[1])
        end_events_sorted = sorted(end_events, key=lambda x: x[1])

        # With serial execution (max_workers=1), callbacks should NOT overlap
        # Each callback should end before the next starts
        for i in range(len(end_events_sorted) - 1):
            assert end_events_sorted[i][1] <= start_events_sorted[i + 1][1], (
                "Callbacks should execute serially with max_workers=1"
            )

        communicator.shutdown()

    def test_callback_can_trigger_send_without_deadlock(self):
        """Verify callbacks can send messages without causing deadlock."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        send_completed = threading.Event()

        class SendingListener(MessageListener):
            def message_received(self, msg: codec.Message) -> None:
                # Callback tries to send a message
                communicator.send(codec.Heartbeat(), timeout=1)
                send_completed.set()

        communicator.add_message_listener(SendingListener())

        # Trigger callback that will attempt to send
        reader = communicator._EmbodySerial__reader
        reader._ReaderThread__handle_message(codec.Heartbeat())

        # Should complete without deadlock
        assert send_completed.wait(timeout=2)

        communicator.shutdown()

    def test_response_callback_doesnt_block_message_callbacks(self):
        """Verify response callbacks don't block message callbacks."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        message_received = threading.Event()
        response_received = threading.Event()

        class TestMessageListener(MessageListener):
            def message_received(self, msg: codec.Message) -> None:
                time.sleep(0.1)  # Simulate processing
                message_received.set()

        class TestResponseListener(ResponseMessageListener):
            def response_message_received(self, msg: codec.Message) -> None:
                time.sleep(0.1)  # Simulate processing
                response_received.set()

        communicator.add_message_listener(TestMessageListener())
        reader = communicator._EmbodySerial__reader
        reader.add_response_message_listener(TestResponseListener())

        # Send both types of messages
        reader._ReaderThread__handle_message(codec.Heartbeat())
        reader._ReaderThread__handle_response_message(codec.HeartbeatResponse())

        # Both should complete (running in parallel)
        assert message_received.wait(timeout=0.5)
        assert response_received.wait(timeout=0.5)

        communicator.shutdown()

    def test_file_download_doesnt_block_callbacks(self):
        """Verify file download doesn't prevent callback processing."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        callback_executed = threading.Event()

        class TestListener(MessageListener):
            def message_received(self, msg: codec.Message) -> None:
                callback_executed.set()

        communicator.add_message_listener(TestListener())

        # Start a file download in background
        def download_file():
            with patch.object(communicator._EmbodySerial__reader, "download_file") as mock_download:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                    mock_download.return_value = tmp.name
                time.sleep(0.1)  # Simulate download time
                communicator.download_file("test.bin", 1024, timeout=5)

        download_thread = threading.Thread(target=download_file)
        download_thread.start()

        # Give download time to acquire lock
        time.sleep(0.05)

        # Trigger callback - should still execute despite download
        reader = communicator._EmbodySerial__reader
        reader._ReaderThread__handle_message(codec.Heartbeat())

        # Callback should complete
        assert callback_executed.wait(timeout=1)

        download_thread.join(timeout=2)
        communicator.shutdown()

    def test_response_callbacks_not_starved_by_message_callbacks(self):
        """Verify response callbacks have dedicated executor and cannot be starved."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        message_callback_started = threading.Event()
        response_callback_completed = threading.Event()

        class BlockingMessageListener(MessageListener):
            """Message callback that blocks for extended period."""

            def message_received(self, msg: codec.Message) -> None:
                message_callback_started.set()
                time.sleep(0.5)  # Block message callback executor

        class FastResponseListener(ResponseMessageListener):
            """Response callback that should execute immediately."""

            def response_message_received(self, msg: codec.Message) -> None:
                response_callback_completed.set()

        # Add blocking message listener
        communicator.add_message_listener(BlockingMessageListener())

        # Add response listener
        reader = communicator._EmbodySerial__reader
        reader.add_response_message_listener(FastResponseListener())

        # Trigger blocking message callback
        reader._ReaderThread__handle_message(codec.Heartbeat())

        # Wait for message callback to start blocking
        assert message_callback_started.wait(timeout=1)

        # Now send response callback - it should execute immediately despite blocked message callback
        start = time.time()
        reader._ReaderThread__handle_response_message(codec.HeartbeatResponse())

        # Response callback should complete quickly (not wait for message callback)
        assert response_callback_completed.wait(timeout=0.2)
        elapsed = time.time() - start

        # Should complete much faster than the 0.5s message callback block time
        assert elapsed < 0.3, f"Response callback took {elapsed}s - likely starved by message callback"

        communicator.shutdown()
