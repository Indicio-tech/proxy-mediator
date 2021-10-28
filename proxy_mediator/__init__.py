from typing import Type
from aries_staticagent.utils import validate
from aries_staticagent.message import BaseMessage


def message_as(message_cls: Type[BaseMessage]):
    return validate(lambda msg: message_cls.parse_obj(msg.dict(by_alias=True)))
