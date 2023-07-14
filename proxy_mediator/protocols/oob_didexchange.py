"""Implementation of OOB and DID Exchange protocols."""

import json
import logging
from typing import Any, Dict, Optional
import uuid

from aries_staticagent import Message, ModuleRouter, Target, crypto
from multiformats import multibase, multicodec

from ..connection import Connection, ConnectionMachine
from ..encode import b64_to_bytes, b64_to_dict, bytes_to_b64, dict_to_b64, unpad
from ..error import ProtocolError
from .connections import Connections
from .constants import DIDCOMM, DIDCOMM_OLD


LOGGER = logging.getLogger(__name__)


def verkey_to_didkey(verkey: bytes) -> str:
    """Convert verkey to didkey."""
    return "did:key:" + multibase.encode(
        multicodec.wrap("ed25519-pub", verkey), "base58btc"
    )


def didkey_to_verkey(didkey: str) -> bytes:
    """Convert didkey to verkey."""
    codec, unwrapped = multicodec.unwrap(multibase.decode(didkey[8:]))
    if codec.name != "ed25519-pub":
        raise ProtocolError(f"Unsupported did:key: {codec.name}")

    return unwrapped


class OobDidExchange(Connections):
    """Implementation of OOB and DID Exchange protocols."""

    protocol = f"{DIDCOMM}didexchange/1.0"
    route = ModuleRouter(protocol)
    oob_protocol = f"{DIDCOMM}out-of-band/1.0"

    def create_invitation(self, *, multiuse: bool = False):
        """Create a new invitation."""

        connection = self.new_connection(multiuse=multiuse)
        ConnectionMachine(connection).send_invite()
        invitation = Message.parse_obj(
            {
                "@type": f"{self.oob_protocol}/invitation",
                "label": "proxy-mediator",
                "handshake_protocols": [self.protocol],
                "services": [
                    {
                        "id": "#inline",
                        "type": "did-communication",
                        "recipientKeys": [verkey_to_didkey(connection.verkey)],
                        "serviceEndpoint": self.endpoint,
                        "routingKeys": [],
                    }
                ],
            }
        )
        invitation_url = "{}?oob={}".format(
            self.endpoint, crypto.bytes_to_b64(invitation.serialize().encode())
        )
        LOGGER.debug("Created invitation: %s", invitation_url)
        return connection, invitation_url

    def signed_attachment(
        self, verkey: bytes, sigkey: bytes, attachment: Dict[str, Any]
    ):
        """Create a signed attachment."""

        didkey = verkey_to_didkey(verkey)
        protected = dict_to_b64(
            {
                "alg": "EdDSA",
                "jwk": {
                    "crv": "Ed25519",
                    "kid": didkey,
                    "kty": "OKP",
                    "x": bytes_to_b64(verkey, urlsafe=True, pad=False),
                },
                "kid": didkey,
            },
            urlsafe=True,
            pad=False,
        )
        data = dict_to_b64(attachment, urlsafe=True, pad=True)
        sig_data = unpad(data)

        return {
            "@id": str(uuid.uuid4()),
            "mime-type": "application/json",
            "data": {
                "base64": data,
                "jws": {
                    "header": {
                        "kid": didkey,
                    },
                    "protected": protected,
                    "signature": bytes_to_b64(
                        crypto.sign_message(f"{protected}.{sig_data}".encode(), sigkey),
                        urlsafe=True,
                        pad=False,
                    ),
                },
            },
        }

    def verify_signed_attachment(self, signed_attachment: Dict[str, Any]):
        """Verify a signed attachment."""
        data = signed_attachment["data"]["base64"]
        sig_data = unpad(data)
        protected = signed_attachment["data"]["jws"]["protected"]
        pub_key_bytes = b64_to_bytes(
            json.loads(b64_to_bytes(protected, urlsafe=True))["jwk"]["x"], urlsafe=True
        )
        sig = signed_attachment["data"]["jws"]["signature"]

        if not crypto.verify_signed_message(
            b64_to_bytes(sig, urlsafe=True) + f"{protected}.{sig_data}".encode(),
            pub_key_bytes,
        ):
            return False, pub_key_bytes

        return True, pub_key_bytes

    async def receive_invite_url(self, invite: str, **kwargs):
        """Process an invitation from a URL."""
        invite_msg = Message.parse_obj(b64_to_dict(invite.split("oob=", 1)[1]))
        return await self.receive_invite(invite_msg, **kwargs)

    async def receive_invite(self, invite: Message, *, endpoint: Optional[str] = None):
        LOGGER.debug("Received invitation: %s", invite.pretty_print())
        service = invite["services"][0]
        invitation_key = service["recipientKeys"][0]
        new_connection = self.new_connection(
            invitation_key=invitation_key,
            target=Target(
                their_vk=didkey_to_verkey(service["recipientKeys"][0]),
                endpoint=service["serviceEndpoint"],
            ),
        )
        ConnectionMachine(new_connection).receive_invite()

        request = Message.parse_obj(
            {
                "@type": self.type("request"),
                "label": "proxy-mediator",
                "~thread": {
                    "pthid": invite["@id"],
                },
                "did": new_connection.did,
                "did_doc~attach": self.signed_attachment(
                    new_connection.verkey,
                    new_connection.sigkey,
                    self.doc_for_connection(new_connection, endpoint=endpoint),
                ),
            },
        )
        LOGGER.debug("Sending request: %s", request.pretty_print())
        ConnectionMachine(new_connection).send_request()
        await new_connection.send_async(request, return_route="all")

        return new_connection

    @route
    @route(doc_uri=DIDCOMM_OLD)
    async def request(self, msg: Message, invite_connection: Connection):
        LOGGER.debug("Received request: %s", msg.pretty_print())
        assert msg.mtc.recipient

        # Pop invite connection
        if not invite_connection.multiuse:
            self.connections.pop(invite_connection.verkey_b58)

        verified, signer = self.verify_signed_attachment(msg["did_doc~attach"])
        if not verified:
            raise ProtocolError("Invalid signature on DID Doc")

        doc = b64_to_dict(msg["did_doc~attach"]["data"]["base64"])

        ConnectionMachine(invite_connection).receive_request()

        # Create relationship connection
        connection = self.new_connection(
            invite_connection=invite_connection,
            target=Target(
                endpoint=doc["service"][0]["serviceEndpoint"],
                recipients=doc["service"][0]["recipientKeys"],
            ),
        )
        connection.diddoc = doc

        ConnectionMachine(connection).send_response()

        response = Message.parse_obj(
            {
                "@type": self.type("response"),
                "~thread": {"thid": msg.id, "pthid": msg.thread["pthid"]},
                "did": connection.did,
                "did_doc~attach": self.signed_attachment(
                    invite_connection.verkey,
                    invite_connection.sigkey,
                    self.doc_for_connection(connection),
                ),
            },
        )
        LOGGER.debug("Sending response: %s", response.pretty_print())
        await connection.send_async(response)
        connection.complete()

    @route
    @route(doc_uri=DIDCOMM_OLD)
    async def response(self, msg: Message, conn: Connection):
        """Process a response."""
        LOGGER.debug("Received response: %s", msg.pretty_print())
        ConnectionMachine(conn).receive_response()

        verified, signer = self.verify_signed_attachment(msg["did_doc~attach"])
        if not verified:
            raise ProtocolError("Invalid signature on DID Doc")

        doc = b64_to_dict(msg["did_doc~attach"]["data"]["base64"])
        assert conn.invitation_key
        if not signer == didkey_to_verkey(conn.invitation_key):
            raise ProtocolError("Connection response not signed by invitation key")

        LOGGER.debug("Attached DID Doc: %s", json.dumps(doc, indent=2))

        # Update connection
        assert conn.target
        conn.target.update(
            recipients=doc["service"][0]["recipientKeys"],
            endpoint=doc["service"][0]["serviceEndpoint"],
        )
        conn.diddoc = doc
        conn.complete()

        complete = Message.parse_obj(
            {
                "@type": self.type("complete"),
                "~thread": {
                    "thid": msg.thread["thid"],
                    "pthid": msg.thread["pthid"]
                    if "pthid" in msg.thread
                    else msg.thread["thid"],
                },
            }
        )
        LOGGER.debug("Sending ping: %s", complete.pretty_print())
        ConnectionMachine(conn).send_complete()
        await conn.send_async(complete, return_route="all")

    @route
    @route(doc_uri=DIDCOMM_OLD)
    async def complete(self, msg: Message, conn: Connection):
        """Receive a complete message."""
        LOGGER.debug("Received complete: %s", msg.pretty_print())
        ConnectionMachine(conn).receive_complete()
