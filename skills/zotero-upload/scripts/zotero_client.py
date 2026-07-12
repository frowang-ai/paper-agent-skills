"""Deprecated imports; use :mod:`paper_agent.clients.zotero`."""
from paper_agent.clients.zotero import (
    ZoteroClient,
    ZoteroCollection,
    ZoteroPaper,
    create_zotero_client,
    discover_zotero_storage,
    find_attachment_pdf,
)

find_zotero_storage_dir = discover_zotero_storage

__all__ = [
    "ZoteroClient",
    "ZoteroCollection",
    "ZoteroPaper",
    "create_zotero_client",
    "discover_zotero_storage",
    "find_attachment_pdf",
    "find_zotero_storage_dir",
]
