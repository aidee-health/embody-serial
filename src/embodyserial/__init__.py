"""Initialize the embodyserial package."""
import importlib.metadata as importlib_metadata


try:
    # This will read version from pyproject.toml
    __version__ = importlib_metadata.version(__name__)
except Exception:
    __version__ = "unknown"
