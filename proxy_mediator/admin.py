from base64 import urlsafe_b64decode
import json
import logging

from aiohttp import web
from aries_staticagent.message import Message

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
        invite_msg = Message.parse_obj(
            json.loads(urlsafe_b64decode(invitation_url.split("c_i=")[1]))
        )
        await connections.receive_invite(invite_msg)
        return web.json_response({"success": True})

    app.add_routes(
        [
            web.get("/create_invitation", create_invite),
            web.post("/receive_invitation", receive_invite),
        ]
    )
    return app
