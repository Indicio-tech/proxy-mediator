"""Active message retriever."""

import asyncio
from contextlib import suppress
import logging
from typing import Optional

import aiohttp

from .agent import Connection


LOGGER = logging.getLogger(__name__)


class MessageRetriever:
    """
    Retrieve messages via websocket from a given connection.

    This class opens a websocket connection, and periodically polls for messages
    using a trust ping with response requested set to false.
    """

    def __init__(self, conn: Connection, poll_interval: float = 5.0):
        if not conn.target or not conn.target.endpoint:
            raise ValueError("Connection must have endpoint for WS polling")
        self.endpoint = conn.target.endpoint + "/ws"
        self.connection = conn
        self.socket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.poll_interval = poll_interval
        self.poll_task: Optional[asyncio.Task] = None
        self.ws_task: Optional[asyncio.Task] = None

    async def ws(self):
        LOGGER.debug("Starting websocket to %s", self.endpoint)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(self.endpoint) as socket:
                    self.socket = socket
                    async for msg in socket:
                        LOGGER.debug("Received ws message: %s", msg)
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            unpacked = self.connection.unpack(msg.data)
                            LOGGER.debug(
                                "Unpacked message from websocket: %s",
                                unpacked.pretty_print(),
                            )
                            await self.connection.dispatch(unpacked)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            LOGGER.error(
                                "ws connection closed with exception %s",
                                socket.exception(),
                            )
            except Exception:
                LOGGER.exception("Websocket connection error")
        self.socket = None

    async def poll(self):
        ping = {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping",
            "response_requested": False,
            "~transport": {"return_route": "all"},
        }
        while True:
            if self.socket:
                prepared_message = self.connection.pack(ping)
                await self.socket.send_bytes(prepared_message)
            else:
                LOGGER.warning("Poll task still active but websocket is gone; stopping")
                break
            await asyncio.sleep(self.poll_interval)

    async def start(self):
        self.ws_task = asyncio.ensure_future(self.ws())
        await asyncio.sleep(1)
        await self.poll()

    async def stop(self):
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
