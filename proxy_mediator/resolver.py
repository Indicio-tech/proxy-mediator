"""DID Resolver."""

from typing import Literal
import base58
from multiformats import multibase, multicodec
from pydid import DIDDocument, DIDUrl, Resource, VerificationMethod
from did_peer_2 import resolve as resolve_peer2
from did_peer_4 import resolve as resolve_peer4


class DIDResolutionError(Exception):
    """Represents an error from a DID Resolver."""


class DIDNotFound(DIDResolutionError):
    """Represents a DID not found error."""


class DIDMethodNotSupported(DIDResolutionError):
    """Represents a DID method not supported error."""


class DIDResolver:
    """DID Resolver.

    Supports did:peer:2 and did:peer:4.
    """

    def __init__(self):
        """Initialize the resolver."""
        self.resolvers = {
            "did:peer:2": resolve_peer2,
            "did:peer:4": resolve_peer4,
            "did:key:": DIDKey.resolve,
        }

    async def resolve(self, did: str) -> dict:
        """Resolve a DID."""
        for prefix, resolver in self.resolvers.items():
            if did.startswith(prefix):
                return resolver(did)

        raise DIDMethodNotSupported(f"No resolver found for DID {did}")

    async def resolve_and_parse(self, did: str) -> DIDDocument:
        """Resolve a DID and parse the DID document."""
        doc = await self.resolve(did)
        return DIDDocument.deserialize(doc)

    async def resolve_and_dereference(self, did_url: str) -> Resource:
        """Resolve a DID URL and dereference the identifier."""
        url = DIDUrl.parse(did_url)
        if not url.did:
            raise DIDResolutionError("Invalid DID URL; must be absolute")

        doc = await self.resolve_and_parse(url.did)
        return doc.dereference(url)

    async def resolve_and_dereference_verification_method(
        self, did_url: str
    ) -> VerificationMethod:
        """Resolve a DID URL and dereference the identifier."""
        resource = await self.resolve_and_dereference(did_url)
        if not isinstance(resource, VerificationMethod):
            raise DIDResolutionError("Resource is not a verification method")

        return resource


class DIDKey:
    """DID Key resolver and helper class."""

    @staticmethod
    def resolve(did: str) -> dict:
        """Resolve a did:key DID."""
        if not did.startswith("did:key:"):
            raise ValueError(f"Invalid did:key: {did}")

        multikey = did.split("did:key:", 1)[1]
        key_id = f"{did}#{multikey}"

        verification_method = {
            "id": key_id,
            "type": "Multikey",
            "controller": did,
            "publicKeyMultibase": multikey,
        }

        if multikey.startswith("z6Mk"):
            return {
                "@context": "https://www.w3.org/ns/did/v1",
                "id": did,
                "verificationMethod": [verification_method],
                "authentication": [key_id],
                "assertionMethod": [key_id],
            }
        elif multikey.startswith("z6LS"):
            return {
                "@context": "https://www.w3.org/ns/did/v1",
                "id": did,
                "verificationMethod": [verification_method],
                "keyAgreement": [key_id],
            }

        raise ValueError(f"Unsupported key type: {multikey}")

    def __init__(self, multikey: str):
        """Initialize the DID Key."""
        self.multikey = multikey

    @classmethod
    def from_public_key_b58(
        cls, public_key: str, key_type: Literal["ed25519-pub", "x25519-pub"]
    ) -> "DIDKey":
        """Create a DID Key from a public key."""
        key_bytes = base58.b58decode(public_key)
        multikey = multibase.encode(multicodec.wrap(key_type, key_bytes), "base58btc")
        return cls(multikey)

    @property
    def key_id(self):
        """Get the key ID."""
        return f"did:key:{self.multikey}#{self.multikey}"
