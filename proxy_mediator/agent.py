"""
Proxy Mediator Agent.
"""
import asyncio
from asyncio.futures import Future
from contextvars import ContextVar
import json
import logging
from typing import Callable, Iterable, MutableMapping, Optional

from aries_staticagent import Connection as AsaPyConn, crypto
from aries_staticagent.connection import Target
from aries_staticagent.dispatcher import Dispatcher, Handler
from aries_staticagent.message import MsgType
from aries_staticagent.module import Module
from statemachine import State, StateMachine

from .protocols.connections import Connections


LOGGER = logging.getLogger(__name__)
VAR: ContextVar["Agent"] = ContextVar("agent")


class ConnectionNotFound(Exception):
    """Raised when connection for message not found."""


class Connection(AsaPyConn):
    """Wrapper around Static Agent library connection to provide state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state: str = "null"
        self._completed: Future = asyncio.get_event_loop().create_future()
        self.multiuse: bool = False
        self.invitation_key: Optional[str] = None

    @property
    def is_completed(self):
        return self._completed.done()

    def complete(self):
        """Complete this connection"""
        self._completed.set_result(self)

    async def completion(self) -> "Connection":
        """Await connection completion.

        For invitation connections, the connection is replaced after receiving
        a connection request. This will return the completed connection.
        """
        return await self._completed

    def from_invite(self, invite: "Connection"):
        """Transfer state from invite connection to relationship connection."""
        self.state = invite.state
        self._completed = invite._completed


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

    receive_invite = null.to(invite_received)
    send_request = invite_received.to(request_sent)
    receive_response = request_sent.to(response_received)
    send_ping = response_received.to(complete) | complete.to.itself()
    receive_ping = response_sent.to(complete) | complete.to.itself()
    send_ping_response = complete.to.itself()
    receive_ping_response = complete.to.itself()


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

    def __init__(self, connections: MutableMapping[str, Connection] = None):
        super().__init__()
        self.connections: MutableMapping[str, Connection] = (
            connections if connections else {}
        )

        # We want each connection created by this module to share the same routes
        # so this same dispatcher will be used for all created connections.
        self.dispatcher = Dispatcher()
        self.mediator_connection: Optional[Connection] = None
        self._mediator_connection_event = asyncio.Event()
        self.agent_connection: Optional[Connection] = None
        self.agent_invitation: Optional[str] = None

    def _recipients_from_packed_message(self, packed_message: bytes) -> Iterable[str]:
        """
        Inspect the header of the packed message and extract the recipient key.
        """
        try:
            wrapper = json.loads(packed_message)
        except Exception as err:
            raise ValueError("Invalid packed message") from err

        recips_json = crypto.b64_to_bytes(wrapper["protected"], urlsafe=True).decode(
            "ascii"
        )
        try:
            recips_outer = json.loads(recips_json)
        except Exception as err:
            raise ValueError("Invalid packed message recipients") from err

        return [recip["header"]["kid"] for recip in recips_outer["recipients"]]

    def connections_for_message(self, packed_message: bytes) -> Iterable[Connection]:
        recipients = self._recipients_from_packed_message(packed_message)
        connections = [
            self.connections[recip] for recip in recipients if recip in self.connections
        ]
        if not connections:
            raise ConnectionNotFound(
                f"No connections for message with recipients: {recipients}"
            )
        return connections

    def new_connection(
        self,
        *,
        multiuse: bool = False,
        invitation_key: str = None,
        invite_connection: Connection = None,
        target: Target = None,
    ):
        """Return new connection and store in connections."""
        conn = Connection.random(target=target, dispatcher=self.dispatcher)
        conn.multiuse = multiuse
        conn.invitation_key = invitation_key
        self.connections[conn.verkey_b58] = conn
        if invite_connection:
            conn.from_invite(invite_connection)
            conn.invitation_key = invite_connection.verkey_b58
        return conn

    def get_connection(self, verkey: str):
        """Return connection by key."""
        return self.connections[verkey]

    def delete_connection_by_key(self, verkey: str):
        if verkey in self.connections:
            self.connections.pop(verkey)

    def delete_connection(self, conn: Connection):
        if conn.verkey_b58 in self.connections:
            self.connections.pop(conn.verkey_b58)

    def store_connection(self, verkey: str, conn: Connection):
        """Store a connection.

        If the connection was previously created with new_connection and not
        deleted, there is no need to call this method.
        """
        self.connections[verkey] = conn

    async def mediator_invite_received(self) -> Connection:
        """Await event notifying that mediator invite has been received."""
        await self._mediator_connection_event.wait()
        if not self.mediator_connection:
            raise RuntimeError("Mediator connection event triggered without set")
        return self.mediator_connection

    async def receive_mediator_invite(self, invite: str) -> Connection:
        """Receive mediator invitation."""
        connections = Connections.get()
        self.mediator_connection = await connections.receive_invite_url(
            invite, endpoint=""
        )
        self._mediator_connection_event.set()
        return self.mediator_connection

    def route_method(self, msg_type: str) -> Callable:
        """Register route decorator."""

        def register_route_dec(func):
            self.dispatcher.add_handler(Handler(MsgType(msg_type), func))
            return func

        return register_route_dec

    def route_module(self, module: Module):
        """Register a module for routing."""
        handlers = [Handler(msg_type, func) for msg_type, func in module.routes.items()]
        return self.dispatcher.add_handlers(handlers)

    async def handle_message(self, packed_message: bytes) -> Optional[bytes]:
        response = []
        for conn in self.connections_for_message(packed_message):
            LOGGER.debug(
                "Handling message with connection using verkey: %s", conn.verkey_b58
            )
            with conn.session(response.append) as session:
                await session.handle(packed_message)

        if response:
            return response.pop()

        return None
