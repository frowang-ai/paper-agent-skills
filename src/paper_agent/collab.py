"""Collaborative-collection paper references (``collab~`` scoped IDs).

Papers inside a collaborative collection are separate copies whose notes,
annotations, tags, and metadata live in the workspace store rather than the
owner's private library. The server addresses them with scoped IDs of the form
``collab~<collection_root_key>~<paper_id>`` (returned by
``library collection items``). Those copies must be accessed through the
``/collections/{root_key}/papers/{paper_id}`` workspace routes; hitting the
plain ``/papers/{id}`` routes with a collaborative paper would either 404 or,
worse, silently target the wrong copy.
"""
from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import quote

from paper_agent.protocol import CommandError, ErrorCode, ExitCode

COLLAB_PREFIX = "collab~"


def split_collab_id(paper_id: str) -> Optional[Tuple[str, str]]:
    """Split ``collab~<root_key>~<paper_id>``; return None for plain IDs."""
    cleaned = paper_id.strip()
    if not cleaned.startswith(COLLAB_PREFIX):
        return None
    parts = cleaned.split("~")
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="Invalid collaborative paper ID; expected collab~<collection_key>~<paper_id>",
            exit_code=ExitCode.USAGE_ERROR,
            details={"paper_id": paper_id},
        )
    return parts[1], parts[2]


def is_collab_id(paper_id: str) -> bool:
    """True when the reference targets a collaborative workspace copy."""
    return split_collab_id(paper_id) is not None


def _seg(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="Resource identifier cannot be empty",
            exit_code=ExitCode.USAGE_ERROR,
        )
    return quote(cleaned, safe="")


def paper_base(paper_id: str) -> str:
    """URL prefix addressing exactly the copy the reference points to.

    Collaborative references route to the workspace endpoints so that notes,
    annotations, tags, and metadata land on the shared copy; anything else
    keeps the legacy private-library route.
    """
    parsed = split_collab_id(paper_id)
    if parsed is None:
        return f"/papers/{_seg(paper_id)}"
    root_key, underlying = parsed
    return f"/collections/{_seg(root_key)}/papers/{_seg(underlying)}"


def underlying_paper_id(paper_id: str) -> str:
    """Underlying source-paper ID of a collaborative reference.

    Used only for read-only endpoints that have no workspace equivalent
    (fulltext/summary/deep/assets/attribute-tree/screenshots); the server's
    collab-visibility check authorizes those reads.
    """
    parsed = split_collab_id(paper_id)
    return parsed[1] if parsed else paper_id.strip()
