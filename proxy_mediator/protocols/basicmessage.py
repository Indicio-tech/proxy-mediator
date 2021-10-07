from aries_staticagent.module import Module, ModuleRouter
from aries_staticagent.utils import timestamp


class BasicMessage(Module):
    doc_uri = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
    protocol = "basicmessage"
    version = "1.0"
    route = ModuleRouter()

    @route
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
