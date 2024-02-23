"""Helpers for normalizing legacy DID Documents."""

from copy import deepcopy
from typing import List
from .resolver import DIDKey


class LegacyDocCorrections:
    """Legacy peer DID document corrections.

    Borrowed from: https://github.com/hyperledger/aries-cloudagent-python/blob/73dd7edad8b7c2373b2ce16397d664606695125a/aries_cloudagent/resolver/default/legacy_peer.py#L27

    These corrections align the document with updated DID spec and DIDComm
    conventions. This also helps with consistent processing of DID Docs.

    Input example:
    {
      "@context": "https://w3id.org/did/v1",
      "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ",
      "publicKey": [
        {
          "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ#1",
          "type": "Ed25519VerificationKey2018",
          "controller": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ",
          "publicKeyBase58": "AU2FFjtkVzjFuirgWieqGGqtNrAZWS9LDuB8TDp6EUrG"
        }
      ],
      "authentication": [
        {
          "type": "Ed25519SignatureAuthentication2018",
          "publicKey": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ#1"
        }
      ],
      "service": [
        {
          "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ;indy",
          "type": "IndyAgent",
          "priority": 0,
          "recipientKeys": [
            "AU2FFjtkVzjFuirgWieqGGqtNrAZWS9LDuB8TDp6EUrG"
          ],
          "routingKeys": ["9NnKFUZoYcCqYC2PcaXH3cnaGsoRfyGgyEHbvbLJYh8j"],
          "serviceEndpoint": "http://bob:3000"
        }
      ]
    }

    Output example:
    {
      "@context": "https://w3id.org/did/v1",
      "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ",
      "verificationMethod": [
        {
          "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ#1",
          "type": "Ed25519VerificationKey2018",
          "controller": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ",
          "publicKeyBase58": "AU2FFjtkVzjFuirgWieqGGqtNrAZWS9LDuB8TDp6EUrG"
        }
      ],
      "authentication": ["did:sov:JNKL9kJxQi5pNCfA8QBXdJ#1"],
      "service": [
        {
          "id": "did:sov:JNKL9kJxQi5pNCfA8QBXdJ#didcomm",
          "type": "did-communication",
          "priority": 0,
          "recipientKeys": ["did:sov:JNKL9kJxQi5pNCfA8QBXdJ#1"],
          "routingKeys": [
              "did:key:z6Mknq3MqipEt9hJegs6J9V7tiLa6T5H5rX3fFCXksJKTuv7#z6Mknq3MqipEt9hJegs6J9V7tiLa6T5H5rX3fFCXksJKTuv7"
          ],
          "serviceEndpoint": "http://bob:3000"
        }
      ]
    }
    """

    @staticmethod
    def public_key_is_verification_method(value: dict) -> dict:
        """Replace publicKey with verificationMethod."""
        if "publicKey" in value:
            value["verificationMethod"] = value.pop("publicKey")
        return value

    @staticmethod
    def authentication_is_list_of_verification_methods_and_refs(value: dict) -> dict:
        """Update authentication to be a list of methods and references."""
        if "authentication" in value:
            modified = []
            for authn in value["authentication"]:
                if isinstance(authn, dict) and "publicKey" in authn:
                    modified.append(authn["publicKey"])
                else:
                    modified.append(authn)
                # TODO more checks?
            value["authentication"] = modified
        return value

    @staticmethod
    def didcomm_services_use_updated_conventions(value: dict) -> dict:
        """Update DIDComm services to use updated conventions."""
        if "service" in value:
            for index, service in enumerate(value["service"]):
                if "type" in service and service["type"] == "IndyAgent":
                    service["type"] = "did-communication"
                    if ";" in service["id"]:
                        service["id"] = value["id"] + f"#didcomm-{index}"
                    if "#" not in service["id"]:
                        service["id"] += f"#didcomm-{index}"
                    if "priority" in service and service["priority"] is None:
                        service.pop("priority")
        return value

    @staticmethod
    def recip_base58_to_ref(vms: List[dict], recip: str) -> str:
        """Convert base58 public key to ref."""
        for vm in vms:
            if "publicKeyBase58" in vm and vm["publicKeyBase58"] == recip:
                return vm["id"]
        return recip

    @classmethod
    def did_key_to_did_key_ref(cls, key: str):
        """Convert did:key to did:key ref."""
        # Check if key is already a ref
        if key.rfind("#") != -1:
            return key
        # Get the value after removing did:key:
        value = key.replace("did:key:", "")

        return key + "#" + value

    @classmethod
    def didcomm_services_recip_keys_are_refs_routing_keys_are_did_key_ref(
        cls,
        value: dict,
    ) -> dict:
        """Update DIDComm service recips to use refs and routingKeys to use did:key."""
        vms = value.get("verificationMethod", [])
        if "service" in value:
            for service in value["service"]:
                if "type" in service and service["type"] == "did-communication":
                    service["recipientKeys"] = [
                        cls.recip_base58_to_ref(vms, recip)
                        for recip in service.get("recipientKeys", [])
                    ]
                if "routingKeys" in service:
                    service["routingKeys"] = [
                        (
                            DIDKey.from_public_key_b58(key, "ed25519-pub").key_id
                            if "did:key:" not in key
                            else cls.did_key_to_did_key_ref(key)
                        )
                        for key in service["routingKeys"]
                    ]
        return value

    @staticmethod
    def qualified(did_or_did_url: str) -> str:
        """Make sure DID or DID URL is fully qualified."""
        if not did_or_did_url.startswith("did:"):
            return f"did:sov:{did_or_did_url}"
        return did_or_did_url

    @classmethod
    def fully_qualified_ids_and_controllers(cls, value: dict) -> dict:
        """Make sure IDs and controllers are fully qualified."""

        def _make_qualified(value: dict) -> dict:
            if "id" in value:
                ident = value["id"]
                value["id"] = cls.qualified(ident)
            if "controller" in value:
                controller = value["controller"]
                value["controller"] = cls.qualified(controller)
            return value

        value = _make_qualified(value)
        vms = []
        for verification_method in value.get("verificationMethod", []):
            vms.append(_make_qualified(verification_method))

        services = []
        for service in value.get("service", []):
            services.append(_make_qualified(service))

        auths = []
        for authn in value.get("authentication", []):
            if isinstance(authn, dict):
                auths.append(_make_qualified(authn))
            elif isinstance(authn, str):
                auths.append(cls.qualified(authn))
            else:
                raise ValueError("Unexpected authentication value type")

        value["authentication"] = auths
        value["verificationMethod"] = vms
        value["service"] = services
        return value

    @staticmethod
    def remove_verification_method(
        vms: List[dict], public_key_base58: str
    ) -> List[dict]:
        """Remove the verification method with the given key."""
        return [vm for vm in vms if vm["publicKeyBase58"] != public_key_base58]

    @classmethod
    def remove_routing_keys_from_verification_method(cls, value: dict) -> dict:
        """Remove routing keys from verification methods.

        This was an old convention; routing keys were added to the public keys
        of the doc even though they're usually not owned by the doc sender.

        This correction should be applied before turning the routing keys into
        did keys.
        """
        vms = value.get("verificationMethod", [])
        for service in value.get("service", []):
            if "routingKeys" in service:
                for routing_key in service["routingKeys"]:
                    vms = cls.remove_verification_method(vms, routing_key)
        value["verificationMethod"] = vms
        return value

    @classmethod
    def apply(cls, value: dict) -> dict:
        """Apply all corrections to the given DID document."""
        value = deepcopy(value)
        for correction in (
            cls.public_key_is_verification_method,
            cls.authentication_is_list_of_verification_methods_and_refs,
            cls.fully_qualified_ids_and_controllers,
            cls.didcomm_services_use_updated_conventions,
            cls.remove_routing_keys_from_verification_method,
            cls.didcomm_services_recip_keys_are_refs_routing_keys_are_did_key_ref,
        ):
            value = correction(value)

        return value
