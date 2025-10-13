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

    def test_three_callbacks_run_in_parallel(self):
        """Verify that up to 3 callbacks can execute simultaneously."""
        serial = DummySerial()

        execution_times = []
        lock = threading.Lock()
        barrier = threading.Barrier(3)  # Synchronize 3 callbacks

        class SlowListener(MessageListener):
            def __init__(self, listener_id):
                self.id = listener_id
                self.called = False

            def message_received(self, msg: codec.Message) -> None:
                if self.called:
                    return  # Only process first message
                self.called = True

                with lock:
                    execution_times.append((self.id, "start", time.time()))

                # Wait for all 3 to start
                barrier.wait(timeout=1)

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
        time.sleep(0.2)

        # Verify all three ran in parallel
        start_events = [(id, t) for id, event, t in execution_times if event == "start"]
        end_events = [(id, t) for id, event, t in execution_times if event == "end"]

        assert len(start_events) == 3
        assert len(end_events) == 3

        # All should start within a short time (parallel execution)
        start_times = [t for _, t in start_events]
        latest_start = max(start_times)
        earliest_start = min(start_times)
        assert latest_start - earliest_start < 0.1  # Started nearly simultaneously

        # All should end after all started (barrier ensures this)
        earliest_end = min(t for _, t in end_events)
        assert earliest_end > latest_start

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

    def test_max_three_concurrent_callbacks(self):
        """Verify that only 3 callbacks run concurrently, 4th waits."""
        serial = DummySerial()
        communicator = serialcomm.EmbodySerial(serial_port="Dummy", serial_instance=serial)

        active_count = 0
        max_active = 0
        lock = threading.Lock()

        class CountingListener(MessageListener):
            def __init__(self, listener_id):
                self.id = listener_id

            def message_received(self, msg: codec.Message) -> None:
                nonlocal active_count, max_active
                with lock:
                    active_count += 1
                    max_active = max(max_active, active_count)

                time.sleep(0.1)  # Hold the worker

                with lock:
                    active_count -= 1

        # Add four listeners
        for i in range(4):
            communicator.add_message_listener(CountingListener(i))

        # Trigger all four quickly
        reader = communicator._EmbodySerial__reader
        for _ in range(4):
            reader._ReaderThread__handle_message(codec.Heartbeat())

        # Wait for processing
        time.sleep(0.3)

        # Should have seen at most 3 concurrent
        assert max_active == 3

        communicator.shutdown()
