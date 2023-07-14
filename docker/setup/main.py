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
from typing import Any, Awaitable, Callable, Optional, TypeVar, cast

from httpx import AsyncClient

from controller.controller import Controller
from controller.models import InvitationRecord, ConnRecord, MediationRecord

PROXY = getenv("PROXY", "http://localhost:3000")
AGENT = getenv("AGENT", "http://localhost:3001")
AGENT_HEADERS = getenv("AGENT_HEADERS", "{}")
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
    error_msg: Optional[str] = None,
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
    func: Optional[Func] = None,
    *,
    until: Optional[Callable[[Any], bool]] = None,
    interval: float = 3.0,
    max_retry: int = 10,
    error_msg: Optional[str] = None,
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
        return json.loads(urlsafe_b64decode(url.split("oob=")[1]))


class Acapy:
    conn_states_order = {"invitation": 0, "request": 1, "response": 2, "active": 3}

    def __init__(self, controller: Controller):
        self.controller = controller

    async def get_invite(self) -> str:
        invitation = await self.controller.post(
            "/out-of-band/create-invitation",
            json={
                "accept": ["didcomm/aip1", "didcomm/aip2;env=rfc19"],
                "handshake_protocols": [
                    "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/didexchange/1.0",
                    "https://didcomm.org/didexchange/1.0",
                ],
                "protocol_version": "1.1",
            },
            response=InvitationRecord,
        )
        return invitation.invitation_url

    async def receive_invitation(self, invite: dict) -> ConnRecord:
        oob_record = await self.controller.post(
            "/out-of-band/receive-invitation",
            json=invite,
            params={"auto_accept": "true"},
        )

        conn_record = await self.controller.record_with_values(
            "connections",
            record_type=ConnRecord,
            invitation_msg_id=oob_record["invi_msg_id"],
            rfc23_state="completed",
        )
        return conn_record

    async def request_mediation(self, conn_id: str):
        await self.controller.post(
            f"/mediation/request/{conn_id}",
        )
        mediation_record = await self.controller.record_with_values(
            "mediation",
            record_type=MediationRecord,
            state="granted",
        )
        return mediation_record

    async def set_default_mediator(self, mediation_id: str):
        result = await self.controller.put(
            f"/mediation/{mediation_id}/default-mediator",
        )
        return result


async def main():
    async with AsyncClient(base_url=PROXY, timeout=60.0) as client, Controller(
        AGENT, headers=json.loads(AGENT_HEADERS)
    ) as controller:
        proxy = Proxy(client)
        await proxy.initialized()
        state = await proxy.get_status()
        if state == "ready":
            print("Proxy is ready.")
            return
        else:
            print(f"Proxy state: {state}")

        if MEDIATOR and not MEDIATOR_INVITE:
            async with Controller(MEDIATOR) as mediator:
                mediator_invite = await Acapy(mediator).get_invite()
        elif MEDIATOR_INVITE:
            mediator_invite = MEDIATOR_INVITE
        else:
            raise RuntimeError(
                "MEDIATOR or MEDIATOR_INVITE environment variable must be set"
            )

        await proxy.receive_mediator_invite(mediator_invite)
        print("Proxy and mediator are now connected.")

        invite = await proxy.get_invite()
        agent = Acapy(controller)
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
