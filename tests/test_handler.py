# pylint: disable=protected-access

"""Tests du PelletRegulationHandler — Sprint 2, scénarios 7 et 10.

Scénario 7 : Modifications des options (hysteresis, garde-fous…) → le nouveau
             handler instancié lors du reload VTherm utilise les nouvelles valeurs.

Scénario 10 : Redémarrage HA avec ``is_heating=True`` stocké dans le Store →
              état restauré correctement et garde-fous respectés dès la première
              itération de régulation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.vtherm_pellet_stove.const import (
    CONF_COOLDOWN_DURATION_MIN,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MIN_OFF_DURATION_MIN,
    CONF_MIN_ON_DURATION_MIN,
    CONF_POWER_CONTROL_ATTRIBUTE,
    CONF_POWER_CONTROL_ENABLED,
    CONF_POWER_BOOST_ENABLED,
    CONF_POWER_LEVELS,
    CONF_SAFETY_ROOM_TEMP,
    CONF_TARGET_VTHERM,
    DATA_DEBUG_SENSORS_PREFIX,
    DATA_HANDLERS,
    DATA_SENSOR_ADD_CB,
    DATA_SENSOR_REGISTERED,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_SETTINGS_UPDATED,
)
from custom_components.vtherm_pellet_stove.handler import (
    PelletRegulationHandler,
    _PropAlgoProxy,
    _resolve_options,
)
from custom_components.vtherm_pellet_stove.sensor import PelletDebugSensor

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
    hass.data = {}
    hass.config_entries.async_entries = MagicMock(return_value=entries or [])
    hass.services.async_call = AsyncMock()
    physical_states = {}
    hass.states.get = MagicMock(side_effect=physical_states.get)

    def _set_state(entity_id, state, attributes=None):
        physical_states[entity_id] = SimpleNamespace(
            state=state,
            attributes=attributes or {},
        )

    hass.states.async_set = MagicMock(side_effect=_set_state)

    def _create_task(coro, **_kwargs):
        """Ferme proprement toute coroutine reçue pour éviter le RuntimeWarning."""
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=_create_task)
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
    underlying_state: str = "off",
):
    """Construit un faux InterfaceThermostatRuntime."""
    thermostat = MagicMock()
    thermostat.hass = hass
    thermostat.unique_id = unique_id
    thermostat.name = name
    thermostat.entity_id = "climate.test_vtherm"
    thermostat.target_temperature = target_temperature
    thermostat.current_temperature = current_temperature
    thermostat.last_temperature_slope = last_temperature_slope
    thermostat.vtherm_hvac_mode = vtherm_hvac_mode
    underlying_list = underlying_list or ["climate.pellet_stove"]
    thermostat.entry_infos = {"underlying_entity_ids": underlying_list}
    for entity_id in underlying_list:
        attributes = {"burner_status": "Off"} if entity_id.startswith("climate.") else {}
        hass.states.async_set(entity_id, underlying_state, attributes)
    thermostat.prop_algorithm = None
    thermostat.cycle_min = 5
    thermostat.update_custom_attributes = MagicMock()
    thermostat.async_write_ha_state = MagicMock()
    return thermostat


def _make_scheduler():
    """Construit un faux InterfaceCycleScheduler."""
    scheduler = MagicMock()
    scheduler.start_cycle = AsyncMock()
    scheduler.cancel_cycle = AsyncMock()
    scheduler.is_cycle_running = False
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


async def test_reset_stops_before_clearing_and_saves():
    """OFF callbacks cannot restart regulation or send duplicate commands."""
    hass = _make_hass()
    thermostat = _make_thermostat(hass)
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    save = AsyncMock()
    handler._store.async_save = save
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)
    await handler.control_heating(timestamp=_now())
    handler._debug_sensor = MagicMock()
    handler._last_applied_level_index = 2
    original_state = handler._controller.save_state()
    scheduler.start_cycle.reset_mock()
    hass.services.async_call.reset_mock()

    async def stop(*_args, **_kwargs):
        assert handler._controller.save_state() == original_state
        thermostat.vtherm_hvac_mode = "off"
        await handler.control_heating()

    hass.services.async_call.side_effect = stop
    await handler.async_reset()

    hass.services.async_call.assert_awaited_once_with(
        "climate",
        "set_hvac_mode",
        {"entity_id": thermostat.entity_id, "hvac_mode": "off"},
        blocking=True,
        context=None,
    )
    assert thermostat.vtherm_hvac_mode == "off"
    assert handler._controller.last_reason == "reset"
    assert handler._controller.current_phase() == "off"
    assert handler._controller.get_debug_attributes()["next_action_allowed_at"] is None
    assert handler._last_applied_level_index is None
    assert handler._last_energy_at is None
    save.assert_awaited_with(handler._controller.save_state())
    handler._debug_sensor.update_from_controller.assert_called_once()
    scheduler.start_cycle.assert_not_awaited()
    await handler.async_reset()
    assert hass.services.async_call.await_count == 1


async def test_reset_failure_does_not_clear_history():
    """An unsuccessful stop must not lift software guard rails."""
    hass = _make_hass()
    handler = PelletRegulationHandler(_make_thermostat(hass))
    handler.init_algorithm()
    await handler.control_heating(timestamp=_now())
    state = handler._controller.save_state()
    hass.services.async_call.side_effect = RuntimeError("stop failed")

    with pytest.raises(RuntimeError, match="stop failed"):
        await handler.async_reset()

    assert handler._controller.save_state() == state
    assert not handler._resetting


async def test_handler_registry_survives_old_handler_removal():
    """Removal of a replaced handler must not remove its successor."""
    hass = _make_hass()
    thermostat = _make_thermostat(hass, vtherm_hvac_mode="off")
    old = PelletRegulationHandler(thermostat)
    new = PelletRegulationHandler(thermostat)
    for handler in (old, new):
        handler.init_algorithm()
        await handler.async_startup()
    old.remove()
    assert hass.data[DOMAIN][DATA_HANDLERS][thermostat.unique_id] is new
    new.remove()
    assert hass.data[DOMAIN][DATA_HANDLERS] == {}


async def test_reset_does_not_clear_history_if_off_is_refused():
    """A locked thermostat may accept the service call without changing mode."""
    hass = _make_hass()
    handler = PelletRegulationHandler(_make_thermostat(hass))
    handler.init_algorithm()
    await handler.control_heating(timestamp=_now())
    state = handler._controller.save_state()
    with pytest.raises(HomeAssistantError) as error:
        await handler.async_reset()
    assert error.value.translation_key == "reset_not_off"
    assert handler._controller.save_state() == state
    assert not handler._resetting


async def test_reset_reports_save_failure_without_restarting():
    hass = _make_hass()
    thermostat = _make_thermostat(hass, vtherm_hvac_mode="off")
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    handler._store.async_save.side_effect = OSError("disk unavailable")
    with pytest.raises(HomeAssistantError) as error:
        await handler.async_reset()
    assert error.value.translation_key == "reset_save_failed"
    assert handler._controller.last_reason == "reset"
    assert thermostat.vtherm_hvac_mode == "off"
    assert not handler._resetting
    hass.services.async_call.assert_not_awaited()


async def test_reset_waits_for_inflight_control_save():
    """A previous cycle cannot overwrite the reset with its old snapshot."""
    hass = _make_hass()
    thermostat = _make_thermostat(hass)
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    saving = asyncio.Event()
    release = asyncio.Event()
    operations = []

    async def save(data):
        if data["last_reason"] != "reset":
            saving.set()
            await release.wait()
            operations.append("save_control")
        else:
            operations.append("save_reset")

    async def stop(_domain, service, *_args, **_kwargs):
        if service != "set_hvac_mode":
            return
        operations.append("stop")
        thermostat.vtherm_hvac_mode = "off"

    handler._store.async_save.side_effect = save
    hass.services.async_call.side_effect = stop
    control = asyncio.create_task(handler.control_heating(timestamp=_now()))
    await saving.wait()
    reset = asyncio.create_task(handler.async_reset())
    release.set()
    await asyncio.gather(control, reset)
    assert operations == ["save_control", "stop", "save_reset"]
    assert handler._controller.last_reason == "reset"


async def test_control_skipped_during_stop_and_reset_calls_serialized():
    hass = _make_hass()
    thermostat = _make_thermostat(hass)
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    scheduler = _make_scheduler()
    scheduler.is_cycle_running = True
    handler.on_scheduler_ready(scheduler)
    stopping = asyncio.Event()
    release = asyncio.Event()

    async def stop(*_args, **_kwargs):
        stopping.set()
        await release.wait()
        thermostat.vtherm_hvac_mode = "off"

    hass.services.async_call.side_effect = stop
    reset = asyncio.create_task(handler.async_reset())
    await stopping.wait()
    await handler.control_heating(timestamp=_now())
    scheduler.start_cycle.assert_not_awaited()
    second_reset = asyncio.create_task(handler.async_reset())
    release.set()
    await asyncio.gather(reset, second_reset)
    hass.services.async_call.assert_awaited_once()
    assert handler._controller.last_reason == "reset"
    assert not handler._resetting


async def test_unknown_physical_state_blocks_automatic_ignition():
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        target_temperature=20.0,
        current_temperature=18.0,
        vtherm_hvac_mode="heat",
    )
    hass.states.async_set(
        "climate.pellet_stove", "unknown", {"burner_status": "Unknown state"}
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.control_heating(timestamp=_now())

    scheduler.start_cycle.assert_not_awaited()
    assert handler._controller.is_heating is False
    assert handler._controller.last_reason == "physical_state_not_confirmed_off"


@pytest.mark.parametrize(
    ("contact_state", "turn_on_allowed"),
    [
        ("off", True),
        ("on", False),
        ("unknown", False),
        ("unavailable", False),
        ("missing", False),
    ],
)
@pytest.mark.parametrize("entity_domain", ["switch", "input_boolean"])
async def test_switch_automatic_ignition_requires_explicit_off_contact(
    entity_domain, contact_state, turn_on_allowed
):
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        target_temperature=20.0,
        current_temperature=18.0,
        vtherm_hvac_mode="heat",
        underlying_list=[f"{entity_domain}.pellet_stove"],
        underlying_state=contact_state if contact_state != "missing" else "off",
    )
    if contact_state == "missing":
        hass.states.get.side_effect = lambda _entity_id: None
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.control_heating(timestamp=_now())

    assert handler._controller.is_heating is turn_on_allowed
    if turn_on_allowed:
        scheduler.start_cycle.assert_awaited_once()
        _, on_percent, force = scheduler.start_cycle.call_args.args
        assert on_percent == pytest.approx(1.0)
        assert force is True
    else:
        scheduler.start_cycle.assert_not_awaited()
        assert handler._controller.last_reason == "physical_state_not_confirmed_off"


async def test_known_flame_does_not_send_duplicate_ignition():
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        target_temperature=20.0,
        current_temperature=18.0,
        vtherm_hvac_mode="heat",
    )
    hass.states.async_set(
        "climate.pellet_stove", "heat", {"burner_status": "Flame On"}
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.control_heating(timestamp=_now())

    scheduler.start_cycle.assert_not_awaited()
    assert handler._controller.is_heating is False


async def test_conflicting_physical_status_blocks_automatic_ignition():
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        target_temperature=20.0,
        current_temperature=18.0,
        vtherm_hvac_mode="heat",
    )
    hass.states.async_set(
        "climate.pellet_stove",
        "heat",
        {"burner_status": "Off", "hvac_action": "heating"},
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.control_heating(timestamp=_now())

    scheduler.start_cycle.assert_not_awaited()
    assert handler._controller.is_heating is False


async def test_safety_stop_without_target_requests_off():
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        target_temperature=None,
        current_temperature=27.0,
        vtherm_hvac_mode="heat",
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    handler._controller.state.is_heating = True
    _mock_store(handler)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.control_heating(timestamp=_now())

    scheduler.start_cycle.assert_awaited_once_with("heat", 0.0, True)
    scheduler.cancel_cycle.assert_awaited_once()
    assert handler._controller.is_heating is False
    assert handler._controller.last_reason == "safety"


@pytest.mark.parametrize("target_temperature", [None, 20.0])
async def test_switch_adopted_on_safety_shutdown_ignores_min_on(target_temperature):
    entry = _make_entry(data={CONF_SAFETY_ROOM_TEMP: 26.0}, unique_id=DOMAIN)
    hass = _make_hass(entries=[entry])
    thermostat = _make_thermostat(
        hass,
        target_temperature=target_temperature,
        current_temperature=27.0,
        underlying_list=["switch.pellet_stove"],
        underlying_state="on",
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler, load_data=None)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.async_added_to_hass()
    await handler.async_startup()
    assert handler._controller.state.last_on_at is None
    assert handler._controller.state.last_off_at is None
    scheduler.start_cycle.assert_not_awaited()

    stopped_at = _now()
    await handler.control_heating(timestamp=stopped_at)

    assert handler._controller.is_heating is False
    assert handler._controller.state.last_off_at == stopped_at
    assert handler._controller.last_reason == "safety"
    scheduler.start_cycle.assert_awaited_once_with("heat", 0.0, True)
    scheduler.cancel_cycle.assert_awaited_once()


async def test_switch_adopted_on_manual_parent_off_does_not_duplicate_stop():
    hass = _make_hass()
    thermostat = _make_thermostat(
        hass,
        vtherm_hvac_mode="heat",
        underlying_list=["switch.pellet_stove"],
        underlying_state="on",
    )
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    _mock_store(handler, load_data=None)
    scheduler = _make_scheduler()
    handler.on_scheduler_ready(scheduler)

    await handler.async_added_to_hass()
    await handler.async_startup()
    assert handler._controller.state.last_on_at is None
    assert handler._controller.state.last_off_at is None
    scheduler.start_cycle.assert_not_awaited()

    stopped_at = _now()
    thermostat.vtherm_hvac_mode = "off"
    await handler.control_heating(timestamp=stopped_at)

    assert handler._controller.is_heating is False
    assert handler._controller.state.last_off_at == stopped_at
    assert handler._controller.last_reason == "hvac_off"
    scheduler.start_cycle.assert_not_awaited()


async def test_unload_during_stop_prevents_reset_of_removed_handler():
    hass = _make_hass()
    thermostat = _make_thermostat(hass)
    handler = PelletRegulationHandler(thermostat)
    handler.init_algorithm()
    handler._controller.state.last_off_at = _now()

    async def stop(*_args, **_kwargs):
        thermostat.vtherm_hvac_mode = "off"
        handler.remove()

    hass.services.async_call.side_effect = stop
    with pytest.raises(ServiceValidationError):
        await handler.async_reset()
    assert handler._controller.state.last_off_at == _now()
    assert not handler._resetting


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

    def test_partial_per_thermostat_entry_uses_defaults_not_global(self):
        """Une entrée locale partielle ne complète jamais ses clés depuis le global."""
        global_entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.8, CONF_MIN_ON_DURATION_MIN: 12},
            unique_id=DOMAIN,
        )
        per_entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={CONF_HYSTERESIS_ON: 1.2},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[global_entry, per_entry])

        opts = _resolve_options(hass, "my_vt_uid")

        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.2)
        assert opts[CONF_MIN_ON_DURATION_MIN] == DEFAULT_OPTIONS[CONF_MIN_ON_DURATION_MIN]

    async def test_live_options_update_preserves_controller_state_and_scheduler(self):
        """Updating settings retains state, timestamps, and the live scheduler."""
        now = _now()
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={CONF_MIN_ON_DURATION_MIN: 42},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(hass, unique_id="my_vt_uid")
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        handler._controller.state.is_heating = True
        handler._controller.state.last_on_at = now - timedelta(minutes=7)
        handler._controller.state.last_off_at = now - timedelta(hours=2)
        handler._debug_sensor = PelletDebugSensor(thermostat)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        state = handler._controller.state

        assert await handler.async_update_options()

        assert handler._controller.state is state
        assert state.last_on_at == now - timedelta(minutes=7)
        assert state.last_off_at == now - timedelta(hours=2)
        assert handler._controller._guard.min_on_duration_min == 42
        assert handler._scheduler is scheduler
        assert handler._debug_sensor.extra_state_attributes[
            "next_action_allowed_at"
        ] == (now - timedelta(minutes=7) + timedelta(minutes=42)).isoformat()
        scheduler.start_cycle.assert_not_awaited()

    async def test_live_options_update_fires_settings_event_only_for_changes(
        self, caplog
    ):
        """Publish changed effective options once with the VTherm identity."""
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        hass.states.async_set("climate.test_vtherm", "heat", {"temperature": 21.0})
        handler = PelletRegulationHandler(_make_thermostat(hass, unique_id="my_vt_uid"))
        handler.init_algorithm()
        hass.bus.async_fire.assert_not_called()
        entry.options = {CONF_MIN_ON_DURATION_MIN: 42}

        with caplog.at_level(logging.INFO):
            assert await handler.async_update_options()
        hass.bus.async_fire.assert_called_once()
        info_records = [
            record for record in caplog.records if record.levelno == logging.INFO
        ]
        assert len(info_records) == 1
        assert "Test VTherm" in info_records[0].message
        assert EVENT_SETTINGS_UPDATED in info_records[0].message
        assert "'min_on_duration_min': 42" in info_records[0].message
        event_type, event_data = hass.bus.async_fire.call_args.args
        assert event_type == EVENT_SETTINGS_UPDATED
        assert event_data == {
            "entity_id": "climate.test_vtherm",
            "name": "Test VTherm",
            "state": "heat",
            "state_attributes": {"temperature": 21.0},
            "configuration": {
                **DEFAULT_OPTIONS,
                CONF_MIN_ON_DURATION_MIN: 42,
            },
        }

        with caplog.at_level(logging.INFO):
            assert await handler.async_update_options()
        hass.bus.async_fire.assert_called_once()
        assert (
            len([record for record in caplog.records if record.levelno == logging.INFO])
            == 1
        )

    async def test_live_options_update_does_not_fire_event_on_failure(self):
        """Do not publish an update when applying the controller config fails."""
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(_make_thermostat(hass, unique_id="my_vt_uid"))
        handler.init_algorithm()
        entry.options = {CONF_MIN_ON_DURATION_MIN: 42}

        with patch.object(
            handler._controller,
            "update_configuration",
            side_effect=RuntimeError("configuration failed"),
        ):
            with pytest.raises(RuntimeError, match="configuration failed"):
                await handler.async_update_options()

        hass.bus.async_fire.assert_not_called()
        assert (
            handler._opts[CONF_MIN_ON_DURATION_MIN]
            == DEFAULT_OPTIONS[CONF_MIN_ON_DURATION_MIN]
        )
        assert (
            handler._controller._guard.min_on_duration_min
            == DEFAULT_OPTIONS[CONF_MIN_ON_DURATION_MIN]
        )
        assert await handler.async_update_options()
        hass.bus.async_fire.assert_called_once()

    async def test_live_options_update_keeps_applied_options_when_bus_fails(self):
        """A bus error is logged without reverting an applied configuration."""
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(_make_thermostat(hass, unique_id="my_vt_uid"))
        handler.init_algorithm()
        entry.options = {CONF_MIN_ON_DURATION_MIN: 42}

        with (
            patch.object(
                hass.bus,
                "async_fire",
                side_effect=RuntimeError("bus unavailable"),
            ) as fire_event,
            patch(
                "custom_components.vtherm_pellet_stove.handler._LOGGER.exception"
            ) as log_exception,
        ):
            assert await handler.async_update_options()
            fire_event.assert_called_once()
            log_exception.assert_called_once()

            assert handler._opts[CONF_MIN_ON_DURATION_MIN] == 42
            assert handler._controller._guard.min_on_duration_min == 42
            assert await handler.async_update_options()
            fire_event.assert_called_once()

    async def test_live_options_update_notifies_even_when_control_fails(self, caplog):
        """A control error propagates after options are applied and notified."""
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={},
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(_make_thermostat(hass, unique_id="my_vt_uid"))
        handler.init_algorithm()
        handler.on_scheduler_ready(_make_scheduler())
        entry.options = {CONF_MIN_ON_DURATION_MIN: 42}

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                handler,
                "_async_control_heating",
                side_effect=RuntimeError("control failed"),
            ),
        ):
            with pytest.raises(RuntimeError, match="control failed"):
                await handler.async_update_options()

            assert handler._opts[CONF_MIN_ON_DURATION_MIN] == 42
            assert handler._controller._guard.min_on_duration_min == 42
            hass.bus.async_fire.assert_called_once()
            assert not [
                record for record in caplog.records if record.levelno == logging.INFO
            ]

            with pytest.raises(RuntimeError, match="control failed"):
                await handler.async_update_options()
            hass.bus.async_fire.assert_called_once()

    async def test_duration_only_options_update_does_not_reapply_power_level(self):
        """Changing a guard duration must not resend an unchanged power level."""
        entry = _make_entry(
            data={
                CONF_MIN_ON_DURATION_MIN: 30,
                CONF_POWER_CONTROL_ENABLED: True,
                CONF_POWER_CONTROL_ATTRIBUTE: "fan_mode",
                CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
            },
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(_make_thermostat(hass))
        handler.init_algorithm()
        handler._controller.state.is_heating = True
        handler._controller.state.current_level_index = 2

        await handler._apply_power_level()
        hass.services.async_call.reset_mock()
        entry.options = {CONF_MIN_ON_DURATION_MIN: 42}

        assert await handler.async_update_options()
        await handler._apply_power_level()

        hass.services.async_call.assert_not_awaited()

    async def test_changed_effective_power_value_is_reapplied(self):
        """A new mapped value at the current index is sent to the stove."""
        entry = _make_entry(
            data={
                CONF_POWER_CONTROL_ENABLED: True,
                CONF_POWER_CONTROL_ATTRIBUTE: "fan_mode",
                CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
            },
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(_make_thermostat(hass))
        handler.init_algorithm()
        handler._controller.state.is_heating = True
        handler._controller.state.current_level_index = 2

        await handler._apply_power_level()
        hass.services.async_call.reset_mock()
        entry.options = {CONF_POWER_LEVELS: ["1", "2", "high", "4", "5"]}

        assert await handler.async_update_options()
        await handler._apply_power_level()

        hass.services.async_call.assert_awaited_once_with(
            "climate",
            "set_fan_mode",
            {"entity_id": "climate.pellet_stove", "fan_mode": "high"},
            blocking=False,
        )

    async def test_switch_disables_power_features_without_losing_climate_options(self):
        """Power settings and runtime state survive temporary switch mode."""
        options = {
            CONF_POWER_CONTROL_ENABLED: True,
            CONF_POWER_BOOST_ENABLED: True,
            CONF_POWER_LEVELS: ["low", "medium", "high"],
        }
        entry = _make_entry(data={}, options=options, unique_id=DOMAIN)
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state="on",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        controller = handler._controller
        controller.state.is_heating = True
        controller.state.current_level_index = 1
        controller.state.last_on_at = _now() - timedelta(minutes=10)
        controller.state.boost_until = _now() + timedelta(minutes=5)
        saved_last_on_at = controller.state.last_on_at
        saved_boost_until = controller.state.boost_until

        assert handler._opts[CONF_POWER_CONTROL_ENABLED] is True
        assert handler._opts[CONF_POWER_BOOST_ENABLED] is True
        assert controller._power_control_enabled is False
        assert controller._power_mapper is None
        assert controller._boost_manager is None

        entry.options = {
            **options,
            CONF_POWER_CONTROL_ENABLED: False,
            CONF_POWER_BOOST_ENABLED: False,
        }
        assert await handler.async_update_options()
        assert controller._power_control_enabled is False
        assert controller._power_mapper is None
        assert controller._boost_manager is None
        assert controller.state.current_level_index == 1
        assert controller.state.last_on_at == saved_last_on_at
        assert controller.state.boost_until == saved_boost_until
        hass.services.async_call.assert_not_awaited()

        entry.options = {**options, CONF_POWER_LEVELS: ["low", "middle", "high"]}
        assert await handler.async_update_options()
        assert controller._power_control_enabled is False
        assert controller._power_mapper is None
        assert controller._boost_manager is None
        assert controller.state.current_level_index == 1
        assert controller.state.last_on_at == saved_last_on_at
        assert controller.state.boost_until == saved_boost_until

        thermostat.entry_infos["underlying_entity_ids"] = ["climate.pellet_stove"]
        assert await handler.async_update_options()
        assert controller._power_control_enabled is True
        assert controller.current_level_value == "middle"
        assert controller._boost_manager is not None
        assert controller.state.current_level_index == 1
        assert controller.state.last_on_at == saved_last_on_at
        assert controller.state.boost_until == saved_boost_until

    async def test_switch_power_inhibition_is_local_with_shared_global_options(self):
        """A switch VTherm cannot disable power control on a climate VTherm."""
        global_options = {
            CONF_POWER_CONTROL_ENABLED: True,
            CONF_POWER_BOOST_ENABLED: True,
            CONF_POWER_CONTROL_ATTRIBUTE: "fan_mode",
            CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
        }
        entry = _make_entry(data=global_options, options={}, unique_id=DOMAIN)
        hass = _make_hass(entries=[entry])
        switch_handler = PelletRegulationHandler(
            _make_thermostat(
                hass,
                unique_id="switch_vtherm",
                underlying_list=["switch.pellet_stove"],
                underlying_state="on",
            )
        )
        climate_handler = PelletRegulationHandler(
            _make_thermostat(hass, unique_id="climate_vtherm")
        )
        switch_handler.init_algorithm()
        climate_handler.init_algorithm()

        assert switch_handler._controller._power_control_enabled is False
        assert switch_handler._controller._boost_manager is None
        assert climate_handler._controller._power_control_enabled is True
        assert climate_handler._controller._boost_manager is not None
        switch_handler._controller.state.is_heating = True
        switch_handler._controller.state.current_level_index = 2
        climate_handler._controller.state.is_heating = True
        climate_handler._controller.state.current_level_index = 2

        await switch_handler._apply_power_level()
        hass.services.async_call.assert_not_awaited()
        await climate_handler._apply_power_level()
        await climate_handler._apply_power_level()

        hass.services.async_call.assert_awaited_once_with(
            "climate",
            "set_fan_mode",
            {"entity_id": "climate.pellet_stove", "fan_mode": "3"},
            blocking=False,
        )
        assert entry.data == global_options
        assert entry.options == {}

    async def test_sensor_is_recreated_after_platform_unload(self):
        """A platform reload registers a fresh sensor for the live handler."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass, unique_id="my_vt_uid")
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        hass.data.setdefault(DOMAIN, {})[DATA_SENSOR_ADD_CB] = MagicMock()
        await handler.async_added_to_hass()
        first_sensor = handler._debug_sensor
        callback = hass.data[DOMAIN][DATA_SENSOR_ADD_CB]
        assert callback.call_count == 1

        handler.detach_debug_sensor()
        handler.attach_debug_sensor()

        assert handler._debug_sensor is not first_sensor
        assert callback.call_count == 2

    async def test_live_options_update_recalculates_off_deadline(self):
        """New off guards use the historic timestamp, not the edit time."""
        now = _now()
        last_off_at = now - timedelta(minutes=12)
        entry = _make_entry(
            data={CONF_TARGET_VTHERM: "my_vt_uid"},
            options={
                CONF_MIN_OFF_DURATION_MIN: 33,
                CONF_COOLDOWN_DURATION_MIN: 8,
            },
            unique_id=f"{DOMAIN}-my_vt_uid",
        )
        hass = _make_hass(entries=[entry])
        handler = PelletRegulationHandler(
            _make_thermostat(hass, unique_id="my_vt_uid")
        )
        handler.init_algorithm()
        handler._controller.state.last_off_at = last_off_at
        handler._debug_sensor = PelletDebugSensor(handler._thermostat)

        assert await handler.async_update_options()

        assert handler._controller.state.last_off_at == last_off_at
        assert handler._debug_sensor.extra_state_attributes[
            "next_action_allowed_at"
        ] == (last_off_at + timedelta(minutes=41)).isoformat()

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
        """init_algorithm expose un proxy via thermostat.prop_algorithm.

        Depuis Fix 4, prop_algorithm est un _PropAlgoProxy (pas le contrôleur
        directement) pour bloquer le double-appel de recalculate().
        """
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        assert isinstance(thermostat.prop_algorithm, _PropAlgoProxy)
        # Le proxy expose bien le on_percent du contrôleur
        assert thermostat.prop_algorithm.on_percent == handler._controller.on_percent

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
        scheduler.cancel_cycle.assert_awaited_once()
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
# Scénario 12 — Capteur de debug réutilisé après rechargement du handler
# ===========================================================================


