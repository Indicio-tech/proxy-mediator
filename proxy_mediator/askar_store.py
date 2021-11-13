from contextvars import ContextVar
import sys
import json


from aries_askar.bindings import generate_raw_key
from aries_askar import Store
from pydantic import BaseModel

from proxy_mediator.agent import Connection
from aries_staticagent import crypto


VAR: ContextVar["AskarStore"] = ContextVar("AskarStore")

if len(sys.argv) > 1:
    REPO_URI = sys.argv[1]
    if REPO_URI == "postgres":
        REPO_URI = "postgres://postgres:mysecretpassword@localhost:5432/askar-test"
else:
    REPO_URI = "sqlite://:memory:"


class AskarStore(BaseModel):
    def __init__(self, repo_uri, key):
        """Configuration"""
        self.repo_uri = repo_uri
        self.key = key

    @classmethod
    def get(cls):
        """Return context var for store."""
        return VAR.get()

    @classmethod
    def set(cls, value: "Store"):
        """Return context var for store."""
        return VAR.set(value)

    @staticmethod
    async def store():
        """Provisioning"""
        key = generate_raw_key()
        return await Store.provision(REPO_URI, "kdf:argon2i", key, recreate=True)

    @staticmethod
    def serialize_json(conn):
        """Convert Connection object to JSON object"""
        return json.dumps(
            {
                "state": crypto.bytes_to_b58(conn.state),
                "multiuse": crypto.bytes_to_b58(conn.multiuse),
                "invitation_key": crypto.bytes_to_b58(conn.invitation_key),
                "did": conn.did,
                "my_vk": conn.verkey_b58,
                "my_sk": crypto.bytes_to_b58(conn.sigkey),
                "recipients": [
                    crypto.bytes_to_b58(recip) for recip in conn.target.recipients
                ]
                if conn.target.recipients
                else [],
                "endpoint": conn.target.endpoint,
            }
        )

    @staticmethod
    def deserialize_json(json_obj):
        """Convert JSON object into Connection object"""
        info = json.loads(json_obj)
        conn = Connection.from_parts(
            (info["my_vk"], info["my_sk"]),
            recipients=info["recipients"],
            endpoint=info["endpoint"],
        )
        conn.state = info["state"]
        conn.multiuse = info["multiuse"]
        conn.invitation_key = info["invitation_key"]
        return conn

    @staticmethod
    async def store_connection(connection: Connection, store, entity: str):
        """Insert agent connection into store"""
        conn = AskarStore.serialize_json(connection).encode()
        async with store.transaction() as txn:
            await txn.insert(
                "connection",
                entity,
                conn,
                {"enctag": "b"},
            )
            await txn.commit()

    @staticmethod
    async def retrieve_connection(store, entity: str):
        """Retrieve mediation connection from store"""
        async with store as session:
            entry = await session.fetch("connection", entity)
        return AskarStore.deserialize_json(entry.value)
