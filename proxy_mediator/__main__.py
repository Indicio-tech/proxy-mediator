"""Connections Protocol Starter Kit"""
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import signal

from aiohttp import web
from aries_staticagent.dispatcher.handler_dispatcher import HandlerDispatcher
from configargparse import ArgumentParser, YAMLConfigFileParser

from . import admin
from .agent import Agent
from .message_retriever import MessageRetriever
from .protocols import BasicMessage, Connections, CoordinateMediation, Routing
from .protocols.oob_didexchange import OobDidExchange
from .store import Store


LOGGER = logging.getLogger("proxy_mediator")


def config():
    """Get config"""
    parser = ArgumentParser(
        config_file_parser_class=YAMLConfigFileParser, prog="proxy_mediator"
    )
    parser.add_argument("--port", env_var="PORT", type=str, required=True)
    parser.add_argument(
        "--mediator-invite", env_var="MEDIATOR_INVITE", type=str, required=False
    )
    parser.add_argument(
        "--enable-store",
        env_var="ENABLE_STORE",
        action="store_true",
    )
    parser.add_argument(
        "--repo-uri",
        env_var="REPO_URI",
        type=str,
        required=False,
    )
    parser.add_argument(
        "--repo-key",
        env_var="REPO_KEY",
        type=str,
        required=False,
    )
    parser.add_argument("--endpoint", env_var="ENDPOINT", type=str, required=True)
    parser.add_argument("--log-level", env_var="LOG_LEVEL", type=str, default="WARNING")
    parser.add_argument(
        "--poll-interval",
        env_var="POLL_INTERVAL",
        type=float,
        required=False,
        default=20.0,
    )
    args = parser.parse_args()

    # Configure logs
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s", level=args.log_level
    )
    logging.root.warning("Log level set to: %s", args.log_level)

    if args.enable_store and not args.repo_uri:
        raise ValueError("--repo-uri required when store is enabled")

    if args.enable_store and not args.repo_key:
        raise ValueError("--repo-key required when store is enabled")

    return args


@asynccontextmanager
async def webserver(port: int, agent: Agent):
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
            response = await agent.handle_message(packed_message)
            if response:
                LOGGER.debug("Returning response over HTTP")
                return web.Response(body=response)
        except Exception:
            LOGGER.exception("Failed to handle message")

        raise web.HTTPAccepted()

    app = web.Application()
    app.add_routes([web.post("/", handle)])

    # Setup "Admin" routes
    admin.register_routes(app)

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


def handle_oob_and_connections_invites(
    connections: Connections, did_exchange: OobDidExchange
):
    """Handle OOB and Connections invites."""

    async def _handle_oob_and_connections_invites(invite: str, **kargs):
        if "c_i=" in invite:
            return await connections.receive_invite_url(invite, **kargs)
        elif "oob=" in invite:
            return await did_exchange.receive_invite_url(invite, **kargs)
        else:
            raise ValueError("Invalid invite")

    return _handle_oob_and_connections_invites


async def main():
    """Main."""
    args = config()
    print(f"Starting proxy with endpoint: {args.endpoint}", flush=True)

    dispatcher = HandlerDispatcher()
    verkeys_to_connections = {}

    # Modules
    connections = Connections(
        dispatcher, verkeys_to_connections, endpoint=args.endpoint
    )
    Connections.set(connections)
    coordinate_mediation = CoordinateMediation()

    did_exchange = OobDidExchange(
        dispatcher, verkeys_to_connections, endpoint=args.endpoint
    )

    # Agent
    agent = Agent(
        dispatcher,
        handle_oob_and_connections_invites(connections, did_exchange),
        verkeys_to_connections,
    )
    Agent.set(agent)

    # Routes
    dispatcher.extend(BasicMessage().routes)
    dispatcher.extend(Routing().routes)
    dispatcher.extend(connections.routes)
    dispatcher.extend(coordinate_mediation.routes)

    # Recall connections
    store = None
    if args.enable_store:
        store = Store(args.repo_uri, args.repo_key)
        Store.set(store)
        LOGGER.debug("Recalling connections")
        await agent.load_connections_from_store(store)

    async with webserver(args.port, agent):
        if agent.mediator_connection:
            LOGGER.debug("Mediator connection loaded from store")
        else:
            agent.state = "setup"
            # Connect to mediator by processing passed in invite
            # All these operations must take place without an endpoint
            if not args.mediator_invite:
                LOGGER.debug("Awaiting mediator invitation over HTTP")
                print("Awaiting mediator invitation over HTTP")
                mediator_connection = await agent.mediator_invite_received()
            else:
                LOGGER.debug(
                    "Receiving mediator invitation from input: %s", args.mediator_invite
                )
                mediator_connection = await agent.receive_mediator_invite(
                    args.mediator_invite
                )
            await mediator_connection.completion()

            # Request mediation and send keylist update
            await coordinate_mediation.request_mediation_from_external(
                mediator_connection
            )
            await coordinate_mediation.send_keylist_update(
                mediator_connection,
                action="add",
                recipient_key=mediator_connection.verkey_b58,
            )

        if agent.agent_connection:
            LOGGER.debug("Agent connection loaded from store")
        else:
            agent.state = "setup"
            # Connect to agent by creating invite and awaiting connection completion
            agent_connection, invite = did_exchange.create_invitation()
            agent.agent_invitation = invite
            print("Invitation URL:", invite, flush=True)
            agent_connection = await agent_connection.completion()
            agent.agent_connection = agent_connection
            print("Connection completed successfully")

            print("Waiting a moment before beginning message retriever")
            await asyncio.sleep(3)

        if not agent.mediator_connection:
            raise RuntimeError("Mediator connection should be set")

        if not agent.agent_connection:
            raise RuntimeError("Agent connection should be set")

        # Store connections
        if store:
            LOGGER.debug("Saving connections")
            await agent.save_connections_to_store(store)

        retriever = MessageRetriever(agent.mediator_connection, args.poll_interval)

        try:
            agent.state = "ready"
            await retriever.start()
        finally:
            LOGGER.debug("Stopping retriever")
            await retriever.stop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(main())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, main_task.cancel)

    try:
        with suppress(asyncio.CancelledError):
            loop.run_until_complete(main_task)
    finally:
        loop.close()
