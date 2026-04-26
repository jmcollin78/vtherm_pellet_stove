# pylint: disable=protected-access

"""Tests du PelletRegulationHandler — Sprint 2, scénarios 7 et 10.

Scénario 7 : Modifications des options (hysteresis, garde-fous…) → le nouveau
             handler instancié lors du reload VTherm utilise les nouvelles valeurs.

Scénario 10 : Redémarrage HA avec ``is_heating=True`` stocké dans le Store →
              état restauré correctement et garde-fous respectés dès la première
              itération de régulation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vtherm_pellet_stove.const import (
    CONF_COOLDOWN_DURATION_MIN,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MIN_OFF_DURATION_MIN,
    CONF_MIN_ON_DURATION_MIN,
    CONF_POWER_CONTROL_ATTRIBUTE,
    CONF_POWER_CONTROL_ENABLED,
    CONF_POWER_LEVELS,
    CONF_SAFETY_ROOM_TEMP,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from custom_components.vtherm_pellet_stove.handler import (
    PelletRegulationHandler,
    _resolve_options,
)


# ---------------------------------------------------------------------------
# Infrastructure mock partagée
# ---------------------------------------------------------------------------


def _make_entry(data: dict, options: dict | None = None, unique_id: str = DOMAIN):
    """Construit un faux ConfigEntry."""
    entry = MagicMock()
    entry.data = dict(data)
    entry.options = dict(options) if options is not None else {}
    entry.unique_id = unique_id
    return entry


def _make_hass(entries: list | None = None):
    """Construit un faux HomeAssistant avec config_entries et services."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=entries or [])
    hass.services.async_call = AsyncMock()
    hass.async_create_task = MagicMock()
    return hass


def _make_thermostat(
    hass,
    *,
    unique_id: str = "vt_pellet_test",
    name: str = "Test VTherm",
    target_temperature: float | None = 20.0,
    current_temperature: float | None = 19.0,
    last_temperature_slope: float | None = None,
    vtherm_hvac_mode: str = "heat",
    underlying_list: list[str] | None = None,
):
    """Construit un faux InterfaceThermostatRuntime."""
    thermostat = MagicMock()
    thermostat.hass = hass
    thermostat.unique_id = unique_id
    thermostat.name = name
    thermostat.target_temperature = target_temperature
    thermostat.current_temperature = current_temperature
    thermostat.last_temperature_slope = last_temperature_slope
    thermostat.vtherm_hvac_mode = vtherm_hvac_mode
    thermostat.entry_infos = {"underlying_entity_ids": underlying_list or []}
    thermostat.prop_algorithm = None
    thermostat.update_custom_attributes = MagicMock()
    thermostat.async_write_ha_state = MagicMock()
    return thermostat


def _make_scheduler():
    """Construit un faux InterfaceCycleScheduler."""
    scheduler = MagicMock()
    scheduler.start_cycle = AsyncMock()
    scheduler.register_cycle_start_callback = MagicMock()
    scheduler.register_cycle_end_callback = MagicMock()
    return scheduler


