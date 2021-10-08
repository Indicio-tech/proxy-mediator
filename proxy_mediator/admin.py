import logging

from aiohttp import web

from .connections import Connections

LOGGER = logging.getLogger(__name__)


def register_routes(connections: Connections, app: web.Application):
    async def retrieve_agent_invitation(request):
        return web.json_response({"invitation_url": connections.agent_invitation})

    app.add_routes(
        [
            web.get("/retrieve_agent_invitation", retrieve_agent_invitation),
        ]
    )
    return app
