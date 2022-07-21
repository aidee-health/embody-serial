"""Command-line interface."""
import click


@click.command()
@click.version_option()
def main() -> None:
    """Embody Serial Communicator."""


if __name__ == "__main__":
    main(prog_name="embody-serial-communicator")  # pragma: no cover