def _make_hass_with_data(entries: list | None = None):
    """Construit un faux hass avec un vrai dict hass.data (nécessaire pour les tests de sensor)."""
    hass = _make_hass(entries)
    hass.data = {}
    # Remettre setdefault pour que ça fonctionne sur le vrai dict
    return hass


class TestScenario12DebugSensorReuse:
    """Vérifie que le capteur de debug est réutilisé entre les recharges de handler.

    Après une modification d'options, VTherm est rechargé, créant un nouveau
    PelletRegulationHandler. async_added_to_hass() ne doit PAS tenter
    d'enregistrer un nouveau PelletDebugSensor (collision unique_id), mais
    récupérer celui déjà stocké dans hass.data et lui pousser les nouvelles
    valeurs via update_from_controller().
    """

    async def test_first_handler_creates_sensor_and_stores_it(self):
        """Premier handler : crée le capteur et le stocke dans hass.data."""
        hass = _make_hass_with_data()
        thermostat = _make_thermostat(hass, unique_id="vt_uid")
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        cb = MagicMock()
        hass.data.setdefault(DOMAIN, {})[DATA_SENSOR_ADD_CB] = cb

        await handler.async_added_to_hass()

        # Le capteur doit être créé et stocké.
        sensor_key = DATA_DEBUG_SENSORS_PREFIX + "vt_uid"
        assert sensor_key in hass.data[DOMAIN]
        assert hass.data[DOMAIN][sensor_key] is handler._debug_sensor
        # async_add_entities doit avoir été appelé une fois.
        cb.assert_called_once()

    async def test_second_handler_reuses_existing_sensor(self):
        """Second handler (après reload) : réutilise le capteur existant sans ré-enregistrement."""
        hass = _make_hass_with_data()
        sensor_key = DATA_DEBUG_SENSORS_PREFIX + "vt_uid"

        # Simule un capteur déjà enregistré par le premier handler.
        fake_existing_sensor = MagicMock()
        hass.data.setdefault(DOMAIN, {})[sensor_key] = fake_existing_sensor
        hass.data[DOMAIN][DATA_SENSOR_REGISTERED] = {"vt_uid"}

        cb = MagicMock()
        hass.data[DOMAIN][DATA_SENSOR_ADD_CB] = cb

        thermostat = _make_thermostat(hass, unique_id="vt_uid")
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        await handler.async_added_to_hass()

        # Le handler doit pointer vers le capteur existant.
        assert handler._debug_sensor is fake_existing_sensor
        # async_add_entities NE doit PAS être rappelé (pas de ré-enregistrement).
        cb.assert_not_called()

    async def test_cached_unregistered_sensor_is_added_once(self):
        """A cached sensor without platform registration is still added."""
        hass = _make_hass_with_data()
        sensor_key = DATA_DEBUG_SENSORS_PREFIX + "vt_uid"
        cached_sensor = MagicMock()
        domain_data = hass.data.setdefault(DOMAIN, {})
        domain_data[sensor_key] = cached_sensor
        callback = MagicMock()
        domain_data[DATA_SENSOR_ADD_CB] = callback

        handler = PelletRegulationHandler(_make_thermostat(hass, unique_id="vt_uid"))
        handler.init_algorithm()
        await handler.async_added_to_hass()

        callback.assert_called_once_with([cached_sensor], update_before_add=True)
        assert domain_data[DATA_SENSOR_REGISTERED] == {"vt_uid"}

    async def test_debug_sensor_updated_with_new_options_after_reload(self):
        """Après reload, update_from_controller est appelé avec le nouveau contrôleur."""
        entry = _make_entry(
            data={CONF_MIN_ON_DURATION_MIN: 45, CONF_MIN_OFF_DURATION_MIN: 25},
            unique_id=DOMAIN,
        )
        hass = _make_hass_with_data(entries=[entry])
        thermostat = _make_thermostat(
            hass,
            unique_id="vt_uid",
            target_temperature=20.0,
            current_temperature=18.0,
        )

        # --- Premier handler ---
        handler1 = PelletRegulationHandler(thermostat)
        handler1.init_algorithm()
        _mock_store(handler1)

        cb = MagicMock()
        hass.data.setdefault(DOMAIN, {})[DATA_SENSOR_ADD_CB] = cb

        await handler1.async_added_to_hass()
        real_sensor = handler1._debug_sensor  # sensor réellement créé

        # Simule update_from_controller (normalement appelé par control_heating)
        now = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)
        real_sensor.update_from_controller(handler1._controller, now)

        # Le guard du handler1 a les valeurs d'origine.
        assert handler1._controller._guard.min_on_duration_min == 45

        # --- Simulation d'un reload : remove du handler1, nouveau handler ---
        handler1.remove()  # libère la référence locale ; le sensor reste dans hass.data

        handler2 = PelletRegulationHandler(thermostat)
        handler2.init_algorithm()
        _mock_store(handler2)
        await handler2.async_added_to_hass()

        # handler2 doit récupérer le même objet capteur.
        assert handler2._debug_sensor is real_sensor
        # async_add_entities ne doit pas être rappelé.
        assert cb.call_count == 1  # appelé uniquement lors du premier handler

        # Après la mise à jour, le capteur expose les valeurs du nouveau contrôleur.
        handler2._debug_sensor.update_from_controller(handler2._controller, now)
        attrs = handler2._debug_sensor.extra_state_attributes
        assert attrs["min_on_duration_min"] == 45  # valeur inchangée ici
        assert attrs["min_off_duration_min"] == 25


