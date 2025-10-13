"""Initialize the embodyserial package."""

import importlib.metadata
import logging

# Configure NullHandler by default to prevent unwanted logging output
_library_logger = logging.getLogger("embodyserial")
if not _library_logger.handlers:
    _library_logger.addHandler(logging.NullHandler())


try:
    __version__ = importlib.metadata.version("embody-serial")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"
