"""Implementation of OOB and DID Exchange protocols."""

import json
import logging
from typing import Any, Dict, Optional, Tuple
import uuid

from aries_staticagent import Message, ModuleRouter, Target, crypto
import base58
from multiformats import multibase, multicodec
from pydid import DIDDocument, Service, VerificationMethod, deserialize_document
from pydid.service import DIDCommV1Service
from pydid.verification_method import (
    Ed25519VerificationKey2018,
    Ed25519VerificationKey2020,
    Multikey,
)

from ..doc_normalization import LegacyDocCorrections

from ..connection import Connection, ConnectionMachine
from ..encode import b64_to_bytes, b64_to_dict, bytes_to_b64, dict_to_b64, unpad
from ..error import ProtocolError
from .connections import Connections
from .constants import DIDCOMM, DIDCOMM_OLD
from ..resolver import DIDResolver


LOGGER = logging.getLogger(__name__)


def verkey_b58_to_didkey(verkey: str) -> str:
    """Convert verkey as b58 str to did key."""
    return verkey_to_didkey(crypto.b58_to_bytes(verkey))


def verkey_to_didkey(verkey: bytes) -> str:
    """Convert verkey to didkey."""
    return "did:key:" + multibase.encode(
        multicodec.wrap("ed25519-pub", verkey), "base58btc"
    )


def didkey_to_verkey(didkey: str) -> bytes:
    """Convert didkey to verkey."""
    try:
        multikey = didkey[8:].split("#")[0]
    except Exception:
        raise ProtocolError(f"Invalid did:key: {didkey}")

    codec, unwrapped = multicodec.unwrap(multibase.decode(multikey))
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
        """Process an invitation."""
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

    def vm_to_verkey(self, vm: VerificationMethod) -> bytes:
        """Convert a verification method to a verkey."""
        LOGGER.debug("Converting VM to verkey: %s", vm.__class__.__name__)
        if isinstance(vm, Ed25519VerificationKey2018):
            return base58.b58decode(vm.public_key_base58)
        elif isinstance(vm, Ed25519VerificationKey2020):
            if vm.public_key_multibase.startswith("z6Mk"):
                codec, verkey = multicodec.unwrap(
                    multibase.decode(vm.public_key_multibase)
                )
                assert codec.name == "ed25519-pub"
                return verkey
            elif vm.public_key_multibase.startswith("z"):
                return multibase.decode(vm.public_key_multibase)
            else:
                raise ValueError(
                    f"Unsupported multibase encoded value: {vm.public_key_multibase}"
                )
        elif isinstance(vm, Multikey):
            codec, verkey = multicodec.unwrap(multibase.decode(vm.public_key_multibase))
            if codec.name == "ed25519-pub":
                return verkey

            raise ValueError(f"Unsupported multicodec: {codec.name}")
        raise ValueError(f"Unsupported verification method: {vm.type}")

    async def target_from_doc(
        self,
        doc: DIDDocument,
        type: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> Target:
        """Create a target from a DID Document."""

        def _filter(service: Service) -> bool:
            """Filter services."""
            if not isinstance(service, DIDCommV1Service):
                return False

            return (
                service.type == type
                or "did-communication"
                and service.service_endpoint.startswith(protocol or "http")
            )

        service = next(filter(_filter, doc.service or []))
        assert isinstance(service, DIDCommV1Service)
        vm = doc.dereference(service.recipient_keys[0])
        if not isinstance(vm, VerificationMethod):
            raise ProtocolError(
                "Invalid verification method reference in recipient keys"
            )
        verkey = self.vm_to_verkey(vm)

        return Target(
            their_vk=verkey,
            endpoint=service.service_endpoint,
        )

    async def doc_from_request_or_response(
        self, message: Message
    ) -> Tuple[DIDDocument, Optional[bytes]]:
        """Extract DID Document from a DID Exchange Request or Response."""
        if "did_doc~attach" in message:
            verified, signer = self.verify_signed_attachment(message["did_doc~attach"])
            if not verified:
                raise ProtocolError("Invalid signature on DID Doc")

            doc = b64_to_dict(message["did_doc~attach"]["data"]["base64"])
            normalized = LegacyDocCorrections.apply(doc)
            return deserialize_document(normalized), signer

        elif "response" in message.type and "did_rotate~attach" in message:
            verified, signer = self.verify_signed_attachment(
                message["did_rotate~attach"]
            )
            if not verified:
                raise ProtocolError("Invalid signature on DID Rotattion")

        resolver = DIDResolver()
        return await resolver.resolve_and_parse(message["did"]), None

    @route
    @route(doc_uri=DIDCOMM_OLD)
    async def request(self, msg: Message, invite_connection: Connection):
        """Handle a request."""
        LOGGER.debug("Received request: %s", msg.pretty_print())
        assert msg.mtc.recipient

        # Pop invite connection
        if not invite_connection.multiuse:
            self.connections.pop(invite_connection.verkey_b58)

        doc, signer = await self.doc_from_request_or_response(msg)
        target = await self.target_from_doc(doc)

        ConnectionMachine(invite_connection).receive_request()

        # Create relationship connection
        connection = self.new_connection(
            invite_connection=invite_connection,
            target=target,
        )
        connection.diddoc = doc.serialize()

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

        doc, signer = await self.doc_from_request_or_response(msg)
        target = await self.target_from_doc(doc)

        assert conn.invitation_key
        if not signer == didkey_to_verkey(conn.invitation_key):
            raise ProtocolError("Connection response not signed by invitation key")

        LOGGER.debug("Attached DID Doc: %s", json.dumps(doc.serialize(), indent=2))

        # Update connection
        assert conn.target
        conn.target = target
        conn.diddoc = doc.serialize()
        conn.complete()

        complete = Message.parse_obj(
            {
                "@type": self.type("complete"),
                "~thread": {
                    "thid": msg.thread["thid"],
                    "pthid": (
                        msg.thread["pthid"]
                        if "pthid" in msg.thread
                        else msg.thread["thid"]
                    ),
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
