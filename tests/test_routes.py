"""Test routes are correctly set in agent."""

from proxy_mediator.protocols.routing import Routing

SOV_DOC_URI = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
DIDCOMM_DOC_URI = "https://didcomm.org/"


def test_routing_protocol_routes():
    routing = Routing()
    assert f"{Routing.protocol}/forward" in routing.routes
    assert (
        f"{DIDCOMM_DOC_URI}{routing.protocol_name}/{routing.version}/forward"
        in routing.routes
    )
