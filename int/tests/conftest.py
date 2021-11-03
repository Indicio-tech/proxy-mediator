"""Automate setup of Proxy Mediator + Mediated Agent:

1. Retrive invitation from mediator
2. Receive invitation in proxy
3. Retrieve invitation from proxy
4. Deliver to agent through Admin API
5. Request mediation from proxy
6. Set proxy as default mediator
"""

import asyncio
from base64 import urlsafe_b64decode
import json
from os import getenv

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
    get_mediation_requests,
)
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.create_invitation_request import CreateInvitationRequest
from acapy_client.models.mediation_create_request import MediationCreateRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from acapy_client.models.get_mediation_requests_state import GetMediationRequestsState
from acapy_client.types import Unset

from httpx import AsyncClient
import pytest


PROXY = getenv("PROXY", "http://proxy:3000")
AGENT_BOB = getenv("AGENT_BOB", "http://agent_bob:4012")
EXTERNAL_MEDIATOR = getenv("EXTERNAL_MEDIATOR", "http://external_mediator:4013")


async def get_proxy_invite() -> dict:
    async with AsyncClient() as client:
        url = None
        while url is None:
            r = await client.get(f"{PROXY}/retrieve_agent_invitation")
            url = r.json()["invitation_url"]
            if not url:
                await asyncio.sleep(1)
        return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))


async def get_mediator_invite(external_mediator: Client) -> str:
    invitation = await create_invitation.asyncio(
        client=external_mediator, json_body=CreateInvitationRequest()
    )
    if not invitation:
        raise RuntimeError("Failed to retrieve invitation from mediator")
    assert not isinstance(invitation.invitation_url, Unset)
    return invitation.invitation_url


async def proxy_receive_mediator_invite(external_mediator: Client, invite: str):
    async with AsyncClient() as client:
        r = await client.post(
            f"{PROXY}/receive_mediator_invitation", json={"invitation_url": invite}
        )
        assert not r.is_error

    # Get mediator mediation requests
    requests = await get_mediation_requests.asyncio(
        client=external_mediator, state=GetMediationRequestsState.GRANTED
    )
    assert requests
    assert not isinstance(requests.results, Unset)
    while not requests.results:
        await asyncio.sleep(1)
        requests = await get_mediation_requests.asyncio(
            client=external_mediator, state=GetMediationRequestsState.GRANTED
        )
        assert requests
        assert not isinstance(requests, Unset)


async def get_proxy_invite() -> dict:
    async with AsyncClient() as client:
        url = None
        while url is None:
            r = await client.get(f"{PROXY}/retrieve_agent_invitation")
            url = r.json()["invitation_url"]
            if not url:
                await asyncio.sleep(1)
        return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))


async def agent_receive_invitation(agent_bob: Client, invite: dict) -> ConnRecord:
    conn_record = await receive_invitation.asyncio(
        client=agent_bob, json_body=ReceiveInvitationRequest.from_dict(invite)
    )
    if not conn_record:
        raise RuntimeError("Failed to receive invitation on agent")

    while conn_record.state != "active":
        await asyncio.sleep(1)
        assert isinstance(conn_record.connection_id, str)
        conn_record = await get_connection.asyncio(
            conn_record.connection_id, client=agent_bob
        )
        assert conn_record

    return conn_record


async def agent_request_mediation_from_proxy(agent_bob: Client, conn_id: str):
    mediation_record = await post_mediation_request_conn_id.asyncio(
        conn_id=conn_id, client=agent_bob, json_body=MediationCreateRequest()
    )
    if not mediation_record:
        raise RuntimeError(f"Failed to request mediation from {conn_id}")

    while mediation_record.state != "granted":
        await asyncio.sleep(1)
        assert isinstance(mediation_record.mediation_id, str)
        mediation_record = await get_mediation_requests_mediation_id.asyncio(
            mediation_record.mediation_id, client=agent_bob
        )
        assert mediation_record

    return mediation_record


async def agent_set_default_mediator(agent_bob: Client, mediation_id: str):
    result = await put_mediation_mediation_id_default_mediator.asyncio(
        mediation_id, client=agent_bob
    )
    if not result:
        raise RuntimeError(f"Failed to set default mediator to {mediation_id}")
    return result


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@pytest.fixture(autouse=True, scope="session")
async def setup():
    agent_bob = Client(base_url=AGENT_BOB)
    external_mediator = Client(base_url=EXTERNAL_MEDIATOR)
    mediator_invite = await get_mediator_invite(external_mediator)
    await proxy_receive_mediator_invite(external_mediator, mediator_invite)
    invite = await get_proxy_invite()
    conn_record = await agent_receive_invitation(agent_bob, invite)

    assert conn_record
    assert isinstance(conn_record.connection_id, str)
    mediation_record = await agent_request_mediation_from_proxy(
        agent_bob, conn_record.connection_id
    )

    assert mediation_record
    assert isinstance(mediation_record.mediation_id, str)
    await agent_set_default_mediator(agent_bob, mediation_record.mediation_id)
