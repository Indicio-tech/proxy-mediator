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
from httpx import AsyncClient

from os import getenv


@pytest.fixture(scope="session")
def agent_alice():
    AGENT_ALICE = getenv("AGENT_ALICE", "http://agent_alice:4011")
    return Client(base_url=AGENT_ALICE)


@pytest.fixture(scope="session")
def external_mediator():
    EXTERNAL_MEDIATOR = getenv("EXTERNAL_MEDIATOR", "http://external_mediator:4013")
    return Client(base_url=EXTERNAL_MEDIATOR)


@pytest.fixture(scope="session")
def agent_bob():
    AGENT_BOB = getenv("AGENT_BOB", "http://agent_bob:4012")
    return Client(base_url=AGENT_BOB)


@pytest.fixture
async def create_invite(agent_alice: Client):
    return await create_invitation.asyncio(
        client=agent_alice,
        json_body=CreateInvitationRequest(),
        auto_accept=True,
    )


@pytest.fixture
async def receive_invite(agent_bob: Client, create_invite):
    invitation = create_invite
    return await receive_invitation.asyncio(
        client=agent_bob,
        json_body=ReceiveInvitationRequest.from_dict(invitation.invitation.to_dict()),
        auto_accept=True,
    )


@pytest.mark.asyncio
async def test_proxy_mediator_connections(
    create_invite, receive_invite, agent_bob, agent_alice, external_mediator
):
    invite = create_invite
    assert isinstance(invite, InvitationResult)

    connection = receive_invite
    assert isinstance(connection, ConnRecord)

    connection_list_alice = await get_connections.asyncio(client=agent_alice)
    connection_list_external_mediator = await get_connections.asyncio(
        client=external_mediator
    )
    # TODO add tests for state of connections

    endpoint = await get_connections_conn_id_endpoints.asyncio(
        client=agent_bob,
        conn_id=connection.connection_id,
    )
    assert endpoint.their_endpoint == "http://proxy:3000"
