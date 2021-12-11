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
from functools import partial, wraps
import json
from os import getenv
from typing import Any, Awaitable, Callable, TypeVar, cast

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
from acapy_client.models.mediation_record import MediationRecord
from acapy_client.models.ping_request import PingRequest
from acapy_client.models.receive_invitation_request import ReceiveInvitationRequest
from acapy_client.types import Unset
from httpx import AsyncClient

PROXY = getenv("PROXY", "http://localhost:3000")
AGENT = getenv("AGENT", "http://localhost:3001")
MEDIATOR = getenv("MEDIATOR")
MEDIATOR_INVITE = getenv("MEDIATOR_INVITE")

Subject = TypeVar("Subject")
Func = TypeVar("Func", bound=Callable)


class PollingFailed(Exception):
    """Raised when polling fails."""


async def poll(
    operation: Callable[[], Awaitable[Subject]],
    condition: Callable[[Subject], bool],
    *,
    interval: float = 3.0,
    max_retry: int = 10,
    error_msg: str = None,
) -> Subject:
    count = 0
    subject = await operation()
    while not condition(subject) and count < max_retry:
        count += 1
        await asyncio.sleep(interval)
        subject = await operation()

    if not condition(subject):
        raise PollingFailed(error_msg or "Polling failed")

    return subject


def poller(
    func: Func = None,
    *,
    until: Callable[[Any], bool] = None,
    interval: float = 3.0,
    max_retry: int = 10,
    error_msg: str = None,
) -> Func:
    if not func:
        return cast(
            Func,
            lambda f: poller(
                f,
                until=until,
                interval=interval,
                max_retry=max_retry,
                error_msg=error_msg,
            ),
        )

    if not until:
        until = bool

    @wraps(func)
    async def _poll_wrapper(*args, **kwargs):
        return await poll(
            partial(func, *args, **kwargs),
            until,
            interval=interval,
            max_retry=max_retry,
            error_msg=error_msg,
        )

    return cast(Func, _poll_wrapper)


class Proxy:
    """Interact with proxy."""

    def __init__(self, client: AsyncClient):
        self.client = client

    async def receive_mediator_invite(self, invite: str):
        r = await self.client.post(
            "/receive_mediator_invitation", json={"invitation_url": invite}
        )
        assert not r.is_error

    async def get_status(self) -> str:
        r = await self.client.get("/status")
        assert not r.is_error
        return r.json().get("status")

    async def await_status(self, state: str):
        return await poll(
            self.get_status,
            lambda retrieved: retrieved == state,
            interval=1,
            max_retry=3,
        )

    @poller(until=lambda state: state != "init")
    async def initialized(self):
        return await self.get_status()

    @poller(
        error_msg=(
            "Failed to retrieve invitation from proxy. "
            "Did the proxy successfully connect to mediator?"
        )
    )
    async def _get_invite(self) -> str:
        r = await self.client.get("/retrieve_agent_invitation")
        return r.json().get("invitation_url")

    async def get_invite(self) -> dict:
        url = await self._get_invite()
        return json.loads(urlsafe_b64decode(url.split("c_i=")[1]))


class Acapy:

    conn_states_order = {"invitation": 0, "request": 1, "response": 2, "active": 3}

    def __init__(self, client: Client):
        self.client = client

    async def get_invite(self) -> str:
        invitation = await create_invitation.asyncio(
            client=self.client, json_body=CreateInvitationRequest()
        )
        if not invitation:
            raise RuntimeError("Failed to retrieve invitation from mediator")
        assert not isinstance(invitation.invitation_url, Unset)
        return invitation.invitation_url

    async def get_connection(self, connection_id: str):
        conn = await get_connection.asyncio(connection_id, client=self.client)
        assert conn
        return conn

    async def get_connection_state(self, connection_id: str) -> str:
        conn = await self.get_connection(connection_id)
        assert isinstance(conn.state, str)
        return conn.state

    async def await_connection_state(self, connection_id: str, state: str):
        return await poll(
            partial(self.get_connection, connection_id),
            lambda conn: isinstance(conn.state, str)
            and self.conn_states_order[conn.state] >= self.conn_states_order[state],
        )

    async def receive_invitation(self, invite: dict) -> ConnRecord:
        conn_record = await receive_invitation.asyncio(
            client=self.client,
            json_body=ReceiveInvitationRequest.from_dict(invite),
            auto_accept="true",
        )

        assert conn_record
        assert isinstance(conn_record.connection_id, str)
        connection_id: str = conn_record.connection_id

        if not conn_record:
            raise RuntimeError("Failed to receive invitation on agent")

        conn_record = await self.await_connection_state(connection_id, "response")
        if conn_record.state == "response":
            await post_connections_conn_id_send_ping.asyncio(
                client=self.client, conn_id=connection_id, json_body=PingRequest()
            )
            conn_record = await self.await_connection_state(connection_id, "active")

        return conn_record

    @poller(until=lambda rec: rec.state == "granted")
    async def _granted_mediation(self, mediation_id: str) -> MediationRecord:
        mediation_record = await get_mediation_requests_mediation_id.asyncio(
            mediation_id, client=self.client
        )
        assert mediation_record
        return mediation_record

    async def request_mediation(self, conn_id: str):
        mediation_record = await post_mediation_request_conn_id.asyncio(
            conn_id=conn_id, client=self.client, json_body=MediationCreateRequest()
        )
        if not mediation_record:
            raise RuntimeError(f"Failed to request mediation from {conn_id}")
        assert isinstance(mediation_record.mediation_id, str)
        return await self._granted_mediation(mediation_record.mediation_id)

    async def set_default_mediator(self, mediation_id: str):
        result = await put_mediation_mediation_id_default_mediator.asyncio(
            mediation_id, client=self.client
        )
        if not result:
            raise RuntimeError(f"Failed to set default mediator to {mediation_id}")
        return result


async def main():
    async with AsyncClient(base_url=PROXY) as client:
        proxy = Proxy(client)
        await proxy.initialized()
        state = await proxy.get_status()
        if state == "ready":
            print("Proxy is ready.")
            return
        else:
            print(f"Proxy state: {state}")

        agent = Acapy(Client(base_url=AGENT, timeout=5.0))

        if MEDIATOR and not MEDIATOR_INVITE:
            mediator = Acapy(Client(base_url=MEDIATOR, timeout=5.0))
            mediator_invite = await mediator.get_invite()
        elif MEDIATOR_INVITE:
            mediator_invite = MEDIATOR_INVITE
        else:
            raise RuntimeError(
                "MEDIATOR or MEDIATOR_INVITE environment variable must be set"
            )

        await proxy.receive_mediator_invite(mediator_invite)
        print("Proxy and mediator are now connected.")

        invite = await proxy.get_invite()
        conn_record = await agent.receive_invitation(invite)

        print("Proxy and agent are now connected.")
        print(f"Proxy connection id: {conn_record.connection_id}")

        assert isinstance(conn_record.connection_id, str)
        mediation_record = await agent.request_mediation(conn_record.connection_id)
        print("Proxy has granted mediation to agent.")
        print(f"Proxy mediation id: {mediation_record.mediation_id}")

        assert mediation_record
        assert isinstance(mediation_record.mediation_id, str)
        await agent.set_default_mediator(mediation_record.mediation_id)
        print("Proxy mediator is now default mediator for agent.")


if __name__ == "__main__":
    asyncio.run(main())
