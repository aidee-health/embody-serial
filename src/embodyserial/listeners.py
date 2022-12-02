"""Listener interfaces that can be subscribed to by clients."""

from abc import ABC
from abc import abstractmethod

from embodycodec import codec


class MessageListener(ABC):
    """Listener interface for being notified of incoming messages."""

    @abstractmethod
    def message_received(self, msg: codec.Message) -> None:
        """Process received message"""
        pass


class ResponseMessageListener(ABC):
    """Listener interface for being notified of incoming response messages."""

    @abstractmethod
    def response_message_received(self, msg: codec.Message) -> None:
        """Process received response message"""
        pass


class ConnectionListener(ABC):
    """Listener interface for being notified of connection changes."""

    @abstractmethod
    def on_connected(self, connected: bool) -> None:
        """Process connection status."""
        pass


class FileDownloadListener(ABC):
    """Listener interface for being notified of file download progress."""

    @abstractmethod
    def on_file_download_progress(
        self, original_file_name: str, size: int, progress: float, kbps: float
    ) -> None:
        """Process file download progress."""
        pass

    @abstractmethod
    def on_file_download_complete(
        self, original_file_name: str, path: str, kbps: float
    ) -> None:
        """Process file download completion."""
        pass

    @abstractmethod
    def on_file_download_failed(
        self, original_file_name: str, error: Exception
    ) -> None:
        """Process file download failure."""
        pass
