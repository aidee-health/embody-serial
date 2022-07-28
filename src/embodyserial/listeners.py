"""Listener interfaces that can be subscribed to by clients."""

from abc import ABC

from embodycodec import codec


class MessageListener(ABC):
    """Listener interface for being notified of incoming messages."""

    def message_received(self, msg: codec.Message) -> None:
        """Process received message"""
        pass


class ResponseMessageListener(ABC):
    """Listener interface for being notified of incoming response messages."""

    def response_message_received(self, msg: codec.Message) -> None:
        """Process received response message"""
        pass


class ConnectionListener(ABC):
    """Listener interface for being notified of connection changes."""

    def on_connected(self, connected: bool) -> None:
        """Process connection status."""
        pass
