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

from controller.controller import Controller
from controller.models import ConnRecord, InvitationResult, MediationRecord
from httpx import AsyncClient
import pytest
import pytest_asyncio


PROXY = getenv("PROXY", "http://proxy:3000")
AGENT_BOB = getenv("AGENT_BOB", "http://agent_bob:4012")
EXTERNAL_MEDIATOR = getenv("EXTERNAL_MEDIATOR", "http://external_mediator:4013")


async def get_proxy_invite() -> dict:
    async with AsyncClient(timeout=60.0) as client:
        url = None
        while url is None:
            r = await client.get(f"{PROXY}/retrieve_agent_invitation")
            url = r.json()["invitation_url"]
            if not url:
                await asyncio.sleep(1)
        return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))


async def get_mediator_invite(external_mediator: Controller) -> str:
    invitation = await external_mediator.post(
        "/connections/create-invitation",
        params={"auto_accept": "true"},
        response=InvitationResult,
    )
    return invitation.invitation_url


async def proxy_receive_mediator_invite(external_mediator: Controller, invite: str):
    async with AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{PROXY}/receive_mediator_invitation", json={"invitation_url": invite}
        )
        assert not r.is_error

    await external_mediator.record_with_values("mediation", state="granted")


async def agent_receive_invitation(agent_bob: Controller, invite: dict) -> ConnRecord:
    conn_record = await agent_bob.post(
        "/connections/receive-invitation",
        json=invite,
        response=ConnRecord,
    )

    conn_record = await agent_bob.record_with_values(
        "connections",
        record_type=ConnRecord,
        connection_id=conn_record.connection_id,
        state="active",
    )
    return conn_record


async def agent_request_mediation_from_proxy(agent_bob: Controller, conn_id: str):
    await agent_bob.post(
        f"/mediation/request/{conn_id}",
    )
    mediation_record = await agent_bob.record_with_values(
        "mediation",
        record_type=MediationRecord,
        state="granted",
    )
    return mediation_record


async def agent_set_default_mediator(agent_bob: Controller, mediation_id: str):
    result = await agent_bob.put(
        f"/mediation/{mediation_id}/default-mediator",
    )
    return result


@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True, scope="session")
async def setup():
    async with Controller(AGENT_BOB) as agent_bob, Controller(
        EXTERNAL_MEDIATOR
    ) as external_mediator:
        mediator_invite = await get_mediator_invite(external_mediator)
        await proxy_receive_mediator_invite(external_mediator, mediator_invite)
        invite = await get_proxy_invite()
        conn_record = await agent_receive_invitation(agent_bob, invite)
        mediation_record = await agent_request_mediation_from_proxy(
            agent_bob, conn_record.connection_id
        )
        assert mediation_record.mediation_id
        await agent_set_default_mediator(agent_bob, mediation_record.mediation_id)
