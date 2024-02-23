"""Active message retriever."""

import asyncio
from contextlib import suppress
import logging
from typing import Optional

import aiohttp

from .connection import Connection


LOGGER = logging.getLogger(__name__)


def _determine_ws_endpoint(doc: dict) -> Optional[str]:
    """Determine which endpoint from a DID Document should be used as the WS endpoint.

    If no suitable endpoint is found, return None.
    """

    if not doc["service"]:
        return None

    for service in doc["service"]:
        # Endpoint will look like:
        #     http://agents-r-us.org
        #     ws://agents-r-us.org/ws
        #     wss://agents-r-us.org/ws
        # Or similar
        endpoint: str = service["serviceEndpoint"]
        if endpoint.startswith("ws"):
            return endpoint


class MessageRetriever:
    """Retrieve messages via websocket from a given connection.

    This class opens a websocket connection, and periodically polls for messages
    using a trust ping with response requested set to false.
    """

    def __init__(self, conn: Connection, poll_interval: float = 5.0):
        """Initialize the message retriever."""
        if not conn.diddoc:
            raise ValueError("Connection must have DID Doc for WS polling")

        endpoint = _determine_ws_endpoint(conn.diddoc)
        if not endpoint:
            raise ValueError("Connection must have a WS endpoint, none found")

        self.endpoint = endpoint
        self.connection = conn
        self.socket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.poll_interval = poll_interval
        self.poll_task: Optional[asyncio.Task] = None
        self.ws_task: Optional[asyncio.Task] = None

    async def handle_ws(
        self, socket: aiohttp.ClientWebSocketResponse, msg: aiohttp.WSMessage
    ):
        """Handle a message from the websocket."""
        LOGGER.debug("Received ws message: %s", msg)
        if msg.type == aiohttp.WSMsgType.BINARY:
            try:
                unpacked = self.connection.unpack(msg.data)
                LOGGER.debug(
                    "Unpacked message from websocket: %s",
                    unpacked.pretty_print(),
                )
                await self.connection.dispatch(unpacked)
            except Exception:
                LOGGER.exception("Failed to handle message")

        elif msg.type == aiohttp.WSMsgType.ERROR:
            LOGGER.error(
                "ws connection closed with exception %s",
                socket.exception(),
            )

    async def ws(self):
        """Open websocket and handle messages."""
        LOGGER.debug("Starting websocket to %s", self.endpoint)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(self.endpoint) as socket:
                    self.socket = socket
                    async for msg in socket:
                        await self.handle_ws(socket, msg)
            except Exception:
                LOGGER.exception("Websocket connection error")
        self.socket = None

    async def poll(self):
        """Periodically send trust ping messages to the mediator."""
        ping = {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping",
            "response_requested": False,
            "~transport": {"return_route": "all"},
        }
        while True:
            if self.socket:
                LOGGER.debug("Polling mediator")
                prepared_message = self.connection.pack(ping)
                await self.socket.send_bytes(prepared_message)
            else:
                LOGGER.warning("Poll task still active but websocket is gone; stopping")
                break
            await asyncio.sleep(self.poll_interval)

    async def start(self):
        """Start the message retriever."""
        self.ws_task = asyncio.ensure_future(self.ws())
        await asyncio.sleep(1)
        await self.poll()

    async def stop(self):
        """Stop the message retriever."""
        if self.socket:
            await self.socket.close()
        if self.poll_task:
            self.poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.poll_task
            self.poll_task = None
        if self.ws_task:
            self.ws_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.ws_task
            self.poll_task = None

    async def __aenter__(self):
        """Enter context."""
        yield asyncio.ensure_future(self.start())

    async def __aexit__(self, exc_type, exc, tb):
        """Exit context."""
        if exc:
            LOGGER.exception("Error occurred in MessageRetriever")
        await self.stop()
        return False
