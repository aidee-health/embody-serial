"""Demonstrate the use of this package. Not intended as a standalone cli."""
import logging

from .embodyserial import EmbodySerial
from .helpers import EmbodySendHelper


def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(thread)d/%(threadName)s] %(message)s",
    )

    logging.info("Setting up serial communication")
    embody_serial = EmbodySerial()
    logging.info("Setting up send helper")
    send_helper = EmbodySendHelper(sender=embody_serial)
    logging.info(f"Serial no: {send_helper.get_serial_no()}")
    logging.info(f"Firmware version: {send_helper.get_firmware_version()}")
    logging.info(f"Vendor: {send_helper.get_vendor()}")
    logging.info(f"Files on device: {send_helper.get_files()}")
    logging.info(f"Model: {send_helper.get_model()}")
    logging.info(f"Current time: {send_helper.get_current_time()}")
    logging.info(f"Battery level: {send_helper.get_battery_level()}")
    logging.info(f"Charge state: {send_helper.get_charge_state()}")
    logging.info(f"Delete all files: {send_helper.delete_all_files()}")
    logging.info(f"Reformat disk: {send_helper.reformat_disk()}")
    embody_serial.shutdown()


if __name__ == "__main__":
    main()  # pragma: no cover
