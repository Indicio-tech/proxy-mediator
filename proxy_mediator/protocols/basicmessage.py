"""Basic Message Module."""
from aries_staticagent.module import Module, ModuleRouter
from aries_staticagent.utils import timestamp

from .constants import DIDCOMM, DIDCOMM_OLD


class BasicMessage(Module):
    """Basic Message Module."""

    protocol = f"{DIDCOMM_OLD}basicmessage/1.0"
    route = ModuleRouter(protocol)

    @route
    @route(doc_uri=DIDCOMM)
    async def message(self, msg, conn):
        """Automatically respond to basicmessages."""
        await conn.send_async(
            {
                "@type": self.type("message"),
                "~l10n": {"locale": "en"},
                "sent_time": timestamp(),
                "content": "You said: {}".format(msg["content"]),
            }
        )
