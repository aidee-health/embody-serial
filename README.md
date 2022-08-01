# Embody Serial Communicator

[![Tests](https://github.com/aidee-health/embody-serial-communicator/workflows/Tests/badge.svg)][tests]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

[tests]: https://github.com/aidee-health/embody-serial-communicator/actions?workflow=Tests
[pre-commit]: https://github.com/pre-commit/pre-commit
[black]: https://github.com/psf/black

## Features

- Connects to an EmBody device over the serial port
- Uses the EmBody protocol to communicate with the device
- Integrates with [the EmBody Protocol Codec](https://github.com/aidee-health/embody-protocol-codec) project
- Asynchronous send without having to wait for response
- Synchronous send where response message is returned
- Provides callback interfaces for incoming messages, response messages and connect/disconnect
- All methods and callbacks are threadsafe
- Separate threads for send, receive and callback processing
- Type safe code using [mypy](https://mypy.readthedocs.io/) for type checking

## Requirements

- Python 3.9 or newer
- Access to private Aidee Health repositories on Github

## Installation

You can install _Embody Serial Communicator_ via [pip] from private Github repo:

```console
$ pip install "git+https://github.com/aidee-health/embody-serial-communicator@main#egg=embodyserial"
```

## Usage

A very basic example where you send a message request and get a response:

```python
from embodyserial import communicator
from embodycodec import codec

comm = communicator.EmbodySerialCommunicator()
response = comm.send_message_and_wait_for_response(codec.ListFiles())
print(f"Received response: {response}")
comm.shutdown()
```

If you want to see more of what happens under the hood, activate debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

Please see the [Command-line Reference] for more details.

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

## Credits

This project was generated from [@cjolowicz]'s [Hypermodern Python Cookiecutter] template.

[@cjolowicz]: https://github.com/cjolowicz
[hypermodern python cookiecutter]: https://github.com/cjolowicz/cookiecutter-hypermodern-python
[file an issue]: https://github.com/aidee-health/embody-serial-communicator/issues
[pip]: https://pip.pypa.io/

<!-- github-only -->

[license]: https://github.com/aidee-health/embody-serial-communicator/blob/main/LICENSE
[contributor guide]: https://github.com/aidee-health/embody-serial-communicator/blob/main/CONTRIBUTING.md
[command-line reference]: https://embody-serial-communicator.readthedocs.io/en/latest/usage.html
