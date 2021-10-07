import logging

from aiohttp import web

from .connections import Connections

LOGGER = logging.getLogger(__name__)


def register_routes(connections: Connections, app: web.Application):
    async def create_invite(request):
        _, invitation = connections.create_invitation()
        return web.json_response({"invitation_url": invitation})

    async def receive_invite(request):
        LOGGER.debug("receive_invite called")
        req = await request.json()
        invitation_url = req["invitation_url"]
        await connections.receive_invite_url(invitation_url)
        return web.json_response({"success": True})

    app.add_routes(
        [
            web.get("/create_invitation", create_invite),
            web.post("/receive_invitation", receive_invite),
        ]
    )
    return app
