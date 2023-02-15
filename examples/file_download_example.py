"""An example that lists all files on the device and downloads them to the current directory.

To run this example, you need to have a device connected to your computer over USB.
Run the example with `poetry run python examples/file_download_example.py`.
"""

import logging

from embodyserial.embodyserial import EmbodySerial
from embodyserial.helpers import EmbodySendHelper


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s"
    )
    logging.info("Starting reporting example")

    logging.info("Setting up communicator")
    # Connect to first available device
    embody_serial = EmbodySerial()
    send_helper = EmbodySendHelper(sender=embody_serial)
    files = send_helper.get_files()
    if len(files) > 0:
        for name, size in files:
            logging.info(f"Downloading {name} ({round(size/1024)}KB)")
            file_name = embody_serial.download_file(file_name=name, size=size)
            logging.info(f"Downloaded {file_name} ({round(size/1024)}KB)")
    else:
        logging.info("No files found on device")

    embody_serial.shutdown()
