"""Default execution entry point if running the package via python -m."""
import sys

from embodyserial import cli


def main():
    """Run embodycli from script entry point."""
    return cli.main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
