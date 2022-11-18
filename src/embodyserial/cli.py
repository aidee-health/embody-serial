"""cli entry point for embodyserial.

Parse command line arguments, invoke embody device.
"""
import argparse
import logging
import sys
import time

from . import __version__
from .embodyserial import EmbodySerial
from .helpers import EmbodySendHelper


get_attributes_dict: dict[str, str] = {
    "serialno": "get_serial_no",
    "ble_mac": "get_bluetooth_mac",
    "model": "get_model",
    "vendor": "get_vendor",
    "time": "get_current_time",
    "battery": "get_battery_level",
    "hr": "get_heart_rate",
    "chargestate": "get_charge_state",
    "temperature": "get_temperature",
    "firmware": "get_firmware_version",
}


def main(args=None):
    """Entry point for embody-serial cli.

    The .toml entry_point wraps this in sys.exit already so this effectively
    becomes sys.exit(main()).
    The __main__ entry point similarly wraps sys.exit().
    """
    if args is None:
        args = sys.argv[1:]

    parsed_args = __get_args(args)
    logging.basicConfig(
        level=getattr(logging, parsed_args.log_level.upper(), logging.INFO),
        format="%(asctime)s:%(levelname)s:%(message)s",
    )
    embody_serial = EmbodySerial(serial_port=parsed_args.device)
    send_helper = EmbodySendHelper(sender=embody_serial)
    try:
        if parsed_args.get:
            print(f"{getattr(send_helper, get_attributes_dict.get(parsed_args.get))()}")
            exit(0)
        elif parsed_args.get_all:
            __get_all_attributes(send_helper)
            exit(0)
        elif parsed_args.set_time:
            print(f"Set current time: {send_helper.set_current_timestamp()}")
            print(f"New current time is: {send_helper.get_current_time()}")
            exit(0)
        elif parsed_args.set_trace_level:
            print(
                f"Trace level set: {send_helper.set_trace_level(parsed_args.set_trace_level)}"
            )
            exit(0)
        elif parsed_args.list_files:
            __list_files(send_helper)
            exit(0)
        elif parsed_args.download_file:
            return __download_file(
                parsed_args.download_file, embody_serial, send_helper
            )
            exit(0)
        elif parsed_args.download_files:
            __download_files(embody_serial, send_helper)
            exit(0)
        elif parsed_args.delete_file:
            print(
                f"Delete file {parsed_args.delete_file}:"
                f" {send_helper.delete_file(file_name=parsed_args.delete_file)}"
            )
            exit(0)
        elif parsed_args.delete_files:
            print(f"Delete files: {send_helper.delete_all_files()}")
            exit(0)
        elif parsed_args.reformat_disk:
            print(f"Reformatting disk: {send_helper.reformat_disk()}")
            exit(0)
        elif parsed_args.reset:
            print(f"Resetting device: {send_helper.reset_device()}")
            exit(0)
        elif parsed_args.reboot:
            print(f"Rebooting device: {send_helper.reboot_device()}")
            exit(0)

    finally:
        embody_serial.shutdown()


def __get_all_attributes(send_helper):
    for attrib in get_attributes_dict.keys():
        print(f"{attrib}: {getattr(send_helper, get_attributes_dict.get(attrib))()}")


def __list_files(send_helper):
    files = send_helper.get_files()
    if len(files) > 0:
        for name, size in send_helper.get_files():
            print(f"{name} ({round(size/1024)}KB)")
    else:
        print("[]")


def __download_files(embody_serial: EmbodySerial, send_helper: EmbodySendHelper):
    files = send_helper.get_files()
    if len(files) == 0:
        print("No files on device")
        return
    print(f"Found {len(files)} {'files' if len(files) > 1 else 'file'}")
    for file in files:
        __do_download_file(file, embody_serial, send_helper)


def __download_file(
    file_name: str, embody_serial: EmbodySerial, send_helper: EmbodySendHelper
):
    filtered_files: list[tuple[str, int]] = [
        tup for tup in send_helper.get_files() if tup[0] == file_name
    ]
    if not filtered_files or len(filtered_files) == 0:
        print(f"Unknown file name {file_name}")
        return
    __do_download_file(filtered_files[0], embody_serial, send_helper)


def __do_download_file(
    file: tuple[str, int], embody_serial: EmbodySerial, send_helper: EmbodySendHelper
):
    print(f"Downloading: {file[0]}")
    start = time.time()
    downloaded_file = embody_serial.download_file(file_name=file[0], size=file[1])
    end = time.time()
    print(
        f"{file[0]} downloaded to {downloaded_file} ({round(file[1]/1024,2)}KB)"
        f" @ ({round((file[1]/1024)/(end-start),2)}KB/s)"
    )


def __get_args(args):
    """Parse arguments passed in from shell."""
    return __get_parser().parse_args(args)


def __get_parser():
    """Return ArgumentParser for pypyr cli."""
    parser = argparse.ArgumentParser(
        allow_abbrev=True,
        description="EmBody CLI application",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    log_levels = ["CRITICAL", "WARNING", "INFO", "DEBUG"]
    parser.add_argument(
        "--log-level",
        help=f"Log level ({log_levels})",
        choices=log_levels,
        default="WARNING",
    )
    parser.add_argument(
        "--channel",
        help="Use serial or ble",
        choices=["serial", "ble"],
        default="serial",
    )
    parser.add_argument(
        "--device", help="Device name (serial or ble name)", default=None
    )
    parser.add_argument(
        "--get", help="Get attribute", choices=get_attributes_dict.keys(), default=None
    )
    parser.add_argument(
        "--get-all", help="Get all attributes", action="store_true", default=None
    )
    parser.add_argument(
        "--set-time", help="Set time (to now)", action="store_true", default=None
    )
    parser.add_argument(
        "--download-file", help="Download specified file", type=str, default=None
    )
    parser.add_argument(
        "--download-files", help="Download all files", action="store_true", default=None
    )
    parser.add_argument(
        "--set-trace-level", help="Set trace level", type=int, default=None
    )
    parser.add_argument(
        "--list-files",
        help="List all files on device",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--delete-file", help="Delete specified file", type=str, default=None
    )
    parser.add_argument(
        "--delete-files", help="Delete all files", action="store_true", default=None
    )
    parser.add_argument(
        "--reformat-disk", help="Reformat disk", action="store_true", default=None
    )
    parser.add_argument(
        "--reset", help="Reset device", action="store_true", default=None
    )
    parser.add_argument(
        "--reboot", help="Reboot device", action="store_true", default=None
    )

    parser.add_argument(
        "--version",
        action="version",
        help="Echo version number.",
        version=f"{__version__}",
    )
    return parser


if __name__ == "__main__":
    main()
