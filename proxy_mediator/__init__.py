from contextvars import ContextVar
from typing import Type
from aries_staticagent.utils import validate
from aries_staticagent.message import BaseMessage
from .agent import Connections

CONNECTIONS: ContextVar[Connections] = ContextVar("connections")


def message_as(message_cls: Type[BaseMessage]):
    return validate(lambda msg: message_cls.parse_obj(msg.dict(by_alias=True)))
