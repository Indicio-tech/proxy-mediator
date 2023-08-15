import asyncio

from typing import Any, Awaitable, Callable, Optional, TypeVar


Subject = TypeVar("Subject", bound=Any)


async def poll_until_condition(
    condition: Callable[[Subject], bool],
    retrieve: Callable[[], Awaitable[Subject]],
    *,
    initial: Optional[Subject] = None,
    timeout: float = 7.5,
    interval: float = 2.0
) -> Subject:
    async def _timeboxed(subject: Subject):
        while not condition(subject):
            await asyncio.sleep(interval)
            subject = await retrieve()
            assert subject

        return subject

    initial = initial or await retrieve()
    assert initial
    return await asyncio.wait_for(_timeboxed(initial), timeout)


async def record_state(
    state: str,
    retrieve: Callable[[], Awaitable[Subject]],
    *,
    initial: Optional[Subject] = None,
    timeout: float = 5.0,
    interval: float = 1.0
) -> Subject:
    """Wait for the state of the record to change to a given value."""
    return await poll_until_condition(
        lambda rec: rec.state == state,
        retrieve,
        initial=initial,
        timeout=timeout,
        interval=interval,
    )
