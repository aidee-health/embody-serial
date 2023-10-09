"""Test cases for the helpers module."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from embodycodec import attributes
from embodycodec import codec
from embodycodec import types
from serial.serialutil import SerialException

from embodyserial import helpers
from embodyserial.exceptions import MissingResponseError


def test_get_current_time_success() -> None:
    sender = __create_sender_mock(attr=attributes.CurrentTimeAttribute(1666368870000))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    current_time = send_helper.get_current_time()
    assert current_time == datetime.fromisoformat("2022-10-21 16:14:30.000+00:00")


def test_get_current_time_no_response() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(return_value=None)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(MissingResponseError):
        send_helper.get_current_time()


def test_get_current_time_with_exception() -> None:
    """Test successful get current time."""
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(side_effect=SerialException)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(SerialException):
        send_helper.get_current_time()


def test_get_serial_no_success() -> None:
    sender = __create_sender_mock(attr=attributes.SerialNoAttribute(12345678))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    serial_no = send_helper.get_serial_no()
    assert serial_no == "0000000000bc614e"


def test_get_battery_level() -> None:
    sender = __create_sender_mock(attr=attributes.BatteryLevelAttribute(3))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    battery_level = send_helper.get_battery_level()
    assert battery_level == 3


def test_get_vendor() -> None:
    sender = __create_sender_mock(attr=attributes.VendorAttribute("Aidee"))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    vendor = send_helper.get_vendor()
    assert vendor == "Aidee"


def test_get_model() -> None:
    sender = __create_sender_mock(attr=attributes.ModelAttribute("Aidee Embody"))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    model = send_helper.get_model()
    assert model == "Aidee Embody"


def test_get_firmware_version() -> None:
    sender = __create_sender_mock(attr=attributes.FirmwareVersionAttribute(0x010203))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    version = send_helper.get_firmware_version()
    assert version == "01.02.03"


def __create_sender_mock(attr: attributes.Attribute) -> helpers.EmbodySender:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(  # type: ignore
        return_value=codec.GetAttributeResponse(
            attribute_id=attr.attribute_id,
            changed_at=int(datetime.now().timestamp() * 1000),
            reporting=types.Reporting(interval=1, on_change=2),
            value=attr,
        )
    )
    return sender


def __create_set_sender_mock() -> helpers.EmbodySender:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(return_value=codec.SetAttributeResponse())  # type: ignore
    return sender


def test_get_on_body_detect_success() -> None:
    sender = __create_sender_mock(attr=attributes.OnBodyDetectAttribute(True))
    send_helper = helpers.EmbodySendHelper(sender=sender)
    on_body_detect = send_helper.get_on_body_detect()
    assert on_body_detect is True


def test_get_on_body_detect_no_response() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(return_value=None)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(MissingResponseError):
        send_helper.get_on_body_detect()


def test_get_on_body_detect_with_exception() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(side_effect=SerialException)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(SerialException):
        send_helper.get_on_body_detect()


def test_set_on_body_detect_success() -> None:
    sender = __create_set_sender_mock()
    send_helper = helpers.EmbodySendHelper(sender=sender)
    result = send_helper.set_on_body_detect(True)
    assert result is True


def test_set_on_body_detect_no_response() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(return_value=None)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(MissingResponseError):
        send_helper.set_on_body_detect(True)
    sender.send.assert_called_once()


def test_set_on_body_detect_with_exception() -> None:
    sender: helpers.EmbodySender = Mock()
    sender.send = Mock(side_effect=SerialException)  # type: ignore
    send_helper = helpers.EmbodySendHelper(sender=sender)
    with pytest.raises(SerialException):
        send_helper.set_on_body_detect(True)
    sender.send.assert_called_once()
