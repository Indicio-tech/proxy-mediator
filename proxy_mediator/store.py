"""Helper for working with Askar store."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging
from typing import Optional, Sequence

from aries_askar import Store as AskarStore, AskarError, AskarErrorCode
from aries_askar.store import Entry, Session

from proxy_mediator.agent import Connection


VAR: ContextVar["Store"] = ContextVar("Store")
LOGGER = logging.getLogger(__name__)


class Store:
    """Helper for working with Askar store."""

    CATEGORY_CONNECTIONS = "connections"
    CATEGORY_IDENTIFIERS = "identifiers"
    IDENTIFIER_AGENT = "agent"
    IDENTIFIER_MEDIATOR = "mediator"

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
        """Close the store."""
        if self.store:
            await self.store.close()
        self.store = None

    async def __aenter__(self):
        """Open store."""
        await self.open()

    async def __aexit__(self, type, value, tb):
        """Close store."""
        await self.close()
        return False

    @asynccontextmanager
    async def transaction(self):
        """Start transaction."""
        if not self.store:
            raise ValueError("Store must be opened")

        async with self.store.transaction() as txn:
            yield txn

    @asynccontextmanager
    async def session(self):
        """Start session."""
        if not self.store:
            raise ValueError("Store must be opened")

        async with self.store.session() as session:
            yield session

    async def store_connection(self, session: Session, connection: Connection):
        """Insert agent connection into store."""
        value = connection.to_store().encode()
        LOGGER.debug("Saving connection: %s", value)
        try:
            await session.insert(
                self.CATEGORY_CONNECTIONS,
                connection.verkey_b58,
                value,
            )
        except AskarError as err:
            if err.code == AskarErrorCode.DUPLICATE:
                await session.remove(self.CATEGORY_CONNECTIONS, connection.verkey_b58)
                await session.insert(
                    self.CATEGORY_CONNECTIONS, connection.verkey_b58, value
                )
            else:
                raise

    async def store_agent(self, session: Session, key: str):
        """Save agent connection verkey for later recall."""
        LOGGER.debug("Saving agent connection: %s", key)
        try:
            await session.insert(
                self.CATEGORY_IDENTIFIERS,
                self.IDENTIFIER_AGENT,
                key,
            )
        except AskarError as err:
            if err.code == AskarErrorCode.DUPLICATE:
                await session.remove(self.CATEGORY_IDENTIFIERS, self.IDENTIFIER_AGENT)
                await session.insert(
                    self.CATEGORY_IDENTIFIERS,
                    self.IDENTIFIER_AGENT,
                    key,
                )
            else:
                raise

    async def store_mediator(self, session: Session, key: str):
        """Save agent connection verkey for later recall."""
        LOGGER.debug("Saving mediator connection: %s", key)
        try:
            await session.insert(
                self.CATEGORY_IDENTIFIERS,
                self.IDENTIFIER_MEDIATOR,
                key,
            )
        except AskarError as err:
            if err.code == AskarErrorCode.DUPLICATE:
                await session.replace(
                    self.CATEGORY_IDENTIFIERS,
                    self.IDENTIFIER_MEDIATOR,
                    key,
                )
            else:
                raise

    async def retrieve_connections(self, session: Session) -> Sequence[Entry]:
        """Retrieve mediation connection from store."""
        entries = list(await session.fetch_all(self.CATEGORY_CONNECTIONS))
        LOGGER.debug("Retrieve connections returning: %s", entries)
        return entries

    async def retrieve_agent(self, session: Session) -> Optional[str]:
        """Retrieve mediation connection from store."""
        entry = await session.fetch(self.CATEGORY_IDENTIFIERS, self.IDENTIFIER_AGENT)
        LOGGER.debug("Retrieve agent returning: %s", entry.value if entry else None)
        return entry.value.decode("ascii") if entry else None

    async def retrieve_mediator(self, session: Session) -> Optional[str]:
        """Retrieve mediation connection from store."""
        entry = await session.fetch(self.CATEGORY_IDENTIFIERS, self.IDENTIFIER_MEDIATOR)
        LOGGER.debug("Retrieve mediator returning: %s", entry.value if entry else None)
        return entry.value.decode("ascii") if entry else None
