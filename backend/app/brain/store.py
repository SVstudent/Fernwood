"""Persistence for the per-brand brain.

Layout, alongside the existing campaigns/ tree:

    brains/{slug}/brain.json        the live brain — laws, personas, history
    brains/{slug}/v{n}.json         immutable snapshot of every version

Why keep the versioned copies. The improvement panel claims "the brain got
better", and that claim is only checkable if the earlier brain still exists to
compare against. Overwriting brain.json in place would leave the claim resting
on a file that no longer contains what it did at the time. Snapshots are small
JSON and Backblaze is cheap; an unfalsifiable metric is not.

Everything goes through the StorageBackend interface, never boto3, so B2 and
local disk behave identically — same as app/storage/index.py.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import UTC, datetime

from app.brain.models import BrainState
from app.storage.factory import get_backend

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_MAX_HISTORY = 40
# Laws fed into a prompt are ranked and capped: an unbounded law list would
# eventually crowd the actual brief out of the context window.
_MAX_LAWS = 24


def brand_slug(brand_name: str) -> str:
    """Stable storage key for a brand name.

    Case- and punctuation-insensitive so "Fernwood Coffee", "fernwood coffee"
    and "Fernwood  Coffee!" all address one brain rather than three empty ones.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (brand_name or "").lower()).strip("-")
    return slug or "unnamed-brand"


def brain_key(slug: str) -> str:
    return f"brains/{slug}/brain.json"


def version_key(slug: str, version: int) -> str:
    return f"brains/{slug}/v{version}.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_brain(brand_name: str) -> BrainState:
    """Read a brand's brain, or return a fresh empty one. Never raises."""
    slug = brand_slug(brand_name)
    backend = get_backend()
    try:
        if backend.exists(brain_key(slug)):
            raw = json.loads(backend.get(brain_key(slug)).decode("utf-8"))
            return BrainState.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - a corrupt brain must not block a run
        logger.warning("could not load brain for %s: %s", slug, exc)

    ts = now_iso()
    return BrainState(
        brand_slug=slug,
        brand_name=brand_name,
        version=0,
        created_at=ts,
        updated_at=ts,
    )


def save_brain(brain: BrainState) -> None:
    """Persist the brain and an immutable snapshot of this version.

    Best-effort: a storage failure is logged, never raised. The campaign it
    belongs to has already succeeded by this point, and losing a learning
    increment is not a reason to report that campaign as failed.
    """
    brain.updated_at = now_iso()
    brain.history = brain.history[-_MAX_HISTORY:]
    payload = json.dumps(brain.ts(), ensure_ascii=False, indent=2).encode("utf-8")

    with _lock:
        backend = get_backend()
        try:
            backend.put(
                brain_key(brain.brand_slug), payload, content_type="application/json"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not save brain %s: %s", brain.brand_slug, exc)
            return
        try:
            backend.put(
                version_key(brain.brand_slug, brain.version),
                payload,
                content_type="application/json",
            )
        except Exception as exc:  # noqa: BLE001 - the live brain is what matters
            logger.warning("could not snapshot brain v%d: %s", brain.version, exc)


def list_brains() -> list[dict]:
    """Every brain in storage, newest first. Never raises."""
    backend = get_backend()
    found: list[dict] = []
    try:
        page = backend.list("brains/", max_keys=1000)
        for entry in page.entries:
            if not entry.key.endswith("/brain.json"):
                continue
            try:
                found.append(json.loads(backend.get(entry.key).decode("utf-8")))
            except Exception:  # noqa: BLE001 - skip one unreadable brain
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("brain listing failed: %s", exc)
        return []
    found.sort(key=lambda b: str(b.get("updatedAt", "")), reverse=True)
    return found


def delete_brain(slug: str) -> None:
    """Wipe a brand's learned memory. Used by the demo's 'reset brain' control.

    Deletes only brain.json — the v{n}.json snapshots stay, because they are the
    evidence trail behind past improvement claims and a reset is meant to give a
    clean baseline, not to rewrite history.
    """
    try:
        get_backend().delete(brain_key(slug))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not delete brain %s: %s", slug, exc)


def top_laws(brain: BrainState, limit: int = _MAX_LAWS) -> list:
    """The laws worth spending prompt budget on.

    Ranked by reinforcement first, then confidence: a lesson two separate
    campaigns arrived at independently is stronger evidence than one the model
    felt strongly about once.
    """
    return sorted(
        brain.laws,
        key=lambda law: (law.reinforced_count, law.confidence),
        reverse=True,
    )[:limit]
