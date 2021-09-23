""" Connections protocol from Indy HIPE 0031
    https://github.com/hyperledger/indy-hipe/tree/master/text/0031-connection-protocol
"""
from enum import Enum, auto

from aries_staticagent import (
    StaticConnection,
    Module,
    route,
    crypto,
    Message
)

from protocolstate import ProtocolStateMachine


class States(Enum):
    """ Possible states for connection protocol. """
    NULL = auto()
    INVITED = auto()
    REQUESTED = auto()
    RESPONDED = auto()
    COMPLETE = auto()


class Events(Enum):
    """ Possible events for connection protocol. """
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
    """ Possible roles for connection protocol. """
    NULL = auto()
    INVITER = auto()
    INVITEE = auto()


class ConnectionState(ProtocolStateMachine):
    """ State object of connection. Defines the state transitions for the
        protocol.
    """
    transitions = {
        Roles.INVITER: {
            States.NULL: {
                Events.SEND_INVITE: States.INVITED,
            },
            States.INVITED: {
                Events.SEND_INVITE: States.INVITED,
                Events.RECV_REQ: States.REQUESTED
            },
            States.REQUESTED: {
                Events.RECV_REQ: States.REQUESTED,
                Events.SEND_RESP: States.RESPONDED
            },
            States.RESPONDED: {
                Events.RECV_REQ: States.REQUESTED,
                Events.SEND_RESP: States.RESPONDED,
                Events.RECV_ACK: States.COMPLETE
            },
            States.COMPLETE: {
                Events.RECV_ACK: States.COMPLETE
            }
        },
        Roles.INVITEE: {
            States.NULL: {
                Events.RECV_INVITE: States.INVITED,
            },
            States.INVITED: {
                Events.RECV_INVITE: States.INVITED,
                Events.SEND_REQ: States.REQUESTED
            },
            States.REQUESTED: {
                Events.SEND_REQ: States.REQUESTED,
                Events.RECV_RESP: States.RESPONDED
            },
            States.RESPONDED: {
                Events.SEND_REQ: States.REQUESTED,
                Events.RECV_RESP: States.RESPONDED,
                Events.SEND_ACK: States.COMPLETE
            },
            States.COMPLETE: {
                Events.SEND_ACK: States.COMPLETE
            }
        }
    }

    def __init__(self):
        # Starting state for this protocol
        super().__init__()
        self.state = States.NULL
        self.role = Roles.NULL


