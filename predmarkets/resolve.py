"""Resolve all tracked markets, dispatching each to its source's client."""
from __future__ import annotations

from . import client, predictit
from .client import Resolved
from .config import TRACKED


def resolve_all(specs=TRACKED) -> list[Resolved]:
    out: list[Resolved] = []
    for spec in specs:
        if getattr(spec, "source", "polymarket") == "predictit":
            out.append(predictit.resolve(spec))
        else:
            out.append(client.resolve(spec))
    return out
