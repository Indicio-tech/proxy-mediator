from contextvars import ContextVar
from typing import Type
from aries_staticagent.utils import validate
from aries_staticagent.message import BaseMessage
from .connections import Connections, Connection

connections: ContextVar[Connections] = ContextVar("connections")
agent_connection: ContextVar[Connection] = ContextVar("agent_connection")
mediator_connection: ContextVar[Connection] = ContextVar("mediator_connection")


def message_as(message_cls: Type[BaseMessage]):
    return validate(lambda msg: message_cls.parse_obj(msg.dict(by_alias=True)))
