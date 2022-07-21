# Embody Serial Communicator

[![Read the documentation at https://embody-serial-communicator.readthedocs.io/](https://img.shields.io/readthedocs/embody-serial-communicator/latest.svg?label=Read%20the%20Docs)][read the docs]
[![Tests](https://github.com/aidee-health/embody-serial-communicator/workflows/Tests/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/aidee-health/embody-serial-communicator/branch/main/graph/badge.svg)][codecov]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

[read the docs]: https://embody-serial-communicator.readthedocs.io/
[tests]: https://github.com/aidee-health/embody-serial-communicator/actions?workflow=Tests
[codecov]: https://app.codecov.io/gh/aidee-health/embody-serial-communicator
[pre-commit]: https://github.com/pre-commit/pre-commit
[black]: https://github.com/psf/black

## Features

- Connects to an embody device over the serial port
- Uses the embody protocol to communicate with the device
- Provides several send methods for synch/async send, send/receive, etc
- Provides callback interfaces for received messages, connect/disconnect, etc
- All methods and callbacks are threadsafe
- Separate threads for send, receive and callback processing

## Requirements

- TODO

## Installation

You can install _Embody Serial Communicator_ via [pip] from private Github repo:

```console
$ pip install git+https://github.com/aidee-health/embody-serial-communicator@main#egg=embodyserial
```

## Usage

Please see the [Command-line Reference] for details.

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
