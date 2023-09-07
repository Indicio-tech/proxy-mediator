"""Errors and error related utilities."""


from abc import ABC
import functools
import logging
from typing import Callable, ClassVar, Optional, Tuple, Type, Union, cast

from aries_staticagent.message import BaseMessage, Message
from inflection import dasherize, underscore
from pydantic.main import BaseModel, Extra

from .agent import Connection


LOGGER = logging.getLogger(__name__)


class ProtocolError(Exception):
    """Raised when an error occurs in a protocol."""


class Reportable(Exception, ABC):
    """Abstract Base Class for exceptions that can be sent as problem reports."""

    code: ClassVar[str]


class ProblemReportDescription(BaseModel):
    """Description object of problem report."""

    code: str
    en: Optional[str]

    class Config:
        """Config for description."""

        extra = Extra.allow


class ProblemReport(BaseMessage):
    """Problem report message."""

    msg_type = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/notification/1.0/problem-report"
    description: ProblemReportDescription

    class Config:
        """Config for problem report."""

        extra = Extra.allow

    @classmethod
    def with_description(cls, **kwargs):
        """Create a problem report with a description."""
        return cls(description=ProblemReportDescription(**kwargs))


def problem_reporter(
    func: Callable = None,
    exceptions: Union[Type[Exception], Tuple[Type[Exception]]] = None,
):
    """Decorator for sending a problem report message when an exception occurs."""

    if not exceptions:
        exceptions = Exception
    if not func:
        return lambda f: problem_reporter(f, exceptions)

    @functools.wraps(func)
    async def _problem_reporter(*args):
        if len(args) == 3:
            _, msg, conn = args
        elif len(args) == 2:
            msg, conn = args
        else:
            raise ValueError(
                "Problem reporter must decorate a message handler with args "
                "[msg, conn] or [self, msg, conn]"
            )

        msg = cast(Message, msg)
        conn = cast(Connection, conn)

        try:
            return await func(*args)
        except exceptions as err:
            code = (
                err.code
                if isinstance(err, Reportable)
                else dasherize(underscore(type(err).__name__))
            )
            await conn.send_async(
                ProblemReport.with_description(en=str(err), code=code)
            )
            raise

    return _problem_reporter
