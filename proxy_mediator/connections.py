""" Connections protocol from Indy HIPE 0031
    https://github.com/hyperledger/indy-hipe/tree/master/text/0031-connection-protocol
"""
from enum import Enum, auto
from typing import Dict

from aries_staticagent import Connection as AsaPyConn, Message, crypto
from aries_staticagent.connection import Target
from aries_staticagent.module import Module, ModuleRouter

from .protocolstate import ProtocolStateMachine


class States(Enum):
    """Possible states for connection protocol."""

    NULL = auto()
    INVITED = auto()
    REQUESTED = auto()
    RESPONDED = auto()
    COMPLETE = auto()


class Events(Enum):
    """Possible events for connection protocol."""

    # Inviter Role
    SEND_INVITE = auto()
    RECV_REQ = auto()
    SEND_RESP = auto()
    RECV_ACK = auto()

    # Invitee Role
    RECV_INVITE = auto()
    SEND_REQ = auto()
    RECV_RESP = auto()
    SEND_ACK = auto()

    # Either
    SEND_ERR = auto()
    RECV_ERR = auto()


class Roles(Enum):
    """Possible roles for connection protocol."""

    NULL = auto()
    INVITER = auto()
    INVITEE = auto()


class ConnectionState(ProtocolStateMachine):
    """State object of connection. Defines the state transitions for the
    protocol.
    """

    transitions = {
        Roles.INVITER: {
            States.NULL: {Events.SEND_INVITE: States.INVITED},
            States.INVITED: {
                Events.SEND_INVITE: States.INVITED,
                Events.RECV_REQ: States.REQUESTED,
            },
            States.REQUESTED: {
                Events.RECV_REQ: States.REQUESTED,
                Events.SEND_RESP: States.RESPONDED,
            },
            States.RESPONDED: {
                Events.RECV_REQ: States.REQUESTED,
                Events.SEND_RESP: States.RESPONDED,
                Events.RECV_ACK: States.COMPLETE,
            },
            States.COMPLETE: {Events.RECV_ACK: States.COMPLETE},
        },
        Roles.INVITEE: {
            States.NULL: {Events.RECV_INVITE: States.INVITED},
            States.INVITED: {
                Events.RECV_INVITE: States.INVITED,
                Events.SEND_REQ: States.REQUESTED,
            },
            States.REQUESTED: {
                Events.SEND_REQ: States.REQUESTED,
                Events.RECV_RESP: States.RESPONDED,
            },
            States.RESPONDED: {
                Events.SEND_REQ: States.REQUESTED,
                Events.RECV_RESP: States.RESPONDED,
                Events.SEND_ACK: States.COMPLETE,
            },
            States.COMPLETE: {Events.SEND_ACK: States.COMPLETE},
        },
    }

    def __init__(self):
        # Starting state for this protocol
        super().__init__()
        self.state = States.NULL
        self.role = Roles.NULL


class Connection(AsaPyConn):
    """Wrapper around Static Agent library connection to provide state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = ConnectionState()


class Connections(Module):
    """Module for Connection Protocol"""

    doc_uri = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
    protocol = "connections"
    version = "1.0"
    route = ModuleRouter()

    def __init__(self, endpoint=None, dispatcher=None, connections=None):
        super().__init__()
        self.endpoint = endpoint
        self.connections: Dict[str, Connection] = connections if connections else {}

        # This isn't a hack per se but it does allow us to have multiple
        # Connections with the same underlying routing which is helpful for
        # testing the connections protocol.
        self.dispatcher = dispatcher

    def create_invitation(self):
        """Create and return an invite."""
        connection = Connection.random(dispatcher=self.dispatcher)
        self.connections[connection.verkey_b58] = connection
        connection.state.role = Roles.INVITER
        connection.state.transition(Events.SEND_INVITE)
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
        return connection, invitation_url

    @route
    async def invitation(self, msg, _conn):
        """Process an invitation."""
        print(msg.pretty_print(), flush=True)
        invitation_key = msg["recipientKeys"][0]
        new_connection = Connection.random(
            target=Target(
                their_vk=msg["recipientKeys"][0],
                endpoint=msg["serviceEndpoint"],
            ),
            dispatcher=self.dispatcher,
        )
        new_connection.state.role = Roles.INVITEE
        new_connection.state.transition(Events.RECV_INVITE)

        self.connections[invitation_key] = new_connection
        await new_connection.send_async(
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
                                "serviceEndpoint": self.endpoint,
                            }
                        ],
                    },
                },
            }
        )

        new_connection.state.transition(Events.SEND_REQ)

    @route
    async def request(self, msg: Message, conn):
        """Process a request."""
        print(msg.pretty_print(), flush=True)
        assert msg.mtc.recipient

        # Pop invite connection
        invite_connection = self.connections.pop(msg.mtc.recipient)
        invite_connection.state.transition(Events.RECV_REQ)

        # Create relationship connection
        connection = Connection.random(
            Target(
                endpoint=msg["connection"]["DIDDoc"]["service"][0]["serviceEndpoint"],
                recipients=msg["connection"]["DIDDoc"]["service"][0]["recipientKeys"],
            ),
            dispatcher=self.dispatcher,
        )

        # Update connections
        self.connections[connection.verkey_b58] = connection
        connection.state = invite_connection.state

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

        connection.state.transition(Events.SEND_RESP)

        await connection.send_async(
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

    @route
    async def response(self, msg: Message, conn):
        """Process a response."""
        print("Got response:", msg.pretty_print(), flush=True)
        their_conn_key = msg["connection~sig"]["signer"]
        connection = self.connections.pop(their_conn_key)

        connection.state.transition(Events.RECV_RESP)

        connection_block = crypto.verify_signed_message_field(msg["connection~sig"])
        print("Unpacked connection block", connection_block, flush=True)

        # Update connection
        assert connection.target
        connection.target.update(
            recipients=msg["connection"]["DIDDoc"]["service"][0]["recipientKeys"],
            endpoint=msg["connection"]["DIDDoc"]["service"][0]["serviceEndpoint"],
        )
        self.connections[connection.verkey_b58] = connection

        connection.state.transition(Events.SEND_ACK)

        # TODO Use trustping
        await connection.send_async(
            {"@type": self.type("ack"), "status": "OK", "~thread": {"thid": msg.id}}
        )

    # TODO Use trustping
    @route("did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping")
    async def ack(self, msg: Message, conn):
        """Process a trustping."""
        print(msg.pretty_print())
        assert msg.mtc.recipient
        connection = self.connections[msg.mtc.recipient]
        connection.state.transition(Events.RECV_ACK)
        await conn.send_async(
            {
                "@type": self.type(protocol="trust_ping", name="ping_response"),
                "~thread": {"thid": msg.id},
            }
        )
