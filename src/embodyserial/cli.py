"""cli entry point for embodyserial.

Parse command line arguments, invoke embody device.
"""
import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

import embodyserial.exceptions as embodyexceptions
from embodyserial import __version__
from embodyserial.embodyserial import EmbodySerial
from embodyserial.helpers import EmbodySendHelper
from embodyserial.listeners import FileDownloadListener


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
    "on_body_state": "get_on_body_state",
}


def main(args=None):
    """Entry point for embody-serial cli.

    The .toml entry_point wraps this in sys.exit already so this effectively
    becomes sys.exit(main()).
    The __main__ entry point similarly wraps sys.exit().
    """
    error = None
    if args is None:
        args = sys.argv[1:]

    parsed_args = __get_args(args)
    logging.basicConfig(
        level=getattr(logging, parsed_args.log_level.upper(), logging.INFO),
        format="%(asctime)s:%(levelname)s:%(message)s",
    )
    try:
        embody_serial = EmbodySerial(serial_port=parsed_args.device)
    except Exception as e:
        print(f"Connection error: {e}")
        exit(-1)

    send_helper = EmbodySendHelper(sender=embody_serial)
    try:
        if parsed_args.get:
            print(f"{getattr(send_helper, get_attributes_dict.get(parsed_args.get))()}")
        elif parsed_args.get_all:
            __get_all_attributes(send_helper)
        elif parsed_args.set_time:
            print(f"Set current time: {send_helper.set_current_timestamp()}")
            print(f"New current time is: {send_helper.get_current_time()}")
        elif parsed_args.set_trace_level:
            print(
                f"Trace level set: {send_helper.set_trace_level(parsed_args.set_trace_level)}"
            )
        elif parsed_args.list_files:
            __list_files(send_helper)
        elif parsed_args.download_file:
            __download_file(
                file_name=parsed_args.download_file,
                embody_serial=embody_serial,
                send_helper=send_helper,
                ignore_crc_error=parsed_args.ignore_crc_error,
                output_folder=parsed_args.output_folder,
                delete=parsed_args.delete,
            )
        elif parsed_args.download_file_with_delay:
            __download_file(
                file_name=parsed_args.download_file_with_delay,
                embody_serial=embody_serial,
                send_helper=send_helper,
                delay=0.01,
                ignore_crc_error=parsed_args.ignore_crc_error,
                output_folder=parsed_args.output_folder,
                delete=parsed_args.delete,
            )
        elif parsed_args.download_files:
            __download_files(
                embody_serial=embody_serial,
                send_helper=send_helper,
                ignore_crc_error=parsed_args.ignore_crc_error,
                output_folder=parsed_args.output_folder,
                delete=parsed_args.delete,
            )
        elif parsed_args.delete_file:
            print(
                f"Delete file {parsed_args.delete_file}:"
                f" {send_helper.delete_file(file_name=parsed_args.delete_file)}"
            )
        elif parsed_args.delete_files:
            print(f"Delete files: {send_helper.delete_all_files()}")
        elif parsed_args.reformat_disk:
            print(f"Reformatting disk: {send_helper.reformat_disk()}")
        elif parsed_args.reset:
            print(f"Resetting device: {send_helper.reset_device()}")
        elif parsed_args.reboot:
            print(f"Rebooting device: {send_helper.reboot_device()}")
        elif parsed_args.activate_on_body_detect:
            print(f"Activating on body detect: {send_helper.set_on_body_detect(True)}")
        elif parsed_args.deactivate_on_body_detect:
            print(
                f"Deactivating on body detect: {send_helper.set_on_body_detect(False)}"
            )
        else:
            pass
    except KeyboardInterrupt as e:
        print(f"Keyboard interrupt: {e}")
        error = e
    except Exception as e:
        print(f"Error occurred: {e}")
        error = e
    finally:
        embody_serial.shutdown()
        if error:
            print(f"({type(error)}): {error}")
            if isinstance(error, embodyexceptions.TimeoutError):
                sys.exit(-3)
            if isinstance(error, embodyexceptions.CrcError):
                sys.exit(-2)
            sys.exit(-1)
        sys.exit(0)


def __get_all_attributes(send_helper):
    for attrib in get_attributes_dict.keys():
        sys.stdout.write(f"{attrib}: ")
        sys.stdout.flush()
        try:
            print(getattr(send_helper, get_attributes_dict.get(attrib))())
        except Exception as e:
            print(f"Error: {e}")


