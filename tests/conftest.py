"""Test configuration for standalone unit tests.

This conftest makes the repository importable without requiring a full
Home Assistant install. It also provides lightweight stubs for the HA modules
used by the integration so that the pellet/ business-logic package can be
tested in pure Python.

For integration tests that need the actual HA test framework, use
pytest-homeassistant-custom-component directly (it provides its own fixtures
and the stubs below are skipped when HA is already importable).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS_ROOT = PROJECT_ROOT / "custom_components"
INTEGRATION_ROOT = CUSTOM_COMPONENTS_ROOT / "vtherm_pellet_stove"
VERSATILE_THERMOSTAT_ROOT = CUSTOM_COMPONENTS_ROOT / "versatile_thermostat"


def _ensure_project_on_path() -> None:
    """Make the repository importable for pytest."""
    project_root_str = str(PROJECT_ROOT)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


def _ensure_package_stub(name: str, path: Path) -> None:
    """Register a lightweight package stub without importing its __init__."""
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]


def _ensure_homeassistant_stubs() -> None:
    """Provide the minimal Home Assistant surface used by unit tests."""
    if "homeassistant" in sys.modules:
        return  # Real HA is present (e.g. pytest-homeassistant-custom-component).

    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")

    class Store:
        """Minimal stub used by handler unit tests."""

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def async_load(self):
            """Return no persisted data."""
            return None

        async def async_save(self, _data) -> None:
            """Accept persisted data."""

    def slugify(value: object) -> str:
        """Return a simple deterministic slug for tests."""
        return str(value).lower().replace(" ", "_")

    storage.Store = Store
    util.slugify = slugify

    homeassistant.helpers = helpers
    helpers.storage = storage
    homeassistant.util = util

    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.storage": storage,
            "homeassistant.util": util,
        }
    )


def _ensure_vtherm_api_stubs() -> None:
    """Stub out vtherm_api if it is not installed."""
    if "vtherm_api" in sys.modules:
        return

    vtherm_api = types.ModuleType("vtherm_api")
    log_collector = types.ModuleType("vtherm_api.log_collector")

    def get_vtherm_logger(name: str):
        import logging
        return logging.getLogger(name)

    log_collector.get_vtherm_logger = get_vtherm_logger

    vtherm_api.log_collector = log_collector

    sys.modules.update(
        {
            "vtherm_api": vtherm_api,
            "vtherm_api.log_collector": log_collector,
        }
    )


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_ensure_project_on_path()
_ensure_homeassistant_stubs()
_ensure_vtherm_api_stubs()

# Register the custom_components package so that relative imports work.
_ensure_package_stub("custom_components", CUSTOM_COMPONENTS_ROOT)
_ensure_package_stub("custom_components.vtherm_pellet_stove", INTEGRATION_ROOT)
_ensure_package_stub("custom_components.versatile_thermostat", VERSATILE_THERMOSTAT_ROOT)
