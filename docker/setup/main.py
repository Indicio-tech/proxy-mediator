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

from acapy_client.api.connection import (
    create_invitation,
    get_connection,
    receive_invitation,
)
from acapy_client.api.mediation import (
    get_mediation_requests_mediation_id,
    post_mediation_request_conn_id,
    put_mediation_mediation_id_default_mediator,
)
from acapy_client.api.trustping import post_connections_conn_id_send_ping
from acapy_client.client import Client
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.create_invitation_request import CreateInvitationRequest
from acapy_client.models.mediation_create_request import MediationCreateRequest
from acapy_client.models.ping_request import PingRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from acapy_client.types import Unset
from httpx import AsyncClient

PROXY = getenv("PROXY", "http://localhost:3000")
AGENT = getenv("AGENT", "http://localhost:3001")
MEDIATOR = getenv("MEDIATOR")
MEDIATOR_INVITE = getenv("MEDIATOR_INVITE")


async def get_mediator_invite(mediator: Client) -> str:
    invitation = await create_invitation.asyncio(
        client=mediator, json_body=CreateInvitationRequest()
    )
    if not invitation:
        raise RuntimeError("Failed to retrieve invitation from mediator")
    assert not isinstance(invitation.invitation_url, Unset)
    return invitation.invitation_url


async def proxy_receive_mediator_invite(invite: str):
    async with AsyncClient() as client:
        r = await client.post(
            f"{PROXY}/receive_mediator_invitation", json={"invitation_url": invite}
        )
        assert not r.is_error


async def get_proxy_invite() -> dict:
    async with AsyncClient() as client:
        url = None
        count = 0
        while url is None and count < 10:
            count += 1
            r = await client.get(f"{PROXY}/retrieve_agent_invitation")
            url = r.json().get("invitation_url")
            if not url:
                await asyncio.sleep(3)
        if url:
            return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))
        raise RuntimeError(
            "Failed to retrieve invitation from proxy. "
            "Did the proxy successfully connect to mediator?"
        )


async def agent_receive_invitation(agent: Client, invite: dict) -> ConnRecord:
    conn_record = await receive_invitation.asyncio(
        client=agent, json_body=ReceiveInvitationRequest.from_dict(invite)
    )

    conn_states_order = {"invite": 0, "request": 1, "response": 2, "active": 3}

    async def _connection_state(conn_record: ConnRecord, state: str):
        count = 0
        assert isinstance(conn_record.state, str)
        while (
            conn_states_order[conn_record.state] <= conn_states_order[state]
            and count < 10
        ):
            count += 1
            await asyncio.sleep(3)
            assert isinstance(conn_record.connection_id, str)
            retrieved = await get_connection.asyncio(
                conn_record.connection_id, client=agent
            )
            assert retrieved
            conn_record = retrieved
            assert isinstance(conn_record.state, str)

    if not conn_record:
        raise RuntimeError("Failed to receive invitation on agent")

    await _connection_state(conn_record, "response")
    if conn_record.state == "response":
        assert isinstance(conn_record.connection_id, str)
        await post_connections_conn_id_send_ping.asyncio(
            client=agent, conn_id=conn_record.connection_id, json_body=PingRequest()
        )
        await _connection_state(conn_record, "active")

    return conn_record


async def agent_request_mediation_from_proxy(agent: Client, conn_id: str):
    mediation_record = await post_mediation_request_conn_id.asyncio(
        conn_id=conn_id, client=agent, json_body=MediationCreateRequest()
    )
    if not mediation_record:
        raise RuntimeError(f"Failed to request mediation from {conn_id}")

    while mediation_record.state != "granted":
        await asyncio.sleep(1)
        assert isinstance(mediation_record.mediation_id, str)
        mediation_record = await get_mediation_requests_mediation_id.asyncio(
            mediation_record.mediation_id, client=agent
        )
        assert mediation_record

    return mediation_record


async def agent_set_default_mediator(agent: Client, mediation_id: str):
    result = await put_mediation_mediation_id_default_mediator.asyncio(
        mediation_id, client=agent
    )
    if not result:
        raise RuntimeError(f"Failed to set default mediator to {mediation_id}")
    return result


async def main():
    agent = Client(base_url=AGENT)

    if MEDIATOR and not MEDIATOR_INVITE:
        mediator = Client(base_url=MEDIATOR)
        mediator_invite = await get_mediator_invite(mediator)
    elif MEDIATOR_INVITE:
        mediator_invite = MEDIATOR_INVITE
    else:
        raise RuntimeError(
            "MEDIATOR or MEDIATOR_INVITE environment variable must be set"
        )

    await proxy_receive_mediator_invite(mediator_invite)
    invite = await get_proxy_invite()
    conn_record = await agent_receive_invitation(agent, invite)
    print("Proxy and agent are now connected.")
    print(f"Proxy connection id: {conn_record.connection_id}")

    assert conn_record
    assert isinstance(conn_record.connection_id, str)
    mediation_record = await agent_request_mediation_from_proxy(
        agent, conn_record.connection_id
    )
    print("Proxy has granted mediation to agent.")
    print(f"Proxy mediation id: {mediation_record.mediation_id}")

    assert mediation_record
    assert isinstance(mediation_record.mediation_id, str)
    await agent_set_default_mediator(agent, mediation_record.mediation_id)

    print("Proxy mediator is now default mediator for agent.")


if __name__ == "__main__":
    asyncio.run(main())