# ===========================================================================
# Scénario 11 — Reconfiguration : options effacées → data mis à jour utilisé
# ===========================================================================


class TestScenario11Reconfigure:
    """Vérifie que _resolve_options lit les nouvelles values après une reconfiguration.

    Lors d'une reconfiguration (async_step_reconfigure), le flux enregistre les
    nouvelles valeurs dans ``entry.data`` et vide ``entry.options`` (``{}``).
    ``_resolve_options`` doit alors ignorer les anciennes options et utiliser
    exclusivement ``entry.data``.
    """

    def test_cleared_options_fall_back_to_data(self):
        """Après reconfigure, entry.options={} → _resolve_options lit entry.data."""
        # Simule un entry ayant des *anciennes* options (issues d'un options-flow)
        # puis une reconfiguration qui les a vidées et a mis à jour entry.data.
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 1.5, CONF_HYSTERESIS_OFF: 0.8},
            options={},  # vidé par async_update_reload_and_abort(options={})
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        opts = _resolve_options(hass, "any_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.5)
        assert opts[CONF_HYSTERESIS_OFF] == pytest.approx(0.8)

    def test_reconfigure_data_overrides_previous_options(self):
        """Reconfigure met à jour data ; options vidées → nouvelles valeurs lues."""
        # Avant reconfigure : data={hyst=0.5}, options={hyst=1.0}
        # Après reconfigure  : data={hyst=2.0}, options={}
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 2.0},
            options={},  # vidé par la reconfiguration
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        opts = _resolve_options(hass, "uid")
        # Doit utiliser la nouvelle valeur de data, pas l'ancienne options
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(2.0)

    def test_per_thermostat_reconfigure_preserves_target(self):
        """Reconfigure per-thermostat : CONF_TARGET_VTHERM reste dans data."""
        per_entry = _make_entry(
            data={CONF_TARGET_VTHERM: "vt_uid", CONF_HYSTERESIS_ON: 1.8},
            options={},  # vidé par reconfigure
            unique_id=f"{DOMAIN}-vt_uid",
        )
        hass = _make_hass(entries=[per_entry])
        opts = _resolve_options(hass, "vt_uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.8)

    def test_handler_reads_reconfigured_data_on_init(self):
        """Après reconfigure, le nouveau handler lit entry.data (options vides)."""
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.9, CONF_HYSTERESIS_OFF: 0.6},
            options={},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        assert handler._controller._hysteresis.hysteresis_on == pytest.approx(0.9)
        assert handler._controller._hysteresis.hysteresis_off == pytest.approx(0.6)

    def test_options_still_override_data_when_non_empty(self):
        """Si entry.options est non-vide (options-flow), il prime toujours sur data."""
        entry = _make_entry(
            data={CONF_HYSTERESIS_ON: 0.5},
            options={CONF_HYSTERESIS_ON: 1.3},
            unique_id=DOMAIN,
        )
        hass = _make_hass(entries=[entry])
        opts = _resolve_options(hass, "uid")
        assert opts[CONF_HYSTERESIS_ON] == pytest.approx(1.3)


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

        # Stable state (locked_on): no transition → aucune commande envoyée au scheduler.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is True
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

        scheduler.start_cycle.assert_awaited_once()
        scheduler.cancel_cycle.assert_awaited_once()
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

    @pytest.mark.parametrize("entity_domain", ["switch", "input_boolean"])
    @pytest.mark.parametrize(
        ("contact_state", "expected_heating"),
        [("on", True), ("off", False)],
    )
    async def test_switch_startup_adopts_without_dates_or_commands(
        self, entity_domain, contact_state, expected_heating
    ):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            vtherm_hvac_mode="heat",
            underlying_list=[f"{entity_domain}.pellet_stove"],
            underlying_state=contact_state,
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler, load_data=None)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.is_heating is expected_heating
        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is None
        store.async_save.assert_awaited_once()
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()

    async def test_switch_startup_on_with_parent_off_preserves_adopted_state(self):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            vtherm_hvac_mode="off",
            underlying_list=["switch.pellet_stove"],
            underlying_state="on",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=None)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.is_heating is True
        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is None
        scheduler.start_cycle.assert_not_awaited()

    @pytest.mark.parametrize("initial_state", ["unknown", "unavailable"])
    @pytest.mark.parametrize("known_state", ["on", "off"])
    async def test_switch_adoption_waits_until_state_is_known(
        self, initial_state, known_state
    ):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state=initial_state,
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=None)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()
        assert handler._switch_adoption_pending is True

        await handler.control_heating(timestamp=_now())
        assert handler._controller.is_heating is False
        scheduler.start_cycle.assert_not_awaited()

        hass.states.async_set("switch.pellet_stove", known_state)
        await handler.control_heating(timestamp=_now())

        assert handler._switch_adoption_pending is False
        assert handler._controller.is_heating is (known_state == "on")
        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is None
        scheduler.start_cycle.assert_not_awaited()

    async def test_missing_switch_state_does_not_adopt(self):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state="off",
        )
        hass.states.get.side_effect = lambda _entity_id: None
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=None)

        await handler.async_added_to_hass()
        await handler.async_startup()
        await handler.control_heating(timestamp=_now())

        assert handler._switch_adoption_pending is True
        assert handler._controller.is_heating is False
        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is None

    @pytest.mark.parametrize(
        ("contact_state", "stored_on", "stored_off", "expected_on", "expected_off"),
        [
            (
                "on",
                "2026-01-15T19:30:00",
                None,
                datetime(2026, 1, 15, 19, 30, tzinfo=timezone.utc),
                None,
            ),
            (
                "off",
                None,
                "2026-01-15T19:30:00+00:00",
                None,
                datetime(2026, 1, 15, 19, 30, tzinfo=timezone.utc),
            ),
            (
                "on",
                "not-an-iso-date",
                None,
                None,
                None,
            ),
        ],
    )
    async def test_switch_restore_preserves_only_valid_relevant_date(
        self, contact_state, stored_on, stored_off, expected_on, expected_off
    ):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state=contact_state,
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(
            handler,
            load_data={
                "is_heating": contact_state == "on",
                "last_on_at": stored_on,
                "last_off_at": stored_off,
            },
        )

        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.state.last_on_at == expected_on
        assert handler._controller.state.last_off_at == expected_off

    async def test_switch_restore_discards_future_and_contradictory_current_date(self):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state="on",
        )
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        old_on = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        recent_off = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(
            handler,
            load_data={
                "is_heating": True,
                "last_on_at": future,
                "last_off_at": recent_off,
            },
        )

        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is not None

        _mock_store(
            handler,
            load_data={
                "is_heating": True,
                "last_on_at": old_on,
                "last_off_at": recent_off,
            },
        )
        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is not None

    async def test_switch_restore_inhibits_old_power_state_without_losing_deadlines(
        self,
    ):
        now = datetime.now(timezone.utc)
        last_on_at = now - timedelta(minutes=10)
        last_off_at = now - timedelta(hours=2)
        boost_until = now + timedelta(minutes=5)
        stored_data = {
            "is_heating": True,
            "current_level_index": 2,
            "last_on_at": last_on_at.isoformat(),
            "last_off_at": last_off_at.isoformat(),
            "last_reason": "below_on_threshold",
            "boost_until": boost_until.isoformat(),
        }
        hass = _make_hass(
            entries=[
                _make_entry(
                    data={},
                    options={
                        CONF_POWER_CONTROL_ENABLED: True,
                        CONF_POWER_BOOST_ENABLED: True,
                        CONF_POWER_LEVELS: ["1", "2", "3", "4", "5"],
                    },
                    unique_id=DOMAIN,
                )
            ]
        )
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state="on",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler, load_data=stored_data)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()

        controller = handler._controller
        assert controller.state.is_heating is True
        assert controller.state.current_level_index == 2
        assert controller.current_level_value is None
        assert controller._boost_manager is None
        assert controller.state.last_on_at == last_on_at
        assert controller.state.last_off_at == last_off_at
        assert controller.state.boost_until == boost_until
        debug_state = controller.get_debug_attributes(now)
        assert debug_state["boost_active"] is False
        assert debug_state["next_action_allowed_at"] == (
            last_on_at + timedelta(minutes=30)
        ).isoformat()
        assert store.async_save.await_args.args[0]["boost_until"] == boost_until.isoformat()
        hass.services.async_call.assert_not_awaited()
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()

    @pytest.mark.parametrize(
        ("contact_state", "current_temperature", "expected_heating", "date_key"),
        [
            ("off", 18.0, True, "last_on_at"),
            ("on", 20.5, False, "last_off_at"),
        ],
    )
    async def test_switch_first_controlled_transition_is_dated_after_adoption(
        self, contact_state, current_temperature, expected_heating, date_key
    ):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            current_temperature=current_temperature,
            underlying_list=["switch.pellet_stove"],
            underlying_state=contact_state,
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler, load_data=None)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()

        assert handler._controller.state.last_on_at is None
        assert handler._controller.state.last_off_at is None
        scheduler.start_cycle.assert_not_awaited()

        transition_at = _now()
        await handler.control_heating(timestamp=transition_at)

        assert handler._controller.is_heating is expected_heating
        assert getattr(handler._controller.state, date_key) == transition_at
        scheduler.start_cycle.assert_awaited_once()
        _, on_percent, force = scheduler.start_cycle.call_args.args
        assert on_percent == pytest.approx(1.0 if expected_heating else 0.0)
        assert force is True
        scheduler.cancel_cycle.assert_awaited_once()
        saved_state = store.async_save.await_args_list[-1].args[0]
        assert saved_state[date_key] == transition_at.isoformat()

    async def test_switch_cycles_hold_and_restore_without_duplicate_commands(self):
        initial_on_at = _now()
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            current_temperature=18.0,
            underlying_list=["switch.pellet_stove"],
            underlying_state="off",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler, load_data=None)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()
        await handler.control_heating(timestamp=initial_on_at)
        assert handler._controller.state.last_on_at == initial_on_at
        hass.states.async_set("switch.pellet_stove", "on")

        thermostat.current_temperature = 20.0
        await handler.control_heating(timestamp=initial_on_at + timedelta(minutes=1))
        assert handler._controller.state.last_on_at == initial_on_at
        scheduler.start_cycle.assert_awaited_once()

        guard = handler._controller._guard
        off_at = initial_on_at + timedelta(minutes=guard.min_on_duration_min + 1)
        thermostat.current_temperature = 20.5
        await handler.control_heating(timestamp=off_at)
        assert handler._controller.state.last_off_at == off_at
        assert scheduler.start_cycle.await_count == 2
        assert [call.args[1] for call in scheduler.start_cycle.await_args_list] == [
            1.0,
            0.0,
        ]
        assert [call.args[2] for call in scheduler.start_cycle.await_args_list] == [
            True,
            True,
        ]
        assert scheduler.cancel_cycle.await_count == 2
        hass.states.async_set("switch.pellet_stove", "off")
        off_snapshot = store.async_save.await_args_list[-1].args[0]

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            current_temperature=20.0,
            underlying_list=["switch.pellet_stove"],
            underlying_state="off",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        store = _mock_store(handler, load_data=off_snapshot)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()
        assert handler._controller.state.last_on_at == initial_on_at
        assert handler._controller.state.last_off_at == off_at
        scheduler.start_cycle.assert_not_awaited()

        await handler.control_heating(timestamp=off_at + timedelta(minutes=1))
        assert handler._controller.state.last_off_at == off_at
        scheduler.start_cycle.assert_not_awaited()

        next_on_at = off_at + timedelta(
            minutes=guard.min_off_duration_min + guard.cooldown_duration_min + 1
        )
        thermostat.current_temperature = 18.0
        await handler.control_heating(timestamp=next_on_at)
        assert handler._controller.state.last_on_at == next_on_at
        assert scheduler.start_cycle.await_count == 1
        _, on_percent, force = scheduler.start_cycle.call_args.args
        assert on_percent == pytest.approx(1.0)
        assert force is True
        scheduler.cancel_cycle.assert_awaited_once()
        hass.states.async_set("switch.pellet_stove", "on")
        on_snapshot = store.async_save.await_args_list[-1].args[0]

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            current_temperature=20.0,
            underlying_list=["switch.pellet_stove"],
            underlying_state="on",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=on_snapshot)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.async_added_to_hass()
        await handler.async_startup()
        await handler.control_heating(timestamp=next_on_at + timedelta(minutes=1))

        assert handler._controller.is_heating is True
        assert handler._controller.state.last_on_at == next_on_at
        assert handler._controller.state.last_off_at == off_at
        scheduler.start_cycle.assert_not_awaited()

    @pytest.mark.parametrize(
        ("contact_state", "elapsed_offset"),
        [
            ("on", -1),
            ("on", 0),
            ("on", 1),
            ("off", -1),
            ("off", 0),
            ("off", 1),
        ],
    )
    async def test_switch_restored_guard_deadlines_keep_original_timestamp(
        self, contact_state, elapsed_offset
    ):
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            underlying_list=["switch.pellet_stove"],
            underlying_state=contact_state,
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        guard = handler._controller._guard
        required_minutes = (
            guard.min_on_duration_min
            if contact_state == "on"
            else guard.min_off_duration_min + guard.cooldown_duration_min
        )
        elapsed_minutes = required_minutes + elapsed_offset
        transition_at = _now() - timedelta(minutes=elapsed_minutes)
        state_key = "last_on_at" if contact_state == "on" else "last_off_at"
        store_data = {
            "is_heating": contact_state == "on",
            "last_on_at": transition_at.isoformat() if contact_state == "on" else None,
            "last_off_at": transition_at.isoformat() if contact_state == "off" else None,
        }
        _mock_store(handler, load_data=store_data)

        await handler.async_added_to_hass()
        await handler.async_startup()

        adopted_at = getattr(handler._controller.state, state_key)
        assert adopted_at == transition_at
        expected_deadline = transition_at + timedelta(minutes=required_minutes)
        assert (
            handler._controller.get_debug_attributes(_now())["next_action_allowed_at"]
            == expected_deadline.isoformat()
        )
        can_transition = elapsed_minutes >= required_minutes
        if contact_state == "on":
            assert guard.can_turn_off(_now(), handler._controller.state) is can_transition
        else:
            assert guard.can_turn_on(_now(), handler._controller.state) is can_transition

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


