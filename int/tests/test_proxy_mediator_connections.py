from os import getenv

import pytest
import pytest_asyncio
from controller.controller import Controller
from controller.models import EndpointsResult, InvitationResult, ConnRecord


@pytest_asyncio.fixture(scope="session")
async def alice():
    ALICE = getenv("ALICE", "http://alice:3001")
    async with Controller(ALICE) as controller:
        yield controller


@pytest_asyncio.fixture(scope="session")
async def bob():
    BOB = getenv("BOB", "http://bob:3001")
    async with Controller(BOB) as controller:
        yield controller


agents = [
    ("alice", "bob", "http://alice:3000"),
    ("bob", "alice", "http://reverse-proxy"),
]


@pytest.mark.parametrize("sender_name, receiver_name, endpoint", agents)
@pytest.mark.asyncio
async def test_connection_from_alice(
    sender_name: str,
    receiver_name: str,
    endpoint: str,
    alice: Controller,
    bob: Controller,
):
    agents = {
        "alice": alice,
        "bob": bob,
    }
    sender: Controller = agents[sender_name]
    receiver: Controller = agents[receiver_name]
    invite = await sender.post(
        "/connections/create-invitation",
        json={},
        params={"auto_accept": "true"},
        response=InvitationResult,
    )
    assert invite
    connection = await receiver.post(
        "/connections/receive-invitation",
        json=invite.invitation,
        params={"auto_accept": "true"},
        response=ConnRecord,
    )

    assert invite.invitation.service_endpoint == endpoint

    await sender.record_with_values(
        "connections",
        connection_id=invite.connection_id,
        state="active",
    )
    await receiver.record_with_values(
        "connections", connection_id=connection.connection_id, state="active"
    )

    endpoint_retrieved = await receiver.get(
        f"/connections/{connection.connection_id}/endpoints", response=EndpointsResult
    )
    assert endpoint_retrieved
    assert endpoint_retrieved.their_endpoint == endpoint
