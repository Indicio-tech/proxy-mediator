""" Connections protocol from Aries RFC 0160
    https://github.com/hyperledger/aries-rfcs/blob/main/features/0160-connection-protocol
"""

import asyncio
from base64 import urlsafe_b64decode
from contextvars import ContextVar
import json
import logging
from typing import Dict, Optional

from ..agent import Connection, Agent, ConnectionMachine
from aries_staticagent import Message, crypto
from aries_staticagent.connection import Target
from aries_staticagent.module import Module, ModuleRouter
from ..error import ProtocolError


LOGGER = logging.getLogger(__name__)
VAR: ContextVar["Connections"] = ContextVar("connections")


class Connections(Module):
    """Module for Connection Protocol"""

    protocol = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/connections/1.0"
    route = ModuleRouter(protocol)

    @classmethod
    def get(cls) -> "Connections":
        return VAR.get()

    @classmethod
    def set(cls, value: "Connections"):
        VAR.set(value)

    def __init__(self, endpoint=None, connections=None):
        super().__init__()
        self.endpoint = endpoint
        self.connections: Dict[str, Connection] = connections if connections else {}

        self.mediator_connection: Optional[Connection] = None
        self._mediator_connection_event = asyncio.Event()
        self.agent_connection: Optional[Connection] = None
        self.agent_invitation: Optional[str] = None

    def create_invitation(self, *, multiuse: bool = False):
        """Create and return an invite."""
        agent = Agent.get()
        connection = agent.new_connection(multiuse=multiuse)
        ConnectionMachine(connection).send_invite()
        invitation = Message.parse_obj(
            {
                "@type": self.type("invitation"),
                "label": "proxy-mediator",
                "recipientKeys": [connection.verkey_b58],
                "serviceEndpoint": self.endpoint,
                "routingKeys": [],
            }
        )
        invitation_url = "{}?c_i={}".format(
            self.endpoint, crypto.bytes_to_b64(invitation.serialize().encode())
        )
        LOGGER.debug("Created invitation: %s", invitation_url)
        return connection, invitation_url

    async def mediator_invite_received(self) -> Connection:
        """Await event notifying that mediator invite has been received."""
        await self._mediator_connection_event.wait()
        if not self.mediator_connection:
            raise RuntimeError("Mediator connection event triggered without set")
        return self.mediator_connection

    async def receive_mediator_invite(self, invite: str) -> Connection:
        """Receive mediator invitation."""
        self.mediator_connection = await self.receive_invite_url(invite, endpoint="")
        self._mediator_connection_event.set()
        return self.mediator_connection

    async def receive_invite_url(self, invite: str, **kwargs):
        """Process an invitation from a URL."""
        invite_msg = Message.parse_obj(
            json.loads(urlsafe_b64decode(invite.split("c_i=")[1]))
        )
        return await self.receive_invite(invite_msg, **kwargs)

    async def receive_invite(self, invite: Message, *, endpoint: str = None):
        """Process an invitation."""
        agent = Agent.get()
        LOGGER.debug("Received invitation: %s", invite.pretty_print())
        invitation_key = invite["recipientKeys"][0]
        new_connection = agent.new_connection(
            invitation_key=invitation_key,
            target=Target(
                their_vk=invite["recipientKeys"][0],
                endpoint=invite["serviceEndpoint"],
            ),
        )
        ConnectionMachine(new_connection).receive_invite()

        request = Message.parse_obj(
            {
                "@type": self.type("request"),
                "label": "proxy-mediator",
                "connection": {
                    "DID": new_connection.did,
                    "DIDDoc": {
                        "@context": "https://w3id.org/did/v1",
                        "id": new_connection.did,
                        "publicKey": [
                            {
                                "id": new_connection.did + "#keys-1",
                                "type": "Ed25519VerificationKey2018",
                                "controller": new_connection.did,
                                "publicKeyBase58": new_connection.verkey_b58,
                            }
                        ],
                        "service": [
                            {
                                "id": new_connection.did + "#indy",
                                "type": "IndyAgent",
                                "recipientKeys": [new_connection.verkey_b58],
                                "routingKeys": [],
                                "serviceEndpoint": endpoint
                                if endpoint is not None
                                else self.endpoint,
                            }
                        ],
                    },
                },
            }
        )
        LOGGER.debug("Sending request: %s", request.pretty_print())
        ConnectionMachine(new_connection).send_request()
        await new_connection.send_async(request, return_route="all")

        return new_connection

    @route
    async def request(self, msg: Message, invite_connection):
        """Process a request.

        For this handler, conn represents an ephemeral connection created for
        the invitation.
        """
        agent = Agent.get()
        LOGGER.debug("Received request: %s", msg.pretty_print())
        assert msg.mtc.recipient

        # Pop invite connection
        if not invite_connection.multiuse:
            agent.delete_connection(invite_connection)

        ConnectionMachine(invite_connection).receive_request()

        # Create relationship connection
        connection = agent.new_connection(
            invite_connection=invite_connection,
            target=Target(
                endpoint=msg["connection"]["DIDDoc"]["service"][0]["serviceEndpoint"],
                recipients=msg["connection"]["DIDDoc"]["service"][0]["recipientKeys"],
            ),
        )
        connection.diddoc = msg["connection"]["DIDDoc"]

        # Prepare response
        connection_block = {
            "DID": connection.did,
            "DIDDoc": {
                "@context": "https://w3id.org/did/v1",
                "id": connection.did,
                "publicKey": [
                    {
                        "id": connection.did + "#keys-1",
                        "type": "Ed25519VerificationKey2018",
                        "controller": connection.did,
                        "publicKeyBase58": connection.verkey_b58,
                    }
                ],
                "service": [
                    {
                        "id": connection.did + ";indy",
                        "type": "IndyAgent",
                        "recipientKeys": [connection.verkey_b58],
                        "routingKeys": [],
                        "serviceEndpoint": self.endpoint,
                    }
                ],
            },
        }

        ConnectionMachine(connection).send_response()

        response = Message.parse_obj(
            {
                "@type": self.type("response"),
                "~thread": {"thid": msg.id, "sender_order": 0},
                "connection~sig": crypto.sign_message_field(
                    connection_block,
                    invite_connection.verkey_b58,
                    invite_connection.sigkey,
                ),
            }
        )
        LOGGER.debug("Sending response: %s", response.pretty_print())
        LOGGER.debug(
            "Unsigned connection object: %s", json.dumps(connection_block, indent=2)
        )
        await connection.send_async(response)
        connection.complete()

    @route
    async def response(self, msg: Message, conn: Connection):
        """Process a response."""
        LOGGER.debug("Received response: %s", msg.pretty_print())
        ConnectionMachine(conn).receive_response()

        signer, connection_block = crypto.verify_signed_message_field(
            msg["connection~sig"]
        )
        if not signer == conn.invitation_key:
            raise ProtocolError("Connection response not signed by invitation key")

        LOGGER.debug(
            "Unpacked connection object: %s", json.dumps(connection_block, indent=2)
        )

        # Update connection
        assert conn.target
        conn.target.update(
            recipients=connection_block["DIDDoc"]["service"][0]["recipientKeys"],
            endpoint=connection_block["DIDDoc"]["service"][0]["serviceEndpoint"],
        )
        conn.diddoc = connection_block["DIDDoc"]
        conn.complete()

        ping = Message.parse_obj(
            {
                "@type": self.type(protocol="trust_ping", name="ping"),
                "~thread": {"thid": msg.id},
            }
        )
        LOGGER.debug("Sending ping: %s", ping.pretty_print())
        ConnectionMachine(conn).send_ping()
        await conn.send_async(ping, return_route="all")

    @route(protocol="trust_ping", version="1.0", name="ping")
    async def ping(self, msg: Message, conn):
        """Process a trustping."""
        LOGGER.debug("Received trustping: %s", msg.pretty_print())
        ConnectionMachine(conn).receive_ping()
        response = Message.parse_obj(
            {
                "@type": self.type(protocol="trust_ping", name="ping_response"),
                "~thread": {"thid": msg.id},
            }
        )
        LOGGER.debug("Sending ping response: %s", response.pretty_print())
        ConnectionMachine(conn).send_ping_response()
        await conn.send_async(response)

    @route(protocol="trust_ping", version="1.0", name="ping_response")
    async def ping_response(self, msg: Message, conn):
        """Process a trustping."""
        LOGGER.debug("Received trustping response: %s", msg.pretty_print())
        ConnectionMachine(conn).receive_ping_response()
