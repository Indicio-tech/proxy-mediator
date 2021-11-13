from aries_staticagent.module import Module, ModuleRouter
from aries_staticagent.utils import timestamp


class BasicMessage(Module):
    protocol = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/basicmessage/1.0"
    route = ModuleRouter(protocol)

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
