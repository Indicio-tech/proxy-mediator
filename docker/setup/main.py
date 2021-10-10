"""Automate setup of Proxy Mediator + Mediated Agent:

1. Retrieve invitation from proxy
2. Deliver to agent through Admin API
3. Request mediation from proxy
4. Set proxy as default mediator
"""

import asyncio
from base64 import urlsafe_b64decode
import json
from os import getenv

from acapy_client import Client
from acapy_client.api.connection import get_connection, receive_invitation
from acapy_client.api.mediation import (
    get_mediation_requests_mediation_id,
    post_mediation_request_conn_id,
    put_mediation_mediation_id_default_mediator,
)
from acapy_client.models.conn_record import ConnRecord
from acapy_client.models.mediation_create_request import MediationCreateRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from httpx import AsyncClient

PROXY = getenv("PROXY", "http://localhost:3000")
AGENT = getenv("AGENT", "http://localhost:3001")


async def get_proxy_invite() -> dict:
    async with AsyncClient() as client:
        r = await client.get(f"{PROXY}/retrieve_agent_invitation")
        url = r.json()["invitation_url"]
        return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))


async def agent_receive_invitation(agent: Client, invite: dict) -> ConnRecord:
    conn_record = await receive_invitation.asyncio(
        client=agent, json_body=ReceiveInvitationRequest.from_dict(invite)
    )
    if not conn_record:
        raise RuntimeError("Failed to receive invitation on agent")

    while conn_record.state != "active":
        await asyncio.sleep(1)
        assert isinstance(conn_record.connection_id, str)
        conn_record = await get_connection.asyncio(
            conn_record.connection_id, client=agent
        )
        assert conn_record

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
