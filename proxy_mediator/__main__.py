"""Connections Protocol Starter Kit"""
import argparse
import json
import logging
import os
from typing import Iterable
from aiohttp import web

from aries_staticagent import crypto, utils
from aries_staticagent.dispatcher import Dispatcher, NoRegisteredHandlerException

from .connections import Connections, Connection
from .connections import State as ConnectionStates


LOGGER = logging.getLogger(__name__)


def config():
    """Get config"""

    def environ_or_required(key):
        if os.environ.get(key):
            return {"default": os.environ.get(key)}
        return {"required": True}

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", **environ_or_required("PORT"))
    parser.add_argument("--replace-keys", action="store_true", dest="replace")
    args = parser.parse_args()
    return args


def store_connection(conn: Connection):
    if hasattr(conn, "state") and (
        conn.state.state == ConnectionStates.COMPLETE
        or conn.state.state == ConnectionStates.RESPONDED
    ):
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


def _recipients_from_packed_message(packed_message: bytes) -> Iterable[str]:
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

    return map(lambda recip: recip["header"]["kid"], recips_outer["recipients"])


def main():
    """Main."""
    args = config()
    endpoint = os.environ.get("ENDPOINT", f"http://localhost:{args.port}")
    print(f"Starting proxy with endpoint: {endpoint}")

    dispatcher = Dispatcher()
    connections = Connections(endpoint, dispatcher=dispatcher)
    conn = recall_connection()
    if not conn or args.replace:
        conn, invitation_url = connections.create_invitation()
        print("Use this invitation to connect to the toolbox.")
        print("Invitation URL:", invitation_url, flush=True)

    conn.route_module(connections)

    @conn.route("did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/basicmessage/1.0/message")
    async def basic_message_auto_responder(msg, conn):
        """Automatically respond to basicmessages."""
        await conn.send_async(
            {
                "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
                "basicmessage/1.0/message",
                "~l10n": {"locale": "en"},
                "sent_time": utils.timestamp(),
                "content": "You said: {}".format(msg["content"]),
            }
        )

    # TODO obtain endpoint and routing keys outside of handler method
    mediation_endpoint = "mediation_endpoint placeholder"
    mediation_routing_keys = "mediation_routing_keys placeholder"

    @conn.route("https://didcomm.org/coordinate-mediation/1.0/mediate-request")
    async def grant_mediation_request(msg, conn):
        await conn.send_async(
            {
                "@type": "https://didcomm.org/coordinate-mediation/1.0/mediate-grant",
                "endpoint": mediation_endpoint,
                "routing_keys": mediation_routing_keys,
            }
        )

    async def handle(request):
        """aiohttp handle POST."""
        response = []
        packed_message = await request.read()
        for recipient in _recipients_from_packed_message(packed_message):
            if recipient in connections.connections:
                conn = connections.connections[recipient]
                with conn.session(response.append) as session:
                    try:
                        await session.handle(await request.read())
                    except NoRegisteredHandlerException:
                        LOGGER.exception("Message handling failed")
                        raise web.HTTPAccepted()

        if response:
            return web.Response(body=response.pop())

        raise web.HTTPAccepted()

    async def create_invite(request):
        _, invitation = connections.create_invitation()
        return web.json_response({"invitation_url": invitation})

    app = web.Application()
    app.add_routes(
        [
            web.post("/", handle),
            web.get("/create_invitation_url", create_invite),
        ]
    )

    web.run_app(app, port=args.port)
    if args.replace:
        store_connection(conn)


if __name__ == "__main__":
    main()
