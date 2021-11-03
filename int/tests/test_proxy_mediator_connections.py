import pytest
from acapy_client import Client
from acapy_client.api.connection import (
    get_connection,
    get_connections,
    receive_invitation,
    create_invitation,
    get_connections_conn_id_endpoints,
)
from acapy_client.api.mediation import (
    get_mediation_requests_mediation_id,
    post_mediation_request_conn_id,
    put_mediation_mediation_id_default_mediator,
)
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.mediation_create_request import MediationCreateRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from acapy_client.models.create_invitation_request import CreateInvitationRequest
from acapy_client.models.invitation_result import InvitationResult
from acapy_client.models.connection_list import ConnectionList

from os import getenv


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
        connection = await receive_invitation.asyncio(
            client=receiver,
            json_body=ReceiveInvitationRequest.from_dict(invite.invitation.to_dict()),
            auto_accept=True,
        )
        return (invite, connection)

    yield _create_connection


@pytest.mark.asyncio
async def test_connection_from_alice(
    create_connection, agent_fixture, agent_alice, agent_bob
):
    connection = await create_connection(agent_alice, agent_bob)
    assert connection[0].invitation.service_endpoint == "http://agent_alice:4011"

    invitation_alice = await get_connection.asyncio(
        conn_id=connection[0].connection_id, client=agent_alice
    )
    print("invitation state (on Alice)", invitation_alice.state)
    connection_bob = await get_connection.asyncio(
        conn_id=connection[1].connection_id, client=agent_bob
    )
    print("connection state (on Bob)", connection_bob.state)
