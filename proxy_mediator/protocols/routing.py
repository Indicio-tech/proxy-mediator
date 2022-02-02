"""Routing protocol."""
import json
import logging
from typing import Any, Dict

from aries_staticagent.message import BaseMessage, Message
from aries_staticagent.module import Module, ModuleRouter
from pydantic.class_validators import validator

from ..agent import Agent
from ..connection import Connection
from ..error import Reportable
from .constants import DIDCOMM, DIDCOMM_OLD


LOGGER = logging.getLogger(__name__)


class ForwardError(Reportable):
    """Base Forward Errors."""


class AgentConnectionNotEstablished(ForwardError):
    """Raised when an agent connection is not established."""

    code = "agent-connection-not-established"


class MediatorConnectionNotEstablished(ForwardError):
    """Raised when no mediator connection is established.

    We should not be receiving forward messages if we haven't connected with the
    external mediator.
    """

    code = "mediator-connection-not-established"


class ForwardFromUnauthorizedConnection(ForwardError):
    """Raised when connection forward was received from is not the external mediator."""

    code = "forward-from-unauthorized-connection"


class Forward(BaseMessage):
    msg_type = f"{DIDCOMM_OLD}routing/1.0/forward"
    to: str
    msg: Dict[str, Any]

    @validator("type", pre=True, always=True)
    @classmethod
    def _type(cls, value):
        """Set type if not present."""
        if not value:
            return cls.msg_type
        return value


class Routing(Module):
    protocol = f"{DIDCOMM_OLD}routing/1.0"
    route = ModuleRouter(protocol)

    @route
    @route(doc_uri=DIDCOMM)
    async def forward(self, msg: Message, conn: Connection):
        """Handle forward message."""
        fwd = Forward.parse_obj(msg.dict(by_alias=True))
        agent = Agent.get()
        if not agent.agent_connection:
            raise AgentConnectionNotEstablished(
                "Connection to the agent has not yet been established."
            )
        if not agent.mediator_connection:
            raise MediatorConnectionNotEstablished(
                "Connection to mediator has not yet been established; "
                "forward messages may only be received from mediator connection"
            )
        if conn != agent.mediator_connection:
            raise ForwardFromUnauthorizedConnection(
                "Forward messages may only be received from mediator connection"
            )

        # Assume forward is for the agent connection and just send.
        # Do not perform any wrapping on message (send as "plaintext") because
        # message is already packed.
        assert agent.agent_connection.target
        endpoint = agent.agent_connection.target.endpoint
        assert endpoint
        await agent.agent_connection._send(json.dumps(fwd.msg).encode(), endpoint)