def __list_files(send_helper):
    files = send_helper.get_files()
    if len(files) > 0:
        for name, size in files:
            print(f"{name} ({round(size/1024)}KB)")
    else:
        print("[]")


def __download_files(
    embody_serial: EmbodySerial,
    send_helper: EmbodySendHelper,
    ignore_crc_error: bool = False,
    output_folder: Optional[Path] = None,
    delete: bool = False,
):
    files = send_helper.get_files()
    if len(files) == 0:
        print("No files on device")
        return
    print(f"Found {len(files)} {'files' if len(files) > 1 else 'file'}")
    for file in files:
        __do_download_file(
            file,
            embody_serial,
            send_helper,
            ignore_crc_error=ignore_crc_error,
            output_folder=output_folder,
            delete=delete,
        )


def __download_file(
    file_name: str,
    embody_serial: EmbodySerial,
    send_helper: EmbodySendHelper,
    delay: float = 0.0,
    ignore_crc_error: bool = False,
    output_folder: Optional[Path] = None,
    delete: bool = False,
):
    filtered_files: list[tuple[str, int]] = [
        tup for tup in send_helper.get_files() if tup[0] == file_name
    ]
    if not filtered_files or len(filtered_files) == 0:
        print(f"Unknown file name {file_name}")
        return
    __do_download_file(
        filtered_files[0],
        embody_serial,
        send_helper,
        delay,
        ignore_crc_error,
        output_folder,
        delete,
    )


def _show_cli_progress_bar(progress: float, total: int, kbps: float):
    bar_length = 20
    percent = progress / 100
    hashes = "#" * int(round(percent * bar_length))
    spaces = " " * (bar_length - len(hashes))
    sys.stdout.write(
        "\rProgress: [{}] {}% ({} kbps)".format(
            hashes + spaces, int(round(percent * 100)), int(round(kbps))
        )
    )
    sys.stdout.flush()


def __do_download_file(
    file: tuple[str, int],
    embody_serial: EmbodySerial,
    send_helper: EmbodySendHelper,
    delay: float = 0.0,
    ignore_crc_error: bool = False,
    output_folder: Optional[Path] = None,
    delete: bool = False,
):
    print(f"Downloading: {file[0]}")

    class _DownloadListener(FileDownloadListener):
        download_invocation_count = 0
        error: Optional[Exception] = None

        def on_file_download_progress(
            self, original_file_name: str, size: int, progress: float, kbps: float
        ) -> None:
            """Display progress in cli."""
            _show_cli_progress_bar(progress, size, kbps)

        def on_file_download_complete(
            self, original_file_name: str, path: str, kbps: float
        ) -> None:
            """Process file download completion."""
            print(f" {original_file_name} downloaded to {path} (@{round(kbps)} kbps)")

        def on_file_download_failed(
            self, original_file_name: str, error: Exception
        ) -> None:
            """Process file download failure."""
            pass

    listener = _DownloadListener()
    tmp_file = embody_serial.download_file(
        file_name=file[0],
        size=file[1],
        download_listener=listener,
        delay=delay,
        ignore_crc_error=ignore_crc_error,
    )
    if output_folder and tmp_file:
        if not output_folder.exists():
            output_folder.mkdir(parents=True)
        filepath = output_folder.joinpath(file[0])
        shutil.move(tmp_file, filepath)
        print(f" {file[0]} moved to {filepath}")

    if delete and tmp_file:
        print(f" Delete file {file[0]}: {send_helper.delete_file(file_name=file[0])}")


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
    parser.add_argument("--device", help="Serial port name", default=None)
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
        "--download-file-with-delay",
        help="Download specified file with simulated delay",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--download-files", help="Download all files", action="store_true", default=None
    )
    parser.add_argument(
        "--ignore-crc-error", help="Ignore CRC errors", action="store_false"
    )
    parser.add_argument(
        "--output-folder",
        help="Download file(s) to specified folder",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--delete",
        help="Delete on device after successful download",
        action="store_true",
        default=None,
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
        "--activate-on-body-detect", help="Activate on body detect", action="store_true"
    )
    parser.add_argument(
        "--deactivate-on-body-detect",
        help="Deactivate on body detect",
        action="store_true",
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
