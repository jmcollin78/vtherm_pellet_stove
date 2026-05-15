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
    DATA_DEBUG_SENSORS_PREFIX,
    DATA_SENSOR_ADD_CB,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from custom_components.vtherm_pellet_stove.handler import (
    PelletRegulationHandler,
    _PropAlgoProxy,
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

    def _create_task(coro, **kwargs):
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
        from datetime import datetime, timezone

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
