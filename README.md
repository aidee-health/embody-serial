# Embody Serial

[![Tests](https://github.com/aidee-health/embody-serial/workflows/Tests/badge.svg)][tests]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

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

- Python 3.9
- Access to private Aidee Health repositories on Github

## Installation

You can install _Embody Serial Communicator_ via [pip] from private Github repo:

```console
$ pip install "git+https://github.com/aidee-health/embody-serial@v1.0.4#egg=embodyserial"
```

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

If you want to see more of what happens under the hood, activate debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

## Using the application from the command line

The application also supports command line arguments.

Once installed with pip, type:

```
embody-serial --help
```

To see which options are available.

### Example 1 - List all attribute values

```shell
embody-serial --device COM3 --get-all
```

### Example 2 - Get serial no of device

```shell
embody-serial --device COM3 --get serialno
```

### Example 3 - List files over serial port

```shell
embody-serial --device /dev/cu.usbmodem2101 --list-files
```

### Example 3 - Set time current time (UTC)

```shell
embody-serial --device COM3 --set-time
```

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

[file an issue]: https://github.com/aidee-health/embody-serial/issues
[pip]: https://pip.pypa.io/

<!-- github-only -->

[license]: https://github.com/aidee-health/embody-serial/blob/main/LICENSE
[contributor guide]: https://github.com/aidee-health/embody-serial/blob/main/CONTRIBUTING.md
[command-line reference]: https://embody-serial.readthedocs.io/en/latest/usage.html
