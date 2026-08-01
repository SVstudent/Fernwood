"""Shared fixtures.

Offline tests must never touch the network or the developer's real storage, so
storage is redirected to a tmp_path and the settings/backend caches are cleared
around every test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.storage import factory  # noqa: E402


def _reset_caches() -> None:
    get_settings.cache_clear()
    factory.get_backend.cache_clear()


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Point every test at a throwaway local storage root."""
    monkeypatch.setenv("FERNWOOD_STORAGE", "local")
    monkeypatch.setenv("PUBLIC_API_BASE", "http://testserver")
    _reset_caches()

    settings = get_settings()
    monkeypatch.setattr(
        type(settings), "local_root", property(lambda self: tmp_path / "blobs")
    )
    factory.get_backend.cache_clear()
    yield tmp_path
    _reset_caches()


@pytest.fixture(autouse=True)
def reset_sse_appstatus():
    """sse-starlette keeps a module-global asyncio.Event for shutdown signalling.

    It binds to whichever event loop first touches it, so the second TestClient
    in a session raises "bound to a different event loop". Clearing it between
    tests lets each client rebind. Test-infra only — irrelevant under uvicorn,
    which has exactly one loop for the process lifetime.
    """
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = None
        yield
        AppStatus.should_exit_event = None
    except ImportError:  # pragma: no cover
        yield


@pytest.fixture
def brief():
    from app.domain.models import CampaignBrief, ColorPreference

    return CampaignBrief(
        brand_name="Fernwood Goods",
        product_service="Handcrafted ceramic dinnerware",
        target_audience="Design-conscious home cooks, 28-45",
        brief_text="Warm, tactile, slow-living.",
        tone_tags=["Earthy & Organic", "Cozy & Warm"],
        colors=ColorPreference(primary="#1E3A2B", secondary="#F4F1EA", accent="#D97706"),
    )


@pytest.fixture
def has_keys() -> bool:
    return get_settings().has_tokenrouter


def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits real external APIs")
