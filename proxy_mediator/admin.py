import logging

from aiohttp import web

from .connections import Connections

LOGGER = logging.getLogger(__name__)


def register_routes(connections: Connections, app: web.Application):
    async def retrieve_agent_invitation(request):
        return web.json_response({"invitation_url": connections.agent_invitation})

    async def receive_mediator_invitation(request: web.Request):
        body = await request.json()
        await connections.receive_mediator_invite(body["invitation_url"])
        return web.Response(status=200)

    app.add_routes(
        [
            web.get("/retrieve_agent_invitation", retrieve_agent_invitation),
            web.post("/receive_mediator_invitation", receive_mediator_invitation),
        ]
    )
    return app
