from functools import partial
from os import getenv

from acapy_client import Client
from acapy_client.api.connection import (
    create_invitation,
    get_connection,
    receive_invitation,
    get_connections_conn_id_endpoints,
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
async def create_connection():
    """Factory fixture to create a connection with
    sender and receiver as parameters"""

    async def _create_connection(sender: Client, receiver: Client):
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


agents = [
    ("agent_alice", "agent_bob", "http://agent_alice:4011"),
    ("agent_bob", "agent_alice", "http://reverse-proxy"),
]


@pytest.mark.parametrize("sender, receiver, endpoint", agents)
@pytest.mark.asyncio
async def test_connection_from_alice(
    sender, receiver, endpoint, create_connection, request
):
    sender = request.getfixturevalue(sender)
    receiver = request.getfixturevalue(receiver)
    invite, connection = await create_connection(sender, receiver)
    assert invite.invitation.service_endpoint == endpoint

    async def _retrieve(client: Client, connection_id: str) -> ConnRecord:
        retrieved = await get_connection.asyncio(
            conn_id=connection_id,
            client=client,
        )
        assert retrieved
        return retrieved

    await record_state("active", partial(_retrieve, sender, invite.connection_id))
    await record_state("active", partial(_retrieve, receiver, connection.connection_id))

    endpoint_retrieved = await get_connections_conn_id_endpoints.asyncio(
        conn_id=invite.connection_id,
        client=sender,
    )
    assert endpoint_retrieved
    assert endpoint_retrieved.my_endpoint == endpoint
