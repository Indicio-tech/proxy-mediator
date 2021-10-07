import asyncio
from typing import List, Optional
from aries_staticagent.module import Module, ModuleRouter
from ..connections import Connection
from ..error import problem_reporter, Reportable


class MediationError(Reportable):
    """Base Exception for mediation related errors."""


class RequestAlreadyPending(MediationError):
    """Raised when mediation request is already pending."""

    code = "request-already-pending"


class UnexpectedMediationGrant(MediationError):
    """Raised when mediation grant message received unexpectedly."""

    code = "unexpected-mediation-grant"


class ExternalMediationNotEstablished(MediationError):
    """
    Raised when a mediation request is received before mediation with
    external mediator is established.
    """

    code = "external-mediation-not-established"


class MediationRequest:
    def __init__(self, connection: Connection):
        self.connection = connection
        self._event = asyncio.Event()

    async def completed(self):
        await self._event.wait()

    def complete(self):
        self._event.set()

    def is_complete(self):
        return self._event.is_set()


class CoordinateMediation(Module):
    doc_uri = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
    protocol = "coordinate-mediation"
    version = "1.0"
    route = ModuleRouter()

    def __init__(self):
        super().__init__()
        self.external_mediator_endpoint: Optional[str] = None
        self.external_mediator_routing_keys: Optional[List[str]] = None
        self.external_pending_request: Optional[MediationRequest] = None
        self.agent_request_received: bool = False

    async def request_mediation_from_external(self, external_conn: Connection):
        """Request mediation from the external mediator."""
        if self.external_pending_request:
            raise RequestAlreadyPending(
                "Mediation request already pending to "
                f"{self.external_pending_request.connection}"
            )

        self.external_pending_request = MediationRequest(external_conn)
        await external_conn.send_async({"@type": self.type("mediate-request")})
        await self.external_pending_request.completed()

    @route(name="mediate-request")
    @problem_reporter(exceptions=MediationError)
    async def mediate_request(self, msg, conn):
        """Handle mediation request message."""
        if (
            not self.external_pending_request
            or not self.external_pending_request.is_complete()
        ):
            raise ExternalMediationNotEstablished(
                "Mediation with external mediator not yet established"
            )

        self.agent_request_received = True
        await conn.send_async(
            {
                "@type": self.type("mediate-grant"),
                "endpoint": self.external_mediator_endpoint,
                "routing_keys": self.external_mediator_routing_keys,
            }
        )

    @route(name="mediate-grant")
    @problem_reporter(exceptions=MediationError)
    async def mediate_grant(self, msg, conn):
        """Handle mediation grant message."""
        if not self.external_pending_request:
            raise UnexpectedMediationGrant(
                "Received unexpected mediation grant message"
            )
        self.external_mediator_endpoint = msg["endpoint"]
        self.external_mediator_routing_keys = msg["routing_keys"]
        self.external_pending_request.complete()