# ===========================================================================
# Scénario 13 — Transition ON→OFF force l'arrêt immédiat du cycle
# ===========================================================================


class TestScenario13ForceOnToOffTransition:
    """Vérifie que start_cycle est appelé avec force=True lors d'une transition ON→OFF.

    Contexte : quand le contrôleur détecte une transition réelle ON→OFF
    (ex. above_off_threshold ou safety), VTherm doit arrêter le cycle
    *immédiatement* sans attendre la fin du cycle en cours. Cela nécessite
    que control_heating passe force=True au scheduler lors de ce changement
    d'état.
    """

    async def test_above_off_threshold_forces_scheduler_stop(self):
        """Transition ON→OFF (above_off_threshold) → start_cycle appelé avec force=True."""
        # Poêle allumé il y a 65 min → min_on_duration (30 min) écoulée.
        sixty_five_min_ago = _now() - timedelta(minutes=65)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": sixty_five_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=17.0,
            current_temperature=19.9,  # ≥ 17.0 + 0.3 → above_off_threshold
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        _, on_percent, force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(0.0)
        assert handler._controller.last_reason == "above_off_threshold"
        # Force doit être True pour stopper le cycle immédiatement.
        assert force is True
        scheduler.cancel_cycle.assert_awaited_once()

    async def test_locked_on_does_not_force(self):
        """Quand le garde-fous maintient ON (locked_on), force reste False."""
        # Poêle allumé il y a 1 min → min_on_duration (30 min) non écoulée.
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
            target_temperature=17.0,
            current_temperature=19.9,  # dépasserait le seuil mais garde-fous bloque
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Stable state (locked_on): aucune transition → aucune commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is True
        assert handler._controller.last_reason == "locked_on"

    async def test_already_off_no_force(self):
        """Si le poêle était déjà éteint et reste éteint, force=False."""
        stored_data = {
            "is_heating": False,
            "current_level_index": None,
            "last_on_at": None,
            "last_off_at": (_now() - timedelta(minutes=60)).isoformat(),
            "last_reason": "above_off_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=17.0,
            current_temperature=19.9,  # reste au-dessus → hold OFF
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Stable state (already off, no transition): aucune commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is False
        # hold_in_band : la temp est déjà au-dessus du seuil, le contrôleur
        # maintient simplement OFF sans relancer de transition.
        assert handler._controller.last_reason in (
            "above_off_threshold",
            "hold_in_band",
        )

    async def test_safety_transition_also_forces(self):
        """Transition ON→OFF par sécurité haute température → force=True aussi."""
        one_min_ago = _now() - timedelta(minutes=1)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": one_min_ago.isoformat(),
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

        _, on_percent, force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(0.0)
        assert handler._controller.last_reason == "safety"
        # Même pour safety, la transition ON→OFF doit forcer l'arrêt immédiat.
        assert force is True
        scheduler.cancel_cycle.assert_awaited_once()

    async def test_off_to_on_transition_forces_scheduler_start(self):
        """Transition OFF→ON (cooldown écoulé + below_on_threshold) → force=True."""
        # Poêle éteint il y a 90 min → min_off + cooldown (30+10=40 min) écoulée.
        ninety_min_ago = _now() - timedelta(minutes=90)
        stored_data = {
            "is_heating": False,
            "current_level_index": None,
            "last_on_at": None,
            "last_off_at": ninety_min_ago.isoformat(),
            "last_reason": "above_off_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=18.5,  # ≤ 20.0 − 0.5 → below_on_threshold
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        _, on_percent, force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(1.0)
        assert handler._controller.last_reason == "below_on_threshold"
        # Force doit être True pour démarrer le cycle immédiatement.
        assert force is True
        scheduler.cancel_cycle.assert_awaited_once()

    async def test_locked_off_does_not_force(self):
        """Quand le garde-fous maintient OFF (locked_off), force reste False."""
        # Poêle éteint il y a 5 min → min_off + cooldown (30+10=40 min) non écoulée.
        five_min_ago = _now() - timedelta(minutes=5)
        stored_data = {
            "is_heating": False,
            "current_level_index": None,
            "last_on_at": None,
            "last_off_at": five_min_ago.isoformat(),
            "last_reason": "above_off_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=18.5,  # demanderait ON mais garde-fous bloque
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Stable state (locked_off): aucune transition → aucune commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is False
        assert handler._controller.last_reason == "locked_off"


class TestScenario14ChangedFalseStillRecomputes:
    """Vérifie que le handler pellet recalcule même quand changed=False."""

    async def test_above_off_threshold_recomputed_when_changed_false(self):
        """changed=False ne doit pas empêcher une transition ON→OFF immédiate."""
        sixty_five_min_ago = _now() - timedelta(minutes=65)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": sixty_five_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=17.0,
            current_temperature=19.9,
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.on_state_changed(False)

        scheduler.start_cycle.assert_awaited_once()
        scheduler.cancel_cycle.assert_awaited_once()
        _, on_percent, force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(0.0)
        assert handler._controller.last_reason == "above_off_threshold"
        assert handler._controller.is_heating is False
        assert force is True


# ===========================================================================
# Scénario 14 — Redémarrage avec is_heating=True persisté mais hvac_mode=off
# ===========================================================================


class TestScenario14StaleHeatingOnRestart:
    """Vérifie que is_heating=True périmé dans le Store ne pose pas last_off_at=now.

    Contexte : si HA se coupe pendant que le poêle chauffait (is_heating=True)
    et que VTherm a sauvegardé hvac_mode=off (ex. bouton off appuyé juste avant),
    la restauration recharge is_heating=True depuis le Store. Lors du premier
    control_heating avec hvac_mode=off, _compute() détecte is_heating=True et
    pose last_off_at=now → le garde-fous min_off+cooldown est armé à l'instant
    du redémarrage → si l'utilisateur bascule immédiatement en heat, il attend
    min_off+cooldown minutes (jusqu'à 1h dans les configs courantes) avant que
    le poêle ne s'allume.

    La correction attendue : async_startup() doit détecter cette incohérence et
    corriger is_heating=False SANS toucher last_off_at, afin que le garde-fous
    ne soit pas armé inutilement.
    """

    async def test_stale_is_heating_does_not_set_last_off_at(self):
        """Store is_heating=True + hvac_mode=off → last_off_at ne doit PAS être mis à now."""
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": (_now() - timedelta(minutes=90)).isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="off",  # ← VTherm est en mode off au démarrage
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        # Simule le démarrage HA : async_startup() applique le guard AVANT
        # d'appeler control_heating() (via on_state_changed).
        await handler.async_startup()

        # last_off_at ne doit PAS avoir été armé : le Store avait last_off_at=None
        # et aucune extinction réelle n'a eu lieu pendant cet arrêt.
        assert handler._controller.state.last_off_at is None

    async def test_stale_is_heating_then_heat_no_locked_off(self):
        """Après redémarrage (is_heating=True périmé + hvac_mode=off), passer en heat
        doit allumer immédiatement (reason != locked_off).
        """
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": (_now() - timedelta(minutes=90)).isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="off",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        # Simule le démarrage HA : async_startup() applique le guard, puis
        # appelle control_heating() via on_state_changed (hvac_mode=off → no cmd).
        await handler.async_startup()

        # L'utilisateur bascule immédiatement en heat.
        thermostat.vtherm_hvac_mode = "heat"
        await handler.control_heating(timestamp=_now())

        _, on_percent, _force = scheduler.start_cycle.call_args[0]
        # Le poêle doit s'allumer (ou demander ON) sans attendre 1h.
        assert on_percent == pytest.approx(1.0)
        assert handler._controller.last_reason != "locked_off"
        scheduler.cancel_cycle.assert_awaited_once()

    async def test_stale_is_heating_with_existing_last_off_at_preserved(self):
        """Si le Store a déjà un last_off_at ancien, il doit être conservé tel quel.

        Cas : poêle éteint normalement (last_off_at sauvegardé), puis is_heating
        sauvegardé True par erreur. La valeur ancienne de last_off_at prime sur
        toute réinitialisation spurieuse.
        """
        old_off_at = _now() - timedelta(hours=24)  # éteint depuis 24h
        stored_data = {
            "is_heating": True,  # périmé
            "current_level_index": None,
            "last_on_at": (_now() - timedelta(hours=25)).isoformat(),
            "last_off_at": old_off_at.isoformat(),  # déjà présent
            "last_reason": "hvac_off",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="off",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        # Simule le démarrage HA : async_startup() applique le guard.
        await handler.async_startup()

        # last_off_at doit rester la valeur d'origine (24h ago), PAS now.
        assert handler._controller.state.last_off_at == old_off_at

        # Et l'allumage en heat doit être immédiat (24h >> min_off+cooldown).
        thermostat.vtherm_hvac_mode = "heat"
        await handler.control_heating(timestamp=_now())

        _, on_percent, _force = scheduler.start_cycle.call_args[0]
        assert on_percent == pytest.approx(1.0)
        assert handler._controller.last_reason != "locked_off"
        scheduler.cancel_cycle.assert_awaited_once()


# ===========================================================================
# Scénario 15 — Contrôle binaire sans cycling
# ===========================================================================


class TestScenario15BinaryControlNoCycling:
    """Vérifie le comportement sans cycling pour le contrôle binaire (0%/100%).

    Les poêles à granulés produisent uniquement 0% ou 100%. Le scheduler ne
    doit envoyer une commande QUE lors des transitions ou en cas de force=True.
    En état stable, aucune commande n'est envoyée (pas de start_cycle ni
    cancel_cycle), ce qui évite de réinitialiser le timer hardware de cooldown.
    """

    async def test_stable_heating_no_command_sent(self):
        """En chauffage stable (pas de transition, force=False) → aucune commande."""
        # Poêle allumé il y a 5 min (en dessous du seuil d'extinction).
        five_min_ago = _now() - timedelta(minutes=5)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": five_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # Reste en dessous du seuil ON → locked_on
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # État stable : aucune commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is True

    async def test_stable_off_no_command_sent(self):
        """En arrêt stable (pas de transition, force=False) → aucune commande."""
        # Poêle éteint il y a 60 min, température toujours au-dessus.
        sixty_min_ago = _now() - timedelta(minutes=60)
        stored_data = {
            "is_heating": False,
            "current_level_index": None,
            "last_on_at": None,
            "last_off_at": sixty_min_ago.isoformat(),
            "last_reason": "above_off_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=17.0,
            current_temperature=19.9,  # Reste au-dessus → stable OFF
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # État stable : aucune commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_not_awaited()
        assert handler._controller.is_heating is False

    async def test_force_sends_command_and_cancels(self):
        """force=True → start_cycle appelé puis cancel_cycle immédiatement."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # below threshold → heating
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now(), force=True)

        scheduler.start_cycle.assert_awaited_once()
        scheduler.cancel_cycle.assert_awaited_once()
        _, _, force = scheduler.start_cycle.call_args[0]
        assert force is True

    async def test_leftover_cycle_gets_cancelled_without_new_command(self):
        """État stable + cycle en cours → seulement cancel_cycle, pas start_cycle."""
        # Poêle déjà en chauffage stable (pas de transition).
        five_min_ago = _now() - timedelta(minutes=5)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": five_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        scheduler.is_cycle_running = True  # Simule un cycle résiduel
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Cycle résiduel annulé, mais aucune nouvelle commande envoyée.
        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_awaited_once()

    async def test_energy_credited_after_cycle_min(self):
        """incremente_energy est appelé après cycle_min minutes de chauffage."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # below threshold → heating
            vtherm_hvac_mode="heat",
        )
        thermostat.cycle_min = 5  # 5 min → 300 s
        thermostat.incremente_energy = MagicMock()

        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        t0 = _now()
        # Premier appel : _last_energy_at initialisé, pas de crédit.
        await handler.control_heating(timestamp=t0)
        thermostat.incremente_energy.assert_not_called()

        # Deuxième appel après 6 min (> 5 min) : énergie créditée.
        t1 = t0 + timedelta(minutes=6)
        await handler.control_heating(timestamp=t1)
        thermostat.incremente_energy.assert_called_once()

    async def test_energy_not_credited_before_cycle_min(self):
        """incremente_energy N'est PAS appelé avant cycle_min minutes."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="heat",
        )
        thermostat.cycle_min = 5
        thermostat.incremente_energy = MagicMock()

        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        t0 = _now()
        await handler.control_heating(timestamp=t0)

        # Deuxième appel après seulement 2 min (< 5 min) : pas de crédit.
        t1 = t0 + timedelta(minutes=2)
        await handler.control_heating(timestamp=t1)
        thermostat.incremente_energy.assert_not_called()

    async def test_energy_tracker_reset_on_turn_off(self):
        """_last_energy_at est remis à None lorsque le poêle s'éteint."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # below threshold → heating
            vtherm_hvac_mode="heat",
        )
        thermostat.cycle_min = 5
        thermostat.incremente_energy = MagicMock()

        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        t0 = _now()
        await handler.control_heating(timestamp=t0)
        assert handler._last_energy_at is not None

        # Bascule au-dessus du seuil → extinction.
        thermostat.current_temperature = 25.0
        t1 = t0 + timedelta(minutes=35)  # min_on_duration (30min) écoulée
        await handler.control_heating(timestamp=t1)

        # _last_energy_at doit être remis à None.
        assert handler._last_energy_at is None

    async def test_hvac_off_does_not_send_start_cycle(self):
        """hvac_mode=off → VTherm gère déjà turn_off ; on ne doit PAS appeler
        start_cycle (ce qui enverrait un second F0000 en concurrence avec le
        set_hvac_mode=off de VTherm, causant une erreur 'No ACK').
        """
        # Poêle en chauffe depuis 35 min → prêt à s'éteindre.
        thirty_five_min_ago = _now() - timedelta(minutes=35)
        stored_data = {
            "is_heating": True,
            "current_level_index": None,
            "last_on_at": thirty_five_min_ago.isoformat(),
            "last_off_at": None,
            "last_reason": "below_on_threshold",
            "boost_until": None,
        }

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="off",  # ← L'utilisateur a pressé OFF
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler, load_data=stored_data)
        await handler.async_added_to_hass()

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        # Aucun appel à start_cycle : VTherm a déjà envoyé set_hvac_mode=off
        # via son propre mécanisme (qui génère F0000).
        scheduler.start_cycle.assert_not_awaited()
        # Le cycle est quand même annulé si un résidu existait.
        assert handler._controller.is_heating is False

    async def test_hvac_off_with_running_cycle_cancels_it(self):
        """hvac_mode=off + cycle résiduel → cancel_cycle() appelé, pas start_cycle."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="off",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        scheduler.is_cycle_running = True  # Simule un cycle résiduel
        handler.on_scheduler_ready(scheduler)

        await handler.control_heating(timestamp=_now())

        scheduler.start_cycle.assert_not_awaited()
        scheduler.cancel_cycle.assert_awaited_once()


# ===========================================================================
# Scénario 16 — Proxy prop_algorithm : protection contre le double calculate()
# ===========================================================================


class TestScenario16PropAlgoProxy:
    """Vérifie que _PropAlgoProxy bloque l'appel spurieux de recalculate().

    Bug Fix 4 : ThermostatProp.recalculate() appelle _prop_algorithm.calculate()
    AVANT que async_control_heating() atteigne notre handler.  Cet appel
    anticipé effectuait la transition OFF→ON sur le contrôleur.  Quand
    control_heating() s'exécutait ensuite, was_heating était déjà True →
    aucune transition détectée → F0001 jamais envoyé → poêle bloqué.
    """

    def test_prop_algorithm_is_proxy_after_init(self):
        """init_algorithm() expose un _PropAlgoProxy, pas le contrôleur directement."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        algo = thermostat.prop_algorithm
        assert isinstance(algo, _PropAlgoProxy), (
            "thermostat.prop_algorithm devrait être un _PropAlgoProxy, "
            f"got {type(algo)}"
        )
        assert (
            algo is not handler._controller
        ), "thermostat.prop_algorithm ne doit PAS être le contrôleur directement"

    def test_proxy_on_percent_delegates_to_controller(self):
        """_PropAlgoProxy.on_percent lit le contrôleur sous-jacent."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        proxy = thermostat.prop_algorithm
        assert isinstance(proxy, _PropAlgoProxy)
        # Le contrôleur est initialisé avec is_heating=False → on_percent=0
        assert proxy.on_percent == handler._controller.on_percent

    def test_proxy_calculate_is_noop(self):
        """_PropAlgoProxy.calculate() ne modifie pas l'état du contrôleur."""
        hass = _make_hass()
        thermostat = _make_thermostat(hass)
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()

        proxy = thermostat.prop_algorithm
        assert isinstance(proxy, _PropAlgoProxy)

        before_heating = handler._controller.is_heating

        # Simule ce que ThermostatProp.recalculate() ferait avec des args positionnels
        proxy.calculate(20.0, 19.0, 15.0, -0.1, "heat", power_shedding=False)

        # L'état du contrôleur ne doit PAS avoir changé
        assert (
            handler._controller.is_heating == before_heating
        ), "Le proxy.calculate() a modifié l'état du contrôleur — le no-op est cassé"

    @pytest.mark.asyncio
    async def test_transition_detected_despite_prior_recalculate_call(self):
        """Fix 4 : la transition OFF→ON est détectée même si recalculate() avait
        déjà appelé controller.calculate() juste avant control_heating().

        Simule : cooldown expiré, recalculate() appelle proxy.calculate() (no-op),
        puis control_heating() appelle controller.calculate() et doit voir
        was_heating=False → transition_on=True → F0001 envoyé.
        """
        now = _now()
        # Les options par défaut sont min_off=20 min + cooldown=5 min = 25 min.
        # On place last_off_at 26 minutes dans le passé pour que can_turn_on() soit True.
        total_delay_min = (
            DEFAULT_OPTIONS[CONF_MIN_OFF_DURATION_MIN]
            + DEFAULT_OPTIONS[CONF_COOLDOWN_DURATION_MIN]
        )

        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,  # Chambre froide → veut chauffer
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        # Placer le contrôleur en état « cooldown venant d'expirer »
        t_off = now - timedelta(minutes=total_delay_min + 1)
        handler._controller._state.last_off_at = t_off
        handler._controller._state.is_heating = False

        # Vérifier que le contrôleur confirme la fin du cooldown
        # (pré-condition du test)
        assert handler._controller._state.is_heating is False

        # ── Étape 1 : simuler l'appel spurieux de recalculate() ──────────────
        # ThermostatProp.recalculate() appelle proxy.calculate() avec les args
        # positionnels habituels (ext_temp, slope, hvac_mode emballés dans *args).
        proxy = thermostat.prop_algorithm
        assert isinstance(proxy, _PropAlgoProxy), "Le proxy doit être en place"
        proxy.calculate(
            thermostat.target_temperature,
            thermostat.current_temperature,
            15.0,  # ext_temp (→ *args, ignoré)
            -0.1,  # slope   (→ *args, ignoré)
            "heat",  # hvac_mode (→ *args, ignoré — kwarg non passé)
            power_shedding=False,
        )

        # Après le no-op du proxy, l'état du contrôleur est inchangé
        assert (
            handler._controller._state.is_heating is False
        ), "Le proxy.calculate() a provoqué une transition — le no-op est cassé"

        # ── Étape 2 : control_heating() s'exécute (vrai appel autorisé) ──────
        await handler.control_heating(timestamp=now)

        # La transition OFF→ON DOIT être détectée et F0001 envoyé
        assert (
            handler._controller.is_heating is True
        ), "Le contrôleur devrait être en is_heating=True après expiration du cooldown"
        scheduler.start_cycle.assert_awaited_once()
        scheduler.cancel_cycle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_control_heating_does_not_replace_proxy_with_controller(self):
        """control_heating() ne doit pas écraser le proxy par le contrôleur."""
        hass = _make_hass()
        thermostat = _make_thermostat(
            hass,
            target_temperature=20.0,
            current_temperature=19.0,
            vtherm_hvac_mode="heat",
        )
        handler = PelletRegulationHandler(thermostat)
        handler.init_algorithm()
        _mock_store(handler)

        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)

        proxy_before = thermostat.prop_algorithm
        assert isinstance(proxy_before, _PropAlgoProxy)

        await handler.control_heating(timestamp=_now())

        proxy_after = thermostat.prop_algorithm
        assert (
            proxy_after is proxy_before
        ), "control_heating() a remplacé le proxy par autre chose — bug !"
        assert isinstance(
            proxy_after, _PropAlgoProxy
        ), "control_heating() a remplacé le proxy par le contrôleur directement"