def _now() -> datetime:
    return datetime(2026, 1, 15, 20, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _patch_ha_store():
    """Patch homeassistant.helpers.storage.Store in handler.py.

    The real Store requires a genuine HA event loop and a StorageManager backed
    by a real hass instance. Using a MagicMock hass makes Store.__init__ store
    an invalid _manager reference that triggers ValueErrors later during
    async_load. Patching the class at import time prevents any real I/O.
    """
    def _make_store(*_args, **_kwargs):
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()
        return store

    with patch(
        "custom_components.vtherm_pellet_stove.handler.Store",
        side_effect=_make_store,
    ):
        yield


def _mock_store(handler: PelletRegulationHandler, load_data: dict | None = None):
    """Reconfigure the store mock that _patch_ha_store already created."""
    handler._store.async_load = AsyncMock(return_value=load_data)
    handler._store.async_save = AsyncMock()
    return handler._store


# ===========================================================================
# Scénario 7 — Options modifiées → nouvelles valeurs prises en compte
# ===========================================================================


class TestScenario7OptionsUpdate:
    """Vérifie que le handler lit les options du bon entry plugin."""

    # --- _resolve_options ---------------------------------------------------

    def test_defaults_when_no_entries(self):
        """Sans entry plugin, DEFAULT_OPTIONS sont utilisées."""
        hass = _make_hass(entries=[])
        opts = _resolve_options(hass, "some_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(DEFAULT_OPTIONS[CONF_HYSTERESIS_ON])
        assert opts[CONF_MIN_ON_DURATION_MIN] == DEFAULT_OPTIONS[CONF_MIN_ON_DURATION_MIN]

    def test_global_entry_data_overrides_defaults(self):
        """L'entry globale (unique_id=DOMAIN) écrase les DEFAULT_OPTIONS."""
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.8, CONF_HYSTERESIS_OFF: 0.4},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        opts = _resolve_options(hass, "any_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(0.8)
        assert opts[CONF_HYSTERESIS_OFF] == pytest.approx(0.4)

    def test_global_entry_options_preferred_over_data(self):
        """Si l'entry a des options (via OptionsFlow), elles priment sur data."""
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.5},
            options={CONF_HYSTERESIS_ON: 1.5},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        opts = _resolve_options(hass, "uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.5)

    def test_per_thermostat_entry_overrides_global(self):
        """L'entry per-thermostat écrase l'entry globale pour le thermostat ciblé."""
        global_entry = _make_entry(data={CONF_HYSTERESIS_ON: 0.8}, unique_id=DOMAIN)
        per_entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 1.2, CONF_TARGET_VTHERM: "my_vt_uid"},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[global_entry, per_entry])
        opts = _resolve_options(hass, "my_vt_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.2)

    def test_per_thermostat_entry_does_not_affect_other_thermostats(self):
        """L'entry per-thermostat n'affecte pas les autres thermostats."""
        global_entry = _make_entry(data={CONF_HYSTERESIS_ON: 0.8}, unique_id=DOMAIN)
        per_entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 1.2, CONF_TARGET_VTHERM: "my_vt_uid"},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[global_entry, per_entry])
        opts = _resolve_options(hass, "other_vt_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(0.8)  # global only

    # --- init_algorithm + reload --------------------------------------------

    def test_handler_reads_options_on_init(self):
        """init_algorithm instancie le contrôleur avec les valeurs d'option."""
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.7, CONF_HYSTERESIS_OFF: 0.4},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(hass)

        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        assert handler._controller._hysteresis.hysteresis_on == pytest.approx(0.7)
        assert handler._controller._hysteresis.hysteresis_off == pytest.approx(0.4)

    def test_new_handler_after_reload_uses_updated_values(self):
        """Après un reload (simulation), le nouveau handler lit les nouvelles options."""
        # Handler v1 — options originales
        entry_v1 = _make_entry(data={CONF_HYSTERESIS_ON: 0.5}, unique_id=DOMAIN)
        hass1 = _make_hass(entries=[entry_v1])
        thermostat1 = _make_thermostat(hass1)
        handler1 = PelletRegulationHandler(thermostat1)
        handler1.init_algorithm()

        # Simulation d'un reload après modification des options
        entry_v2 = _make_entry(data={CONF_HYSTERESIS_ON: 1.0}, unique_id=DOMAIN)
        hass2 = _make_hass(entries=[entry_v2])
        thermostat2 = _make_thermostat(hass2)
        handler2 = PelletRegulationHandler(thermostat2)
        handler2.init_algorithm()

        # handler1 a les anciennes valeurs, handler2 les nouvelles
        assert handler1._controller._hysteresis.hysteresis_on == pytest.approx(0.5)
        assert handler2._controller._hysteresis.hysteresis_on == pytest.approx(1.0)

    def test_init_sets_prop_algorithm_on_thermostat(self):
        """init_algorithm expose le contrôleur via thermostat.prop_algorithm."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        assert thermostat.prop_algorithm is handler._controller

    def test_guard_rail_values_from_options(self):
        """Les durées minimales sont lues depuis les options."""
        entry = _make_entry(
            data={CONF_MIN_ON_DURATION_MIN: 45, CONF_MIN_OFF_DURATION_MIN: 25,
                  CONF_COOLDOWN_DURATION_MIN: 10},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        guard = handler._controller._guard
        assert guard.min_on_duration_min == 45
        assert guard.min_off_duration_min == 25
        assert guard.cooldown_duration_min == 10

    async def test_control_heating_calls_scheduler_with_on_percent(self):
        """control_heating transmet le on_percent calculé au scheduler."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # ≤ 20.0 − 0.5 → on_percent=1
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        scheduler.start_cycle.assert_awaited_once()
        call_args = scheduler.start_cycle.call_args[0]
        hvac_mode, on_percent, _force = call_args
        assert hvac_mode == "heat"
        assert on_percent == pytest.approx(1.0)

    async def test_control_heating_skipped_when_no_target(self):
        """control_heating ne fait rien quand target_temperature est None."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass, target_temperature=None)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        scheduler.start_cycle.assert_not_awaited()
        thermostat.async_write_ha_state.assert_not_called()

    async def test_power_level_applied_to_climate_entity(self):
        """_apply_power_level appelle climate.set_fan_mode sur l'underlying climate."""
        entry = _make_entry(
            data={
                CONF_POWER_CONTROL_ENABLED: True,
                CONF_POWER_CONTROL_ATTRIBUTE: "fan_mode",
                CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
            },
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=17.0,  # delta_T = 3.0 ≥ 2.0 → niveau max (index 4)
            underlying_list=["climate.poele_pellets"],
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # set_fan_mode doit avoir été appelé une fois
        hass.services.async_call.assert_awaited_once_with(
            "climate",
            "set_fan_mode",
            {"entity_id": "climate.poele_pellets", "fan_mode": "5"},
            blocking=False,
        )

    async def test_power_level_not_reapplied_when_unchanged(self):
        """set_fan_mode n'est pas rappelé si le niveau n'a pas changé."""
        entry = _make_entry(
            data={
                CONF_POWER_CONTROL_ENABLED: True,
                CONF_POWER_CONTROL_ATTRIBUTE: "fan_mode",
                CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
            },
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=17.0,  # delta_T = 3.0 → niveau max (index 4)
            underlying_list=["climate.poele_pellets"],
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        now = _now()
        await handler.control_heating(timestamp=now)
        first_call_count = hass.services.async_call.await_count

        # Deuxième itération sans changement de niveau
        await handler.control_heating(timestamp=now + timedelta(minutes=5))
        second_call_count = hass.services.async_call.await_count

        assert second_call_count == first_call_count  # pas d'appel supplémentaire


# ===========================================================================
# Scénario 10 — Redémarrage HA avec is_heating=True → état restauré
# ===========================================================================


class TestScenario10RestoreAfterRestart:
    """Le Store restaure l'état persisté et les garde-fous sont cohérents."""

    async def test_is_heating_restored_from_store(self):
        """async_added_to_hass restaure is_heating=True depuis le Store."""
        stored_data = {
            "is_heating": True,
            "current_level_index": 2,
            "last_on_at": "2026-01-15T19:32:11+00:00",
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        # Avant restauration : état initial
        assert handler._controller.is_heating is False

        # Remplace le Store réel par un mock chargé avec les données sauvegardées
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        # Après restauration
        assert handler._controller.is_heating is True
        assert handler._controller.state.current_level_index == 2
        assert handler._controller.state.last_reason == "below_on_threshold"
        assert handler._controller.state.last_on_at is not None

    async def test_guard_rail_respected_after_restore(self):
        """Après restauration, min_on_duration est respectée même si la temp est ok."""
        # Poêle allumé il y a 1 minute → min_on_duration (30min) non écoulée
        one_min_ago = _now() - timedelta(minutes=1)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": one_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            # Température dépassant le seuil d'extinction (≥ 20.0 + 0.3 = 20.3)
            # → sans garde-fous, on_percent serait 0 ; avec garde-fous, reste ON.
            current_temperature=20.5,
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Le scheduler doit recevoir on_percent=1 (locked_on)
        scheduler.start_cycle.assert_awaited_once()
        _, on_percent, _force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(1.0)
        assert handler._controller.last_reason == "locked_on"

    async def test_turn_off_allowed_after_min_on_duration_elapsed(self):
        """Après min_on_duration écoulée, l'extinction est autorisée."""
        # Poêle allumé il y a 35 minutes (> 30 min) → extinction autorisée
        long_ago = _now() - timedelta(minutes=35)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": long_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=20.5,  # ≥ 20.3 → demande OFF
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        _, on_percent, _force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(0.0)
        assert handler._controller.last_reason == "above_off_threshold"

    async def test_no_restore_when_store_is_empty(self):
        """Si le Store ne contient rien, l'état reste à l'initial (is_heating=False)."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=None)
        await handler.async_added_to_hass()

        assert handler._controller.is_heating is False

    async def test_state_persisted_after_control_heating(self):
        """control_heating sauvegarde l'état dans le Store."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # → allumage
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # async_save doit avoir été appelé avec un dict contenant is_heating=True
        save_mock = cast(AsyncMock, store.async_save)
        save_mock.assert_awaited_once() # pylint: disable=no-member
        saved = save_mock.await_args[0][0] # pylint: disable=no-member
        assert saved["is_heating"] is True

    async def test_on_scheduler_ready_registers_callbacks(self):
        """on_scheduler_ready enregistre bien les callbacks start/end."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        scheduler.register_cycle_start_callback.assert_called_once_with(
            handler._on_cycle_start
        )
        scheduler.register_cycle_end_callback.assert_called_once_with(
            handler._on_cycle_end
        )

    async def test_safety_overrides_restore_state(self):
        """La sécurité haute température force OFF même si is_heating=True restauré."""
        long_ago = _now() - timedelta(minutes=1)  # min_on_duration non écoulée
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": long_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        entry = _make_entry(data={CONF_SAFETY_ROOM_TEMP: 26.0}, unique_id=DOMAIN)
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=27.0,  # ≥ safety_room_temp → force OFF
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        _, on_percent, _force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(0.0)
        assert handler._controller.last_reason == "safety"
