"""Test cases for the helpers module."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from embodycodec import attributes
from embodycodec import codec
from embodycodec import types
from serial.serialutil import SerialException

from embodyserial import helpers


def test_get_current_time_success() -> None:
    sender = __create_sender_mock(attr=attributes.CurrentTimeAttribute(1666368870000))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    current_time = send_helper.get_current_time()
    assert current_time
    assert current_time == datetime.fromisoformat("2022-10-21 16:14:30.000+00:00")


def test_get_current_time_no_response() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(return_value=None)
    send_helper = helpers.EmbodySendHelper(sender=sender)
    current_time = send_helper.get_current_time()
    assert current_time is None


def test_get_current_time_with_exception() -> None:
    """Test successful get current time."""
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(side_effect=SerialException)
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(Exception):
        send_helper.get_current_time()


def test_get_serial_no_success() -> None:
    sender = __create_sender_mock(attr=attributes.SerialNoAttribute(12345678))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    serial_no = send_helper.get_serial_no()
    assert serial_no
    assert serial_no == "0000000000bc614e"


def __create_sender_mock(attr: attributes.Attribute) -> helpers.EmbodySender:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(
        return_value=codec.GetAttributeResponse(
            attribute_id=attr.attribute_id,
            changed_at=int(datetime.now().timestamp() * 1000),
            reporting=types.Reporting(interval=1, on_change=2),
            value=attr,
        )
    )
    return sender
