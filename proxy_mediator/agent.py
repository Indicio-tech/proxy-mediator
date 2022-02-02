"""
Proxy Mediator Agent.
"""
import asyncio
from contextvars import ContextVar
import logging
from typing import Callable, Iterable, MutableMapping, Optional

from aries_staticagent.crypto import recipients_from_packed_message
from aries_staticagent.dispatcher.base import Dispatcher

from .connection import Connection
from .store import Store


LOGGER = logging.getLogger(__name__)
VAR: ContextVar["Agent"] = ContextVar("agent")


class ConnectionNotFound(Exception):
    """Raised when connection for message not found."""


class Agent:
    """Agent"""

    @classmethod
    def get(cls):
        """Return context var for agent."""
        return VAR.get()

    @classmethod
    def set(cls, value: "Agent"):
        """Return context var for agent."""
        return VAR.set(value)

    def __init__(
        self,
        dispatcher: Dispatcher,
        receive_invite_url: Callable,
        connections: MutableMapping[str, Connection] = None,
    ):
        self.connections: MutableMapping[str, Connection] = (
            connections if connections is not None else {}
        )

        # We want each connection created by this module to share the same routes
        # so this same dispatcher will be used for all created connections.
        self.dispatcher = dispatcher
        self.state: str = "init"

        # Special connections
        self.receive_invite_url = receive_invite_url
        self.mediator_connection: Optional[Connection] = None
        self._mediator_connection_event = asyncio.Event()
        self.agent_connection: Optional[Connection] = None
        self.agent_invitation: Optional[str] = None

    def connections_for_message(self, packed_message: bytes) -> Iterable[Connection]:
        recipients = recipients_from_packed_message(packed_message)
        connections = [
            self.connections[recip] for recip in recipients if recip in self.connections
        ]
        if not connections:
            raise ConnectionNotFound(
                f"No connections for message with recipients: {recipients}"
            )
        return connections

    async def handle_message(self, packed_message: bytes) -> Optional[bytes]:
        """Handle a received message."""
        response = []
        for conn in self.connections_for_message(packed_message):
            LOGGER.debug(
                "Handling message with connection using verkey: %s", conn.verkey_b58
            )
            with conn.session(response.append) as session:
                LOGGER.debug(
                    "Handling message with connection using verkey: %s", conn.verkey_b58
                )
                msg = conn.unpack(packed_message)
                if session:
                    session.update_thread_from_msg(msg)
                await self.dispatcher.dispatch(msg, conn)

        if response:
            return response.pop()

        return None

    # Mediator setup operations
    async def mediator_invite_received(self) -> Connection:
        """Await event notifying that mediator invite has been received."""
        await self._mediator_connection_event.wait()
        if not self.mediator_connection:
            raise RuntimeError("Mediator connection event triggered without set")
        return self.mediator_connection

    async def receive_mediator_invite(self, invite: str) -> Connection:
        """Receive mediator invitation."""
        self.mediator_connection = await self.receive_invite_url(invite, endpoint="")
        self._mediator_connection_event.set()
        return self.mediator_connection

    # Store
    async def load_connections_from_store(self, store: Store):
        """Load connections from store."""
        async with store:
            async with store.session() as session:
                entries = await store.retrieve_connections(session)
                connections = [
                    Connection.from_store(entry.value_json, dispatcher=self.dispatcher)
                    for entry in entries
                ]
                self.connections.update(
                    {connection.verkey_b58: connection for connection in connections}
                )

                mediator_connection_key = await store.retrieve_mediator(session)
                agent_connection_key = await store.retrieve_agent(session)

        if mediator_connection_key:
            self.mediator_connection = self.connections.get(mediator_connection_key)
        if agent_connection_key:
            self.agent_connection = self.connections.get(agent_connection_key)

    async def save_connections_to_store(self, store: Store):
        """Save connections to store."""
        async with store:
            async with store.transaction() as txn:
                for connection in self.connections.values():
                    await store.store_connection(txn, connection)

                if self.agent_connection:
                    await store.store_agent(txn, self.agent_connection.verkey_b58)

                if self.mediator_connection:
                    await store.store_mediator(txn, self.mediator_connection.verkey_b58)

                await txn.commit()
