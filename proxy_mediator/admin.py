import logging

from aiohttp import web

from .agent import Agent

LOGGER = logging.getLogger(__name__)


def register_routes(agent: Agent, app: web.Application):
    async def retrieve_agent_invitation(request):
        return web.json_response({"invitation_url": agent.agent_invitation})

    app.add_routes(
        [
            web.get("/retrieve_agent_invitation", retrieve_agent_invitation),
        ]
    )
    return app
