"""Initialize the embodyserial package."""
import importlib.metadata


try:
    __version__ = importlib.metadata.version("embody-serial")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"
