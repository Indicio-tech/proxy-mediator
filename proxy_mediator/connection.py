"""Connection object."""
import asyncio
from asyncio.futures import Future
import json
from typing import Optional

from aries_staticagent import Connection as AsaPyConn
from aries_staticagent import crypto
from statemachine import State, StateMachine


class Connection(AsaPyConn):
    """Wrapper around Static Agent library connection to provide state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state: str = "null"
        self._completed: Future = asyncio.get_event_loop().create_future()
        self.multiuse: bool = False
        self.invitation_key: Optional[str] = None
        self.diddoc: Optional[dict] = None

    @property
    def is_completed(self):
        return self._completed.done()

    def complete(self):
        """Complete this connection"""
        self._completed.set_result(self)

    async def completion(self) -> "Connection":
        """Await connection completion.

        For invitation connections, the connection is replaced after receiving
        a connection request. This will return the completed connection.
        """
        return await self._completed

    @classmethod
    def from_invite(cls, invite: "Connection", *args, **kwargs):
        """Transfer state from invite connection to relationship connection."""
        conn = cls.random(*args, **kwargs)
        conn.state = invite.state
        conn._completed = invite._completed
        conn.invitation_key = invite.verkey_b58
        return conn

    def to_store(self):
        """Convert Connection object to JSON object."""
        value = {
            "state": self.state,
            "multiuse": self.multiuse,
            "invitation_key": self.invitation_key,
            "did": self.did,
            "verkey": self.verkey_b58,
            "sigkey": crypto.bytes_to_b58(self.sigkey),
            "diddoc": self.diddoc,
        }
        if self.target:
            value["target"] = {
                "recipients": [
                    crypto.bytes_to_b58(recip) for recip in self.target.recipients or []
                ],
                "endpoint": self.target.endpoint,
            }
        return json.dumps(value)

    @classmethod
    def from_store(cls, value: dict, **kwargs) -> "Connection":
        """Convert JSON object into Connection object"""
        conn = cls.from_parts(
            (value["verkey"], value["sigkey"]),
            recipients=value.get("target", {}).get("recipients"),
            endpoint=value.get("target", {}).get("endpoint"),
            **kwargs
        )
        conn.state = value["state"]
        conn.multiuse = value["multiuse"]
        conn.invitation_key = value["invitation_key"]
        conn.diddoc = value["diddoc"]
        return conn


class ConnectionMachine(StateMachine):
    null = State("null", initial=True)
    invite_sent = State("invite_sent")
    invite_received = State("invited")
    request_sent = State("request_sent")
    request_received = State("requested")
    response_sent = State("response_sent")
    response_received = State("responded")
    complete = State("complete")

    send_invite = null.to(invite_sent)
    receive_request = invite_sent.to(request_received)
    send_response = request_received.to(response_sent)

    receive_invite = null.to(invite_received)
    send_request = invite_received.to(request_sent)
    receive_response = request_sent.to(response_received)
    send_ping = response_received.to(complete) | complete.to.itself()
    receive_ping = response_sent.to(complete) | complete.to.itself()
    send_ping_response = complete.to.itself()
    receive_ping_response = complete.to.itself()
