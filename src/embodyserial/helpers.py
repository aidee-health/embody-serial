"""Helpers for the embodyserial interface."""

from datetime import datetime
from datetime import timezone
from typing import Optional

from embodycodec import attributes
from embodycodec import codec

from embodyserial.embodyserial import EmbodySender


class EmbodySendHelper:
    """Facade to make send/receive more protocol agnostic with simple get/set methods."""

    def __init__(self, sender: EmbodySender, timeout: Optional[int] = 30) -> None:
        self.__sender = sender
        self.__send_timeout = timeout

    def get_current_time(self) -> Optional[datetime]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.CurrentTimeAttribute.attribute_id
        )
        return (
            datetime.fromtimestamp(response_attribute.value / 1000, tz=timezone.utc)
            if response_attribute
            else None
        )

    def get_serial_no(self) -> Optional[str]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.SerialNoAttribute.attribute_id
        )
        return response_attribute.formatted_value() if response_attribute else None

    def get_vendor(self) -> Optional[str]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.VendorAttribute.attribute_id
        )
        return response_attribute.formatted_value() if response_attribute else None

    def get_model(self) -> Optional[str]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.ModelAttribute.attribute_id
        )
        return response_attribute.formatted_value() if response_attribute else None

    def get_bluetooth_mac(self) -> Optional[str]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.BluetoothMacAttribute.attribute_id
        )
        return response_attribute.formatted_value() if response_attribute else None

    def get_battery_level(self) -> Optional[int]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.BatteryLevelAttribute.attribute_id
        )
        return response_attribute.value if response_attribute else None

    def get_heart_rate(self) -> Optional[int]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.HeartrateAttribute.attribute_id
        )
        return response_attribute.value if response_attribute else None

    def get_charge_state(self) -> Optional[bool]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.ChargeStateAttribute.attribute_id
        )
        return response_attribute.value if response_attribute else None

    def get_temperature(self) -> Optional[float]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.TemperatureAttribute.attribute_id
        )
        return response_attribute.temp_celsius() if response_attribute else None

    def __do_send_get_attribute_request(
        self, attribute_id: int
    ) -> Optional[attributes.Attribute]:
        response = self.__sender.send(
            codec.GetAttribute(attribute_id),
            self.__send_timeout,
        )
        if response and isinstance(response, codec.GetAttributeResponse):
            return response.value
        else:
            return None
