from aries_staticagent.module import Module, ModuleRouter


class CoordinateMediation(Module):
    doc_uri = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
    protocol = "coordinate-mediation"
    version = "1.0"
    route = ModuleRouter()

    # TODO obtain endpoint and routing keys outside of handler method
    mediation_endpoint = "mediation_endpoint placeholder"
    mediation_routing_keys = "mediation_routing_keys placeholder"

    @route(name="mediate-grant")
    async def mediate_grant(self, msg, conn):
        await conn.send_async(
            {
                "@type": "https://didcomm.org/coordinate-mediation/1.0/mediate-grant",
                "endpoint": self.mediation_endpoint,
                "routing_keys": self.mediation_routing_keys,
            }
        )
