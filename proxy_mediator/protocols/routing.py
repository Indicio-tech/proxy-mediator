"""Routing protocol."""
from typing import Any, Dict

from aries_staticagent.message import BaseMessage
from aries_staticagent.module import Module, ModuleRouter

from .. import CONNECTIONS, message_as
from ..connections import Connection
from ..error import Reportable


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
    to: str
    msg: Dict[str, Any]


class Routing(Module):
    doc_uri = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
    protocol = "routing"
    version = "1.0"
    route = ModuleRouter()

    @route
    @message_as(Forward)
    async def forward(self, msg: Forward, conn: Connection):
        """Handle forward message."""
        connections = CONNECTIONS.get()
        if not connections.agent_connection:
            raise AgentConnectionNotEstablished(
                "Connection to the agent has not yet been established."
            )
        if not connections.mediator_connection:
            raise MediatorConnectionNotEstablished(
                "Connection to mediator has not yet been established; "
                "forward messages may only be received from mediator connection"
            )
        if conn != connections.mediator_connection:
            raise ForwardFromUnauthorizedConnection(
                "Forward messages may only be received from mediator connection"
            )

        # Assume forward is for the agent connection and just send.
        # Do not perform any wrapping on message (send as "plaintext") because
        # message is already packed.
        await connections.agent_connection.send_async(msg.msg, plaintext=True)
