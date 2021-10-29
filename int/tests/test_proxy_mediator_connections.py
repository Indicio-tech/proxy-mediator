import pytest
from acapy_client import Client
from acapy_client.api.connection import (
    get_connection,
    receive_invitation,
    create_invitation,
)
from acapy_client.api.mediation import (
    get_mediation_requests_mediation_id,
    post_mediation_request_conn_id,
    put_mediation_mediation_id_default_mediator,
)
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.mediation_create_request import MediationCreateRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest


@pytest.fixture(scope="session")
def alice():
    yield Client(base_url="http://agent_alice:4011")


@pytest.fixture(scope="session")
def bob():
    yield Client(base_url="http://agent_bob:4012")


@pytest.fixture
async def create_invitation(client: alice):
    return await create_invitation.asyncio(
        client=alice, json_body=CreateInvitationRequest(), auto_accept="true"
    )


@pytest.fixture
async def receive_invitation(create_invitation):
    return await receive_invitation.asyncio(
        client=bob,
        json_body=ReceiveInvitationRequest.from_dict(
            create_invitation.invitation.to_dict()
        ),
        auto_accept="true",
    )


@pytest.mark.asyncio
def test_proxy_mediator_connections():
    assert True
