# Embody Serial

[![PyPI](https://img.shields.io/pypi/v/embody-serial.svg)][pypi_]
[![Status](https://img.shields.io/pypi/status/embody-serial.svg)][status]
[![Python Version](https://img.shields.io/pypi/pyversions/embody-serial)][python version]
[![License](https://img.shields.io/pypi/l/embody-serial)][license]

[![Tests](https://github.com/aidee-health/embody-serial/workflows/Tests/badge.svg)][tests]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

[pypi_]: https://pypi.org/project/embody-serial/
[status]: https://pypi.org/project/embody-serial/
[python version]: https://pypi.org/project/embody-serial
[tests]: https://github.com/aidee-health/embody-serial/actions?workflow=Tests
[pre-commit]: https://github.com/pre-commit/pre-commit
[black]: https://github.com/psf/black

## Features

- Connects to an EmBody device over the serial port
- Uses the EmBody protocol to communicate with the device
- Integrates with [the EmBody Protocol Codec](https://github.com/aidee-health/embody-protocol-codec) project
- Asynchronous send without having to wait for response
- Synchronous send where response message is returned
- Send facade for protocol agnostic communication with device
- Provides callback interfaces for incoming messages, response messages and connect/disconnect
- All methods and callbacks are threadsafe
- Separate threads for send, receive and callback processing
- Type safe code using [mypy](https://mypy.readthedocs.io/) for type checking

## Requirements

- Python 3.9 or newer
- Access to private Aidee Health repositories on Github

## Installation

You can install _Embody Serial_ via [pip]:

```console
$ pip install embody-serial
```

This adds `embody-serial` as a library, but also provides the CLI application with the same name.

## Usage

A very basic example where you send a message request and get a response:

```python
from embodyserial.embodyserial import EmbodySerial
from embodyserial.helpers import EmbodySendHelper

embody_serial = EmbodySerial()
send_helper = EmbodySendHelper(sender=embody_serial)
print(f"Serial no: {send_helper.get_serial_no()}")
embody_serial.shutdown()
```

If you want to see more of what happens under the hood, activate debug logging before setting up `EmbodySerial`:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

## Using the application from the command line

The application also provides a CLI application that is automatically added to the path when installing via pip.

Once installed with pip, type:

```
embody-serial --help
```

To see which options are available.

> **Note**
> The serial port is automatically detected, but can be overridden by using the `--device` option.

### Example - List all attribute values

```shell
embody-serial --get-all
```

### Example - Get serial no of device

```shell
embody-serial --get serialno
```

### Example - List files over serial port

```shell
embody-serial --list-files
```

### Example - Set time current time (UTC)

```shell
embody-serial --set-time
```

### Example - Download files

```shell
embody-serial --download-files
```

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

[file an issue]: https://github.com/aidee-health/embody-serial/issues
[pip]: https://pip.pypa.io/

## Troubleshooting

### I get an error message saying 'no module named serial' or similar

This is a known issue and is usually caused by one of two things.

#### Ensure you haven't installed `serial` or `jserial`

Embody-serial uses the `pyserial` library. Run `pip list` to see if either the `serial` or `jserial` library is installed. If they are, remove them with `pip uninstall serial`.

#### Problems with pyserial

Sometimes, for whatever reason, it is necessary to re-install pyserial. Perform a `pip uninstall pyserial` and then `pip install pyserial` to see if this helps.

<!-- github-only -->

[license]: https://github.com/aidee-health/embody-serial/blob/main/LICENSE
[contributor guide]: https://github.com/aidee-health/embody-serial/blob/main/CONTRIBUTING.md
[command-line reference]: https://embody-serial.readthedocs.io/en/latest/usage.html
