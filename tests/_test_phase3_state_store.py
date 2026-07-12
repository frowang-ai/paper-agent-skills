from __future__ import annotations

import json
from pathlib import Path

from paper_agent.storage import StateStore


def test_state_store_round_trips_items_and_collections(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "data" / "state.sqlite3")
    store.initialize()
    store.record_zotero_item(
        profile="default",
        library_id="0",
        item_key="ITEM1",
        frowang_paper_id="uuid-1",
        short_id="P-1",
        task_id="task-1",
        synced_at="2026-07-11T12:00:00Z",
    )
    store.record_zotero_collection(
        profile="default",
        library_id="0",
        collection_key="ZC1",
        frowang_collection_id="C-1",
        name="Methods",
        synced_at="2026-07-11T12:00:00Z",
    )

    assert store.get_zotero_item("default", "0", "ITEM1")["task_id"] == "task-1"
    assert store.get_zotero_collection("default", "0", "ZC1")["frowang_collection_id"] == "C-1"
    status = store.zotero_status("default", "0")
    assert status["item_count"] == 1
    assert status["collection_count"] == 1


def test_legacy_json_import_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "sync_state.json"
    legacy.write_text(
        json.dumps(
            {
                "ITEM1": {
                    "frowang_id": "P-1",
                    "task_id": "task-1",
                    "synced_at": "2026-07-11 12:00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(tmp_path / "state.sqlite3")
    store.initialize()

    first = store.import_legacy_zotero_json(legacy, profile="default", library_id="0")
    second = store.import_legacy_zotero_json(legacy, profile="default", library_id="0")

    assert first == {"imported": 1, "skipped": 0, "total": 1}
    assert second == {"imported": 0, "skipped": 1, "total": 1}