class Connections(Module):
    """ Module for Connection Protocol """
    DOC_URI = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/'
    PROTOCOL = 'connections'
    VERSION = '1.0'

    def __init__(self, endpoint=None, dispatcher=None, connections=None):
        super().__init__()
        self.endpoint = endpoint
        self.connections = connections if connections else {}

        # This isn't a hack per se but it does allow us to have multiple
        # Connections with the same underlying routing which is helpful for
        # testing the connections protocol.
        self.dispatcher = dispatcher

    def create_invitation(self):
        """ Create and return an invite. """
        conn_vk, conn_sk = crypto.create_keypair()
        connection = StaticConnection(
            conn_vk,
            conn_sk,
            dispatcher=self.dispatcher
        )
        conn_vk_b58 = crypto.bytes_to_b58(conn_vk)
        self.connections[conn_vk_b58] = connection
        connection.state = ConnectionState()
        connection.state.role = Roles.INVITER
        connection.state.transition(Events.SEND_INVITE)
        invitation = Message({
            '@type': self.type('invitation'),
            'label': 'static-iiw',
            'recipientKeys': [conn_vk_b58],
            'serviceEndpoint': self.endpoint,
            'routingKeys': []
        })
        invitation_url = '{}?c_i={}'.format(
            self.endpoint,
            crypto.bytes_to_b64(invitation.serialize().encode())
        )
        return connection, invitation_url

    @route
    async def invitation(self, msg, _agent):
        """ Process an invitation. """
        print(msg.pretty_print())
        their_conn_key = msg['recipientKeys'][0]
        my_vk, my_sk = crypto.create_keypair()
        new_connection = StaticConnection(
            my_vk,
            my_sk,
            msg['recipientKeys'][0],
            msg['serviceEndpoint'],
            dispatcher=self.dispatcher
        )
        new_connection.did = crypto.bytes_to_b58(my_vk[:16])
        new_connection.vk_b58 = crypto.bytes_to_b58(my_vk)
        new_connection.state = ConnectionState()
        new_connection.state.role = Roles.INVITEE
        new_connection.state.transition(Events.RECV_INVITE)

        self.connections[their_conn_key] = new_connection
        await new_connection.send_async({
            '@type': self.type('request'),
            'label': 'apts-demo-agent-as-invitee',
            'connection': {
                'DID': new_connection.did,
                'DIDDoc': {
                    "@context": "https://w3id.org/did/v1",
                    "id": new_connection.did,
                    "publicKey": [{
                        "id": new_connection.did + "#keys-1",
                        "type": "Ed25519VerificationKey2018",
                        "controller": new_connection.did,
                        "publicKeyBase58": new_connection.vk_b58
                    }],
                    "service": [{
                        "id": new_connection.did + ";indy",
                        "type": "IndyAgent",
                        "recipientKeys": [new_connection.vk_b58],
                        "routingKeys": [],
                        "serviceEndpoint": self.endpoint,
                    }],
                }
            }
        })

        new_connection.state.transition(Events.SEND_REQ)

    @route
    async def request(self, msg, _agent):
        """ Process a request. """
        print(msg.pretty_print())
        connection = self.connections[msg.mtc.ad['recip_vk']]
        connection.state.transition(Events.RECV_REQ)

        # Old connection keys, need to sign new keys with these
        conn_vk, conn_sk = connection.my_vk, connection.my_sk

        # Relationship keys, replacing connection keys
        my_vk, my_sk = crypto.create_keypair()

        # Update connection
        connection.my_vk, connection.my_sk = my_vk, my_sk
        connection.did = crypto.bytes_to_b58(my_vk[:16])
        connection.vk_b58 = crypto.bytes_to_b58(my_vk)
        connection.their_did = msg['connection']['DIDDoc']['publicKey'][0]['controller']
        connection.their_vk = crypto.b58_to_bytes(
            msg['connection']['DIDDoc']['publicKey'][0]['publicKeyBase58']
        )
        connection.endpoint = msg['connection']['DIDDoc']['service'][0]['serviceEndpoint']

        del self.connections[msg.mtc.ad['recip_vk']]
        self.connections[connection.vk_b58] = connection

        # Prepare response
        connection_block = {
            'DID': connection.did,
            'DIDDoc': {
                "@context": "https://w3id.org/did/v1",
                "id": connection.did,
                "publicKey": [{
                    "id": connection.did + "#keys-1",
                    "type": "Ed25519VerificationKey2018",
                    "controller": connection.did,
                    "publicKeyBase58": connection.vk_b58
                }],
                "service": [{
                    "id": connection.did + ";indy",
                    "type": "IndyAgent",
                    "recipientKeys": [connection.vk_b58],
                    "routingKeys": [],
                    "serviceEndpoint": self.endpoint,
                }],
            }
        }

        connection.state.transition(Events.SEND_RESP)

        await connection.send_async({
            '@type': self.type('response'),
            '~thread': {
                'thid': msg.id,
                'sender_order': 0
            },
            'connection~sig': crypto.sign_message_field(
                connection_block,
                crypto.bytes_to_b58(conn_vk),
                conn_sk
            )
        })


    @route
    async def response(self, msg, _agent):
        """ Process a response. """
        print("Got response:", msg.pretty_print())
        their_conn_key = msg['connection~sig']['signer']
        connection = self.connections[their_conn_key]

        connection.state.transition(Events.RECV_RESP)

        msg['connection'] = crypto.verify_signed_message_field(msg['connection~sig'])
        del msg['connection~sig']
        print("Got response (sig unpacked)", msg.pretty_print())

        # Update connection
        del self.connections[their_conn_key]
        connection.their_did = msg['connection']['DIDDoc']['publicKey'][0]['controller']
        connection.their_vk = crypto.b58_to_bytes(
            msg['connection']['DIDDoc']['publicKey'][0]['publicKeyBase58']
        )
        connection.endpoint = msg['connection']['DIDDoc']['service'][0]['serviceEndpoint']
        self.connections[connection.vk_b58] = connection

        connection.state.transition(Events.SEND_ACK)

        await connection.send_async({
            '@type': self.type('ack'),
            'status': 'OK',
            '~thread': {
                'thid': msg.id
            }
        })


    @route
    async def ack(self, msg, _agent):
        """ Process an ack. """
        print(msg.pretty_print())
        connection = self.connections[msg.mtc.ad['recip_vk']]
        connection.state.transition(Events.RECV_ACK)