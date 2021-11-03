from functools import partial
from os import getenv

from acapy_client import Client
from acapy_client.api.connection import (
    create_invitation,
    get_connection,
    receive_invitation,
)
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.create_invitation_request import CreateInvitationRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from acapy_client.types import Unset
import pytest

from . import record_state


@pytest.fixture(scope="session")
def agent_alice():
    AGENT_ALICE = getenv("AGENT_ALICE", "http://agent_alice:4011")
    return Client(base_url=AGENT_ALICE)


@pytest.fixture(scope="session")
def agent_bob():
    AGENT_BOB = getenv("AGENT_BOB", "http://agent_bob:4012")
    return Client(base_url=AGENT_BOB)


@pytest.fixture
async def agent_fixture():
    def _agent_fixture(agent):
        return agent

    yield _agent_fixture


@pytest.fixture
async def create_connection(agent_fixture):
    """Factory fixture to create a connection with
    sender and receiver as parameters"""

    async def _create_connection(sender: Client, receiver: Client):
        sender = agent_fixture(sender)
        receiver = agent_fixture(receiver)
        invite = await create_invitation.asyncio(
            client=sender,
            json_body=CreateInvitationRequest(),
            auto_accept=True,
        )
        assert invite
        assert not isinstance(invite.invitation, Unset)
        connection = await receive_invitation.asyncio(
            client=receiver,
            json_body=ReceiveInvitationRequest.from_dict(invite.invitation.to_dict()),
            auto_accept=True,
        )
        return (invite, connection)

    yield _create_connection


@pytest.mark.asyncio
async def test_connection_from_alice(create_connection, agent_alice, agent_bob):
    invite, connection = await create_connection(agent_alice, agent_bob)
    assert invite.invitation.service_endpoint == "http://agent_alice:4011"

    invitation_alice = await get_connection.asyncio(
        conn_id=invite.connection_id, client=agent_alice
    )
    assert invitation_alice
    print("invitation state (on Alice)", invitation_alice.state)
    connection_bob = await get_connection.asyncio(
        conn_id=connection.connection_id, client=agent_bob
    )
    assert connection_bob
    print("connection state (on Bob)", connection_bob.state)

    async def _retrieve(client: Client, connection_id: str) -> ConnRecord:
        retrieved = await get_connection.asyncio(
            conn_id=connection_id,
            client=client,
        )
        assert retrieved
        return retrieved

    await record_state("active", partial(_retrieve, agent_alice, invite.connection_id))
    await record_state(
        "active", partial(_retrieve, agent_bob, connection.connection_id)
    )


@pytest.mark.asyncio
async def test_connection_from_bob(create_connection, agent_alice, agent_bob):
    invite, connection = await create_connection(agent_bob, agent_alice)
    assert invite.invitation.service_endpoint == "http://reverse-proxy"

    invitation_bob = await get_connection.asyncio(
        conn_id=invite.connection_id, client=agent_bob
    )
    assert invitation_bob
    print("invitation state (on Bob)", invitation_bob.state)
    connection_alice = await get_connection.asyncio(
        conn_id=connection.connection_id, client=agent_alice
    )
    assert connection_alice
    print("connection state (on Alice)", connection_alice.state)

    async def _retrieve(client: Client, connection_id: str) -> ConnRecord:
        retrieved = await get_connection.asyncio(
            conn_id=connection_id,
            client=client,
        )
        assert retrieved
        return retrieved

    await record_state("active", partial(_retrieve, agent_bob, invite.connection_id))
    await record_state(
        "active", partial(_retrieve, agent_alice, connection.connection_id)
    )
