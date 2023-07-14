"""Encoding helpers."""

import base64
import json
from typing import Any, Dict


def pad(val: str) -> str:
    """Pad base64 values if need be: JWT calls to omit trailing padding."""
    padlen = 4 - len(val) % 4
    return val if padlen > 2 else (val + "=" * padlen)


def unpad(val: str) -> str:
    """Remove padding from base64 values if need be."""
    return val.rstrip("=")


def b64_to_bytes(val: str, urlsafe=False) -> bytes:
    """Convert a base 64 string to bytes."""
    if urlsafe:
        return base64.urlsafe_b64decode(pad(val))
    return base64.b64decode(pad(val))


def b64_to_str(val: str, urlsafe=False, encoding=None) -> str:
    """Convert a base 64 string to string on input encoding (default utf-8)."""
    return b64_to_bytes(val, urlsafe).decode(encoding or "utf-8")


def bytes_to_b64(val: bytes, urlsafe=False, pad=True, encoding: str = "ascii") -> str:
    """Convert a byte string to base 64."""
    b64 = (
        base64.urlsafe_b64encode(val).decode(encoding)
        if urlsafe
        else base64.b64encode(val).decode(encoding)
    )
    return b64 if pad else unpad(b64)


def str_to_b64(val: str, urlsafe=False, encoding=None, pad=True) -> str:
    """Convert a string to base64 string on input encoding (default utf-8)."""
    return bytes_to_b64(val.encode(encoding or "utf-8"), urlsafe, pad)


def dict_to_b64(val: Dict[str, Any], urlsafe=False, encoding=None, pad=True) -> str:
    """Convert a dict to base64 string on input encoding (default utf-8)."""
    return bytes_to_b64(
        json.dumps(val, separators=(",", ":")).encode(encoding or "utf-8"), urlsafe, pad
    )


def b64_to_dict(val: str, urlsafe=False) -> Dict[str, Any]:
    """Convert a base 64 string to dict."""
    return json.loads(b64_to_bytes(val, urlsafe))
