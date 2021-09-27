""" Connections protocol from Indy HIPE 0031
    https://github.com/hyperledger/indy-hipe/tree/master/text/0031-connection-protocol
"""
from typing import Dict

from aries_staticagent import Connection as AsaPyConn, Message, crypto
from aries_staticagent.connection import Target
from aries_staticagent.module import Module, ModuleRouter

from statemachine import StateMachine, State


class Connection(AsaPyConn):
    """Wrapper around Static Agent library connection to provide state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state: str = "null"


class ConnectionMachine(StateMachine):
    null = State("null", initial=True)
    invite_sent = State("invite_sent")
    invite_received = State("invited")
    request_sent = State("request_sent")
    request_received = State("requested")
    response_sent = State("response_sent")
    response_received = State("responded")
    complete = State("complete")

    send_invite = null.to(invite_sent)
    receive_request = invite_sent.to(request_received)
    send_response = request_received.to(response_sent)

    recieve_invite = null.to(invite_received)
    send_request = invite_received.to(request_sent)
    receive_response = request_sent.to(response_received)
    send_ack = response_received.to(complete)
    receive_ack = response_sent.to(complete)


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
        ConnectionMachine(new_connection).recieve_invite()

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

        ConnectionMachine(new_connection).send_request()

    @route
    async def request(self, msg: Message, conn):
        """Process a request."""
        print(msg.pretty_print(), flush=True)
        assert msg.mtc.recipient

        # Pop invite connection
        invite_connection = self.connections.pop(msg.mtc.recipient)
        ConnectionMachine(invite_connection).receive_request()

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

        ConnectionMachine(connection).send_response()

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
        ConnectionMachine(connection).receive_response()

        connection_block = crypto.verify_signed_message_field(msg["connection~sig"])
        print("Unpacked connection block", connection_block, flush=True)

        # Update connection
        assert connection.target
        connection.target.update(
            recipients=msg["connection"]["DIDDoc"]["service"][0]["recipientKeys"],
            endpoint=msg["connection"]["DIDDoc"]["service"][0]["serviceEndpoint"],
        )
        self.connections[connection.verkey_b58] = connection

        # TODO Use trustping
        await connection.send_async(
            {
                "@type": self.type(protocol="trust_ping", name="ping_response"),
                "~thread": {"thid": msg.id},
            }
        )
        ConnectionMachine(connection).send_ack()

    # TODO Use trustping
    @route("did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping")
    async def ack(self, msg: Message, conn):
        """Process a trustping."""
        print(msg.pretty_print(), flush=True)
        assert msg.mtc.recipient
        connection = self.connections[msg.mtc.recipient]
        ConnectionMachine(connection).receive_ack()
        await conn.send_async(
            {
                "@type": self.type(protocol="trust_ping", name="ping_response"),
                "~thread": {"thid": msg.id},
            }
        )
