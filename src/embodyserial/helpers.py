"""Helpers for the embodyserial interface."""

from datetime import datetime
from datetime import timezone
from typing import Optional

from embodycodec import attributes
from embodycodec import codec
from embodycodec import types

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
        return (
            response_attribute.temp_celsius()
            if response_attribute
            and isinstance(response_attribute, attributes.TemperatureAttribute)
            else None
        )

    def get_firmware_version(self) -> Optional[str]:
        response_attribute = self.__do_send_get_attribute_request(
            attributes.FirmwareVersionAttribute.attribute_id
        )
        return response_attribute.value if response_attribute else None

    def get_files(self) -> list[str]:
        response = self.__sender.send(
            msg=codec.ListFiles(), timeout=self.__send_timeout
        )
        files = list()
        if response and isinstance(response, codec.ListFilesResponse):
            if len(response.files) == 0:
                return files
            else:
                for file in response.files:
                    files.append(str(file.file_name))
        else:
            return files

    def delete_file(self, file_name: str) -> bool:
        response = self.__sender.send(
            msg=codec.DeleteFile(types.File(file_name)), timeout=self.__send_timeout
        )
        return (
            True
            if response and isinstance(response, codec.DeleteFileResponse)
            else False
        )

    def get_file(self, file_name: str) -> bool:
        response = self.__sender.send(
            msg=codec.GetFile(file=types.File(file_name=file_name)),
            timeout=self.__send_timeout,
        )
        if not response or not isinstance(response, codec.GetFileResponse):
            return False
        # TODO (Espen - 2022-10-21): add listener and act on codec.SendFile message
        # set path in init or in this method
        return True

    def set_current_timestamp(self) -> bool:
        return self.set_timestamp(datetime.now(timezone.utc))

    def set_timestamp(self, time: datetime) -> bool:
        attr = attributes.CurrentTimeAttribute(int(time.timestamp() * 1000))
        return self.__do_send_set_attribute_request(attr)

    def set_trace_level(self, level: int) -> bool:
        attr = attributes.TraceLevelAttribute(level)
        return self.__do_send_set_attribute_request(attr)

    def reformat_disk(self, file_name: str) -> bool:
        response = self.__sender.send(
            msg=codec.ReformatDisk, timeout=self.__send_timeout
        )
        return (
            True
            if response and isinstance(response, codec.ReformatDiskResponse)
            else False
        )

    def __do_send_get_attribute_request(
        self, attribute_id: int
    ) -> Optional[attributes.Attribute]:
        response = self.__sender.send(
            msg=codec.GetAttribute(attribute_id), timeout=self.__send_timeout
        )
        if response and isinstance(response, codec.GetAttributeResponse):
            return response.value
        else:
            return None

    def __do_send_set_attribute_request(self, attr: attributes.Attribute) -> bool:
        response = self.__sender.send(
            msg=codec.SetAttribute(attr.attribute_id), timeout=self.__send_timeout
        )
        return response and isinstance(response, codec.SetAttributeResponse)
