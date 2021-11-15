from contextvars import ContextVar
from enum import Enum
import json
from typing import Optional

from aries_askar import Store as AskarStore, AskarError, AskarErrorCode
from aries_staticagent import crypto

from proxy_mediator.agent import Connection


VAR: ContextVar["Store"] = ContextVar("Store")


class Store:
    """Helper for working with Askar store."""

    class Name(Enum):
        """Types of entities stored."""

        agent = "agent"
        mediator = "mediator"

    def __init__(self, repo_uri: str, key: str):
        """Initialize store with repo_uri and key for wallet.

        Example URI values:
            sqlite://:memory:
            postgres://postgres:mysecretpassword@localhost:5432/askar-test

        Key should be treated as a secret value. Actual encryption key is derived
        from key using Argon2i. Key strength is analagous to password strength.
        """
        self.repo_uri = repo_uri
        self.key = key
        self.store: Optional[AskarStore] = None

    @classmethod
    def get(cls):
        """Return context var for store."""
        return VAR.get()

    @classmethod
    def set(cls, value: "Store"):
        """Return context var for store."""
        return VAR.set(value)

    async def open(self):
        """Open/provision the store."""
        self.store = await AskarStore.provision(
            self.repo_uri, "kdf:argon2i", self.key, recreate=False
        )

    async def close(self):
        if self.store:
            await self.store.close()
        self.store = None

    async def __aenter__(self):
        await self.open()

    async def __aexit__(self, type, value, tb):
        await self.close()

    @staticmethod
    def serialize_json(conn):
        """Convert Connection object to JSON object"""
        return json.dumps(
            {
                "state": conn.state,
                "multiuse": conn.multiuse,
                "invitation_key": conn.invitation_key,
                "did": conn.did,
                "verkey": conn.verkey_b58,
                "sigkey": crypto.bytes_to_b58(conn.sigkey),
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
            (info["verkey"], info["sigkey"]),
            recipients=info["recipients"],
            endpoint=info["endpoint"],
        )
        conn.state = info["state"]
        conn.multiuse = info["multiuse"]
        conn.invitation_key = info["invitation_key"]
        return conn

    async def store_connection(self, connection: Connection, name: Name):
        """Insert agent connection into store"""
        if not self.store:
            raise ValueError("Store must be opened")

        value = Store.serialize_json(connection).encode()
        async with self.store.transaction() as txn:
            try:
                await txn.insert(
                    "connection",
                    name.value,
                    value,
                )
            except AskarError as err:
                if err.code == AskarErrorCode.DUPLICATE:
                    await txn.replace("connection", name.value, value)
                else:
                    raise
            await txn.commit()

    async def retrieve_connection(self, name: Name):
        """Retrieve mediation connection from store"""
        if not self.store:
            raise ValueError("Store must be opened")

        async with self.store as session:
            entry = await session.fetch("connection", name.value)

        if entry:
            return Store.deserialize_json(entry.value)
        return None

    async def store_agent(self, connection: Connection):
        return await self.store_connection(connection, self.Name.agent)

    async def store_mediator(self, connection: Connection):
        return await self.store_connection(connection, self.Name.mediator)

    async def retrieve_agent(self):
        return await self.retrieve_connection(self.Name.agent)

    async def retrieve_mediator(self):
        return await self.retrieve_connection(self.Name.mediator)
