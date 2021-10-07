"""Connections Protocol Starter Kit"""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os

from aiohttp import web
from aries_staticagent import crypto
from configargparse import ArgumentParser, YAMLConfigFileParser

from . import (
    admin,
    agent_connection as agent_connection_var,
    connections as connections_var,
    mediator_connection as mediator_connection_var,
)
from .connections import Connection, ConnectionMachine, Connections
from .protocols import BasicMessage, CoordinateMediation, Routing


LOGGER = logging.getLogger("proxy_mediator")


def config():
    """Get config"""
    parser = ArgumentParser(
        config_file_parser_class=YAMLConfigFileParser, prog="proxy_mediator"
    )
    parser.add_argument("--port", env_var="PORT", type=str, required=True)
    parser.add_argument(
        "--mediator-invite", env_var="MEDIATOR_INVITE", type=str, required=True
    )
    parser.add_argument("--endpoint", env_var="ENDPOINT", type=str, required=True)
    parser.add_argument("--log-level", env_var="LOG_LEVEL", type=str, default="WARNING")
    args = parser.parse_args()

    # Configure logs
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s", level=args.log_level
    )
    logging.root.warning("Log level set to: %s", args.log_level)

    return args


def store_connection(conn: Connection):
    if hasattr(conn, "state") and (
        conn.state == ConnectionMachine.complete
        or conn.state == ConnectionMachine.response_received
        or conn.state == ConnectionMachine.response_sent
    ):
        assert conn.target
        with open(".keys", "w+") as key_file:
            json.dump(
                {
                    "did": conn.did,
                    "my_vk": conn.verkey_b58,
                    "my_sk": crypto.bytes_to_b58(conn.sigkey),
                    "recipients": [
                        crypto.bytes_to_b58(recip) for recip in conn.target.recipients
                    ]
                    if conn.target.recipients
                    else [],
                    "endpoint": conn.target.endpoint,
                },
                key_file,
            )


def recall_connection():
    if not os.path.exists(".keys"):
        return None
    with open(".keys", "r") as key_file:
        info = json.load(key_file)
        return Connection.from_parts(
            (info["my_vk"], info["my_sk"]),
            recipients=info["recipients"],
            endpoint=info["endpoint"],
        )


@asynccontextmanager
async def webserver(port: int, connections: Connections):
    """Listen for messages and handle using Connections."""

    async def sleep():
        print(
            "======== Running on {} ========\n(Press CTRL+C to quit)".format(port),
            flush=True,
        )
        while True:
            await asyncio.sleep(3600)

    async def handle(request):
        """aiohttp handle POST."""
        packed_message = await request.read()
        LOGGER.debug("Received packed message: %s", packed_message)
        try:
            response = await connections.handle_message(packed_message)
            if response:
                LOGGER.debug("Returning response over HTTP")
                return web.Response(body=response)
        except Exception:
            LOGGER.exception("Failed to handle message")

        raise web.HTTPAccepted()

    app = web.Application()
    app.add_routes([web.post("/", handle)])

    # Setup "Admin" routes
    admin.register_routes(connections, app)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    print("Starting server...", flush=True)
    await site.start()
    try:
        yield sleep
    finally:
        print("Closing server...", flush=True)
        await runner.cleanup()


async def main():
    """Main."""
    args = config()
    print(f"Starting proxy with endpoint: {args.endpoint}", flush=True)

    connections = Connections(args.endpoint)
    connections_var.set(connections)
    connections.route_module(BasicMessage())
    coordinate_mediation = CoordinateMediation()
    connections.route_module(coordinate_mediation)
    connections.route_module(Routing())

    async with webserver(args.port, connections) as loop:
        # Connect to mediator by processing passed in invite
        mediator_connection = await connections.receive_invite_url(args.mediator_invite)
        mediator_connection_var.set(mediator_connection)
        await mediator_connection.completion()
        await coordinate_mediation.request_mediation_from_external(mediator_connection)

        # Connect to agent by creating invite and awaiting connection completion
        agent_connection, invite = connections.create_invitation()
        print("Invitation URL:", invite, flush=True)
        agent_connection = await agent_connection.completion()
        agent_connection_var.set(agent_connection)
        print("Connection completed successfully")

        # TODO Start self repairing WS connection to mediator to retrieve
        # messages as a separate task
        await loop()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
