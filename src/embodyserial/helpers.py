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
        response = self.__sender.send(
            codec.GetAttribute(attributes.CurrentTimeAttribute.attribute_id),
            self.__send_timeout,
        )
        if response and isinstance(response, codec.GetAttributeResponse):
            return datetime.fromtimestamp(response.value.value / 1000, tz=timezone.utc)
        else:
            return None
