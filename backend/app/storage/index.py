"""Campaign persistence + Library index.

Everything goes through the StorageBackend interface (never boto3 directly), so
local disk and B2 behave identically.

Layout:
  campaigns/{id}/campaign.json     full Campaign object (the frontend shape)
  campaigns/{id}/runs/...          genblaze's manifests + assets (sink-owned)
  index/campaigns.json             rollup so the Library is a single GET
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from app.domain.models import Campaign
from app.storage.factory import get_backend

logger = logging.getLogger(__name__)

INDEX_KEY = "index/campaigns.json"
_MAX_INDEXED = 50
_lock = threading.Lock()


def campaign_key(campaign_id: str) -> str:
    return f"campaigns/{campaign_id}/campaign.json"


def save_campaign(campaign: Campaign) -> None:
    """Write campaign.json and refresh the rollup index."""
    backend = get_backend()
    payload = json.dumps(campaign.ts(), ensure_ascii=False, indent=2).encode("utf-8")
    backend.put(campaign_key(campaign.id), payload, content_type="application/json")

    with _lock:
        entries = _read_index()
        entries = [e for e in entries if e.get("id") != campaign.id]
        entries.insert(0, campaign.ts())
        entries = entries[:_MAX_INDEXED]
        backend.put(
            INDEX_KEY,
            json.dumps(entries, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )


def _read_index() -> list[dict[str, Any]]:
    backend = get_backend()
    try:
        if not backend.exists(INDEX_KEY):
            return []
        data = json.loads(backend.get(INDEX_KEY).decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read campaign index: %s", exc)
        return []


def list_campaigns() -> tuple[list[dict[str, Any]], str]:
    """Return (campaigns, source). source is 'ok' or 'unavailable'."""
    try:
        entries = _read_index()
        if entries:
            return entries, "ok"
        rebuilt = rebuild_index()
        return rebuilt, "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Library listing failed: %s", exc)
        return [], "unavailable"


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    backend = get_backend()
    key = campaign_key(campaign_id)
    try:
        if not backend.exists(key):
            return None
        return json.loads(backend.get(key).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read campaign %s: %s", campaign_id, exc)
        return None


def delete_campaign(campaign_id: str) -> None:
    """Remove a campaign from the library.

    The campaign.json object must go too, not just the index entry: an empty or
    stale index triggers rebuild_index(), which rescans storage for
    campaign.json files — so deleting only the index entry would resurrect the
    campaign on the next Library load.

    Generated asset blobs and manifests under campaigns/{id}/runs/ are left in
    place deliberately: they are the immutable provenance record, they may be
    under object lock, and deleting them would be slow and irreversible.
    """
    backend = get_backend()
    with _lock:
        entries = [e for e in _read_index() if e.get("id") != campaign_id]
        backend.put(
            INDEX_KEY,
            json.dumps(entries, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        try:
            backend.delete(campaign_key(campaign_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete campaign.json for %s: %s", campaign_id, exc)


def rebuild_index() -> list[dict[str, Any]]:
    """Self-healing scan: find every campaign.json and rewrite the rollup."""
    backend = get_backend()
    found: list[dict[str, Any]] = []
    try:
        page = backend.list("campaigns/", max_keys=1000)
        for entry in page.entries:
            if not entry.key.endswith("/campaign.json"):
                continue
            try:
                found.append(json.loads(backend.get(entry.key).decode("utf-8")))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Index rebuild scan failed: %s", exc)
        return []

    found.sort(key=lambda c: str(c.get("createdAt", "")), reverse=True)
    found = found[:_MAX_INDEXED]
    try:
        backend.put(
            INDEX_KEY,
            json.dumps(found, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist rebuilt index: %s", exc)
    return found
