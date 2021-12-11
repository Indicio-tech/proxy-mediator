import logging

from aiohttp import web

from .protocols.connections import Connections
from .agent import Agent

LOGGER = logging.getLogger(__name__)


def register_routes(app: web.Application):
    connections = Connections.get()
    agent = Agent.get()

    async def retrieve_agent_invitation(request):
        return web.json_response({"invitation_url": connections.agent_invitation})

    async def receive_mediator_invitation(request: web.Request):
        body = await request.json()
        await connections.receive_mediator_invite(body["invitation_url"])
        return web.Response(status=200)

    async def status(request: web.Request):
        return web.json_response({"status": agent.state})

    app.add_routes(
        [
            web.get("/retrieve_agent_invitation", retrieve_agent_invitation),
            web.post("/receive_mediator_invitation", receive_mediator_invitation),
            web.get("/status", status),
        ]
    )
    return app
