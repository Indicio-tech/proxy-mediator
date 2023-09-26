"""Coordinate mediation protocol."""
import asyncio
from contextvars import ContextVar
import logging
from typing import List, Optional

from aries_staticagent.message import Message
from aries_staticagent.module import Module, ModuleRouter

from ..agent import Agent
from ..connection import Connection
from ..error import ProtocolError, Reportable, problem_reporter
from .constants import DIDCOMM, DIDCOMM_OLD
from .oob_didexchange import verkey_b58_to_didkey, verkey_to_didkey


LOGGER = logging.getLogger(__name__)


class MediationError(ProtocolError, Reportable):
    """Base Exception for mediation related errors."""


class RequestAlreadyPending(MediationError):
    """Raised when mediation request is already pending."""

    code = "request-already-pending"


class UnexpectedMediationGrant(MediationError):
    """Raised when mediation grant message received unexpectedly."""

    code = "unexpected-mediation-grant"


class ExternalMediationNotEstablished(MediationError):
    """Raised when a mediation request comes out of order.

    Specifically, when the mediation request is received before mediation with
    external mediator is established.
    """

    code = "external-mediation-not-established"


class MediationRequest:
    """Mediation request."""

    def __init__(self, connection: Connection):
        """Initialize a mediation request."""
        self.connection = connection
        self._event = asyncio.Event()

    async def completed(self):
        """Wait for mediation request to be completed."""
        await self._event.wait()

    def complete(self):
        """Mark mediation request as complete."""
        self._event.set()

    def is_complete(self):
        """Return whether mediation request is complete."""
        return self._event.is_set()


VAR: ContextVar["CoordinateMediation"] = ContextVar("coordinate_mediation")


class CoordinateMediation(Module):
    """Coordinate mediation module."""

    protocol = f"{DIDCOMM_OLD}coordinate-mediation/1.0"
    route = ModuleRouter(protocol)

    @classmethod
    def get(cls) -> "CoordinateMediation":
        """Return context var for coordinate mediation module."""
        return VAR.get()

    @classmethod
    def set(cls, value: "CoordinateMediation"):
        """Set context var for coordinate mediation module."""
        VAR.set(value)

    def __init__(self):
        """Initialize a coordinate mediation module."""
        super().__init__()
        self.external_mediator_endpoint: Optional[str] = None
        self.external_mediator_routing_keys: Optional[List[str]] = None
        self.external_pending_request: Optional[MediationRequest] = None
        self.agent_request_received: bool = False

    async def request_mediation_from_external(self, external_conn: Connection):
        """Request mediation from the external mediator."""
        LOGGER.debug("Requesting mediation from: %s", external_conn)
        if self.external_pending_request:
            raise RequestAlreadyPending(
                "Mediation request already pending to "
                f"{self.external_pending_request.connection}"
            )

        self.external_pending_request = MediationRequest(external_conn)
        await external_conn.send_async(
            {"@type": self.type("mediate-request")}, return_route="all"
        )
        await self.external_pending_request.completed()

    async def send_keylist_update(
        self, external_conn: Connection, action: str, recipient_key: str
    ):
        """Send a keylist update to the external mediator."""
        update = Message.parse_obj(
            {
                "@type": self.type("keylist-update"),
                "updates": [{"recipient_key": recipient_key, "action": action}],
            }
        )
        LOGGER.debug("Sending keylist update: %s", update.pretty_print())
        response = await external_conn.send_and_await_returned_async(
            update, type_=self.type("keylist-update-response")
        )
        # TODO Process response and check for failures
        LOGGER.debug("Received keylist update response: %s", response.pretty_print())

    @route(name="mediate-request")
    @route(doc_uri=DIDCOMM, name="mediate-request")
    @problem_reporter(exceptions=MediationError)
    async def mediate_request(self, msg, conn):
        """Handle mediation request message."""
        agent = Agent.get()
        LOGGER.debug("Received mediation request message: %s", msg.pretty_print())
        if (
            not self.external_pending_request
            or not self.external_pending_request.is_complete()
        ):
            raise ExternalMediationNotEstablished(
                "Mediation with external mediator not yet established"
            )

        assert self.external_mediator_routing_keys
        assert agent.mediator_connection

        self.agent_request_received = True
        await conn.send_async(
            {
                "@type": self.type("mediate-grant"),
                "endpoint": self.external_mediator_endpoint,
                "routing_keys": [
                    verkey_to_didkey(agent.mediator_connection.verkey),
                    *[
                        verkey_b58_to_didkey(key)
                        if not key.startswith("did:key:")
                        else key
                        for key in self.external_mediator_routing_keys
                    ],
                ],
            }
        )

    @route(name="mediate-grant")
    @route(doc_uri=DIDCOMM, name="mediate-grant")
    @problem_reporter(exceptions=MediationError)
    async def mediate_grant(self, msg, conn):
        """Handle mediation grant message."""
        LOGGER.debug("Received mediation grant message: %s", msg.pretty_print())
        if not self.external_pending_request:
            raise UnexpectedMediationGrant(
                "Received unexpected mediation grant message"
            )
        self.external_mediator_endpoint = msg["endpoint"]
        self.external_mediator_routing_keys = msg["routing_keys"]
        self.external_pending_request.complete()

    @route(name="keylist-update")
    @route(doc_uri=DIDCOMM, name="keylist-update")
    async def keylist_update(self, msg: Message, conn):
        """Handle keylist update message."""
        LOGGER.debug("Received keylist update message: %s", msg.pretty_print())
        response = Message.parse_obj(
            {
                "@type": self.type("keylist-update-response"),
                "updated": [
                    {
                        "recipient_key": update["recipient_key"],
                        "action": update["action"],
                        "result": "success",
                    }
                    for update in msg["updates"]
                ],
            }
        )
        LOGGER.debug("Sending keylist update response: %s", response.pretty_print())
        await conn.send_async(response)

    @route(name="keylist-update-response")
    @route(doc_uri=DIDCOMM, name="keylist-update-response")
    async def keylist_update_response(self, msg: Message, conn):
        """Handle keylist update response message."""
        LOGGER.debug("Received keylist update response message: %s", msg.pretty_print())
