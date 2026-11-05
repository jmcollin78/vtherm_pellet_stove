"""Pellet stove regulation handler — Sprint 2 full implementation."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.core import Context
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import slugify
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_COOLDOWN_DURATION_MIN,
    CONF_DRY_CONTACT,
    CONF_BISTABLE_CONFIRMED,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_OFF_DURATION_MIN,
    CONF_MIN_ON_DURATION_MIN,
    CONF_MIN_ON_PERCENT,
    CONF_POWER_BOOST_DURATION_MIN,
    CONF_POWER_BOOST_ENABLED,
    CONF_POWER_CONTROL_ATTRIBUTE,
    CONF_POWER_CONTROL_ENABLED,
    CONF_POWER_DEFAULT_LEVEL_INDEX,
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
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .pellet.controller import HVAC_MODE_OFF, PelletRegulationController
from .sensor import PelletDebugSensor
from .target import observe_target, validate_target

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceCycleScheduler, InterfaceThermostatRuntime

_LOGGER = get_vtherm_logger(__name__)

# Key from versatile_thermostat const.py for the list of underlying entity IDs.
_CONF_UNDERLYING_LIST = "underlying_entity_ids"


class _PropAlgoProxy:
    """Read-only proxy exposing the pellet controller's on_percent to VTherm.

    VTherm's ``ThermostatProp.recalculate()`` calls ``_prop_algorithm.calculate()``
    on every temperature-sensor update **before** ``async_control_heating()``
    reaches our handler.  That spurious first call mutates the controller's
    internal state (e.g. it can set ``is_heating=True`` when the cooldown
    expires), so when our ``control_heating()`` runs immediately after and
    captures ``was_heating``, it already sees the post-transition value and
    detects **no transition** → F0001 is never sent and the stove stays off.

    By placing this proxy as ``prop_algorithm`` instead of the controller
    directly, ``recalculate()`` becomes a no-op for the pellet state machine.
    The authoritative ``calculate()`` call is the one made explicitly in
    ``PelletRegulationHandler.control_heating()``.
    """

    def __init__(self, controller: "PelletRegulationController") -> None:
        self._controller = controller

    # VTherm reads this to populate ``on_percent`` and ``power_percent``.
    @property
    def on_percent(self) -> float | None:  # type: ignore[override]
        return self._controller.on_percent

    # Used by feature_safety_manager and thermostat_valve.
    @property
    def calculated_on_percent(self) -> float:
        return self._controller.calculated_on_percent

    def calculate(self, *_args: Any, **_kwargs: Any) -> float:
        """No-op: actual calculation is managed by PelletRegulationHandler.control_heating()."""
        return self._controller.on_percent or 0.0


def _resolve_options(hass: Any, vtherm_uid: str | None) -> dict[str, Any]:
    """Return the effective options for a given VTherm unique_id.

    A per-thermostat entry is complete and never inherits global values.
    """
    _LOGGER.debug("%s - _resolve_options: start (vtherm_uid=%s)", DOMAIN, vtherm_uid)
    opts: dict[str, Any] = dict(DEFAULT_OPTIONS)

    global_entry = None
    per_entry = None

    for entry in hass.config_entries.async_entries(DOMAIN):
        target = entry.data.get(CONF_TARGET_VTHERM)
        if target is None and entry.unique_id == DOMAIN:
            global_entry = entry
        elif target == vtherm_uid:
            per_entry = entry

    selected_entry = per_entry or global_entry
    if selected_entry is not None:
        _LOGGER.debug(
            "%s - _resolve_options: applying %s options (target=%s)",
            DOMAIN,
            "per-thermostat" if per_entry is not None else "global",
            vtherm_uid,
        )
        opts.update(dict(selected_entry.options or selected_entry.data))

    local = dict(per_entry.options or per_entry.data) if per_entry is not None else {}
    opts[CONF_DRY_CONTACT] = local.get(CONF_DRY_CONTACT) is True
    opts[CONF_BISTABLE_CONFIRMED] = local.get(CONF_BISTABLE_CONFIRMED) is True

    _LOGGER.debug("%s - _resolve_options: completed", DOMAIN)
    return opts


class PelletRegulationHandler:
    """Handler implementing the VT external proportional algorithm lifecycle."""

    def __init__(self, thermostat: "InterfaceThermostatRuntime") -> None:
        """Bind the handler to a VT thermostat runtime object."""
        self._thermostat = thermostat
        self._scheduler: "InterfaceCycleScheduler | None" = None
        self._should_publish_intermediate: bool = True
        self._controller: PelletRegulationController | None = None
        self._prop_proxy: _PropAlgoProxy | None = None
        self._store: Store | None = None
        self._opts: dict[str, Any] = dict(DEFAULT_OPTIONS)
        self._last_applied_level_index: int | None = None
        self._debug_sensor: PelletDebugSensor | None = None
        self._last_energy_at: datetime | None = None
        self._control_lock = asyncio.Lock()
        self._reset_lock = asyncio.Lock()
        self._resetting = False
        self._removed = False
        self._restored = False
        self._unsubscribers: list = []
        self._target_error: str | None = None
        self._storage_error: str | None = None
        self._bound_target: dict | None = None
        self._stopping = False
        self._storage_lock: asyncio.Lock | None = None
        _LOGGER.debug("%s - __init__: handler created", self._thermostat.name)

    # ------------------------------------------------------------------
    # InterfacePropAlgorithmHandler contract
    # ------------------------------------------------------------------

    def init_algorithm(self) -> None:
        """Initialise the runtime algorithm state."""
        _LOGGER.debug("%s - init_algorithm: start", self._thermostat.name)
        hass = self._thermostat.hass
        vtherm_uid = self._thermostat.unique_id

        self._opts = _resolve_options(hass, vtherm_uid)
        self._bound_target = self._target_identity()
        domain_data = hass.data.setdefault(DOMAIN, {})
        self._storage_lock = domain_data.setdefault("cycle_storage_locks", {}).setdefault(
            vtherm_uid, asyncio.Lock()
        )

        self._controller = PelletRegulationController(
            name=self._thermostat.name,
            hysteresis_on=float(self._opts[CONF_HYSTERESIS_ON]),
            hysteresis_off=float(self._opts[CONF_HYSTERESIS_OFF]),
            min_on_percent=float(self._opts[CONF_MIN_ON_PERCENT]),
            max_on_percent=float(self._opts[CONF_MAX_ON_PERCENT]),
            min_on_duration_min=int(self._opts[CONF_MIN_ON_DURATION_MIN]),
            min_off_duration_min=int(self._opts[CONF_MIN_OFF_DURATION_MIN]),
            cooldown_duration_min=int(self._opts[CONF_COOLDOWN_DURATION_MIN]),
            safety_room_temp=float(self._opts[CONF_SAFETY_ROOM_TEMP]),
            power_control_enabled=bool(self._opts[CONF_POWER_CONTROL_ENABLED]) and not self._opts[CONF_DRY_CONTACT],
            power_levels=list(self._opts.get(CONF_POWER_LEVELS) or []) or None,
            power_default_level_index=int(self._opts[CONF_POWER_DEFAULT_LEVEL_INDEX]),
            power_boost_enabled=bool(self._opts[CONF_POWER_BOOST_ENABLED]) and not self._opts[CONF_DRY_CONTACT],
            power_boost_duration_min=int(self._opts[CONF_POWER_BOOST_DURATION_MIN]),
        )

        # Expose a proxy as prop_algorithm so VTherm can read on_percent at
        # any time while blocking the spurious controller.calculate() call that
        # ThermostatProp.recalculate() would otherwise trigger before our own
        # control_heating() runs (see _PropAlgoProxy docstring).
        self._prop_proxy = _PropAlgoProxy(self._controller)
        self._thermostat.prop_algorithm = self._prop_proxy

        # Initialise persistent store (one per thermostat unique_id).
        slug = slugify(vtherm_uid or DOMAIN)
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY.format(slug))

        _LOGGER.debug(
            "%s - init_algorithm hysteresis_on=%s hysteresis_off=%s "
            "min_on=%smin min_off=%smin cooldown=%smin safety=%s°C",
            self._thermostat.name,
            self._opts[CONF_HYSTERESIS_ON],
            self._opts[CONF_HYSTERESIS_OFF],
            self._opts[CONF_MIN_ON_DURATION_MIN],
            self._opts[CONF_MIN_OFF_DURATION_MIN],
            self._opts[CONF_COOLDOWN_DURATION_MIN],
            self._opts[CONF_SAFETY_ROOM_TEMP],
        )

    async def async_update_options(self) -> bool:
        """Apply the current effective options while retaining the live runtime."""
        async with self._control_lock:
            if self._removed or self._controller is None:
                return False

            options = _resolve_options(
                self._thermostat.hass, self._thermostat.unique_id
            )
            previous_options = deepcopy(self._opts)
            previous_power_enabled = bool(
                self._opts.get(CONF_POWER_CONTROL_ENABLED)
            )
            previous_power_attribute = self._opts.get(
                CONF_POWER_CONTROL_ATTRIBUTE, "fan_mode"
            )
            previous_level_index = self._controller.current_level_index
            previous_level_value = self._controller.current_level_value
            self._controller.update_configuration(
                hysteresis_on=float(options[CONF_HYSTERESIS_ON]),
                hysteresis_off=float(options[CONF_HYSTERESIS_OFF]),
                min_on_percent=float(options[CONF_MIN_ON_PERCENT]),
                max_on_percent=float(options[CONF_MAX_ON_PERCENT]),
                min_on_duration_min=int(options[CONF_MIN_ON_DURATION_MIN]),
                min_off_duration_min=int(options[CONF_MIN_OFF_DURATION_MIN]),
                cooldown_duration_min=int(options[CONF_COOLDOWN_DURATION_MIN]),
                safety_room_temp=float(options[CONF_SAFETY_ROOM_TEMP]),
                power_control_enabled=bool(options[CONF_POWER_CONTROL_ENABLED]) and not options[CONF_DRY_CONTACT],
                power_levels=list(options.get(CONF_POWER_LEVELS) or []) or None,
                power_default_level_index=int(
                    options[CONF_POWER_DEFAULT_LEVEL_INDEX]
                ),
                power_boost_enabled=bool(options[CONF_POWER_BOOST_ENABLED]) and not options[CONF_DRY_CONTACT],
                power_boost_duration_min=int(
                    options[CONF_POWER_BOOST_DURATION_MIN]
                ),
            )
            self._opts = options
            power_configuration_changed = (
                previous_power_enabled
                != bool(options[CONF_POWER_CONTROL_ENABLED])
                or previous_power_attribute
                != options.get(CONF_POWER_CONTROL_ATTRIBUTE, "fan_mode")
                or previous_level_index != self._controller.current_level_index
                or previous_level_value != self._controller.current_level_value
            )
            if power_configuration_changed:
                self._last_applied_level_index = None
            if self._debug_sensor is not None:
                self._debug_sensor.update_from_controller(self._controller)
            control_succeeded = False
            try:
                if self._scheduler is not None:
                    await self._async_control_heating()
                control_succeeded = True
            finally:
                if previous_options != options:
                    thermostat_state = self._thermostat.hass.states.get(
                        self._thermostat.entity_id
                    )
                    event_data = {
                        "entity_id": self._thermostat.entity_id,
                        "name": self._thermostat.name,
                        "state": (thermostat_state.state if thermostat_state else None),
                        "state_attributes": (
                            dict(thermostat_state.attributes)
                            if thermostat_state
                            else {}
                        ),
                        "configuration": {
                            key: deepcopy(options[key]) for key in DEFAULT_OPTIONS
                        },
                    }
                    try:
                        self._thermostat.hass.bus.async_fire(
                            EVENT_SETTINGS_UPDATED,
                            event_data,
                        )
                        if control_succeeded:
                            _LOGGER.info(
                                "%s - Sending event %s with data: %s",
                                self._thermostat.name,
                                EVENT_SETTINGS_UPDATED,
                                event_data["configuration"],
                            )
                    except Exception:  # pylint: disable=broad-except
                        _LOGGER.exception(
                            "%s - Failed to publish settings updated event",
                            self._thermostat.name,
                        )
            return True

    async def async_added_to_hass(self) -> None:
        """Restore persistent state when the thermostat entity is added to HA."""
        _LOGGER.debug("%s - async_added_to_hass: start", self._thermostat.name)
        if self._restored or self._controller is None or self._store is None:
            _LOGGER.debug(
                "%s - async_added_to_hass: skipped (controller/store not ready)",
                self._thermostat.name,
            )
            return

        try:
            async with self._storage_lock:
                cached = self._thermostat.hass.data.get(DOMAIN, {}).get(
                    "cycle_snapshots", {}
                ).get(self._thermostat.unique_id)
                data = deepcopy(cached) if cached is not None else await self._store.async_load()
        except (HomeAssistantError, OSError, ValueError) as err:
            self._storage_error = str(err)
            self._controller.state.resume_reason = "invalid"
            data = None
        if isinstance(data, dict) and "target" in data:
            if data.get("target") != self._target_identity():
                data = None
                self._controller.state.resume_reason = "invalid"
            else:
                data = {key: value for key, value in data.items() if key != "target"}
        elif isinstance(data, dict) and data.get("cycle_version") is not None:
            data = None
            self._controller.state.resume_reason = "invalid"
        if data is not None and not isinstance(data, dict):
            data = None
            self._controller.state.resume_reason = "invalid"
        if data:
            _LOGGER.debug("%s - async_added_to_hass: persisted data found", self._thermostat.name)
            self._controller.restore_state(data)
            _LOGGER.debug(
                "%s - async_added_to_hass: restored state is_heating=%s reason=%s",
                self._thermostat.name,
                self._controller.is_heating,
                self._controller.last_reason,
            )

            # NOTE: do NOT check vtherm_hvac_mode here.
            # async_added_to_hass() is called BEFORE VTherm restores its own
            # state (super().async_added_to_hass() runs after us in
            # ThermostatProp.async_added_to_hass()), so vtherm_hvac_mode is
            # always None at this point.  The stale-state guard is applied in
            # async_startup() where VTherm is fully initialised.
        else:
            _LOGGER.debug("%s - async_added_to_hass: no persisted data", self._thermostat.name)

        self.attach_debug_sensor()
        self._restored = True

    def attach_debug_sensor(self) -> None:
        """Create or reuse this handler's sensor on the active global platform."""
        if self._removed or self._controller is None:
            return
        hass = self._thermostat.hass
        domain_data = hass.data.setdefault(DOMAIN, {})
        sensor_key = DATA_DEBUG_SENSORS_PREFIX + (
            self._thermostat.unique_id or DOMAIN
        )
        sensor = domain_data.get(sensor_key)
        if sensor is None:
            sensor = PelletDebugSensor(self._thermostat)
            domain_data[sensor_key] = sensor
        self._debug_sensor = sensor
        sensor.update_from_controller(self._controller)
        callback = domain_data.get(DATA_SENSOR_ADD_CB)
        registered = domain_data.setdefault(DATA_SENSOR_REGISTERED, set())
        uid = self._thermostat.unique_id or DOMAIN
        if callback is not None and uid not in registered:
            callback([sensor], update_before_add=True)
            registered.add(uid)
        elif callback is None and sensor not in domain_data.setdefault(
            "pending_sensors", []
        ):
            domain_data["pending_sensors"].append(sensor)

    def detach_debug_sensor(self) -> None:
        """Forget a sensor entity after its owning platform has been unloaded."""
        hass = self._thermostat.hass
        domain_data = hass.data.setdefault(DOMAIN, {})
        sensor_key = DATA_DEBUG_SENSORS_PREFIX + (
            self._thermostat.unique_id or DOMAIN
        )
        if domain_data.get(sensor_key) is self._debug_sensor:
            domain_data.pop(sensor_key, None)
        domain_data.setdefault(DATA_SENSOR_REGISTERED, set()).discard(
            self._thermostat.unique_id or DOMAIN
        )
        pending = domain_data.get("pending_sensors", [])
        if self._debug_sensor in pending:
            pending.remove(self._debug_sensor)
        self._debug_sensor = None

    async def async_startup(self) -> None:
        """Run startup actions after thermostat initialisation."""
        _LOGGER.debug("%s - async_startup: start", self._thermostat.name)

        async with self._control_lock:
            if not self._restored:
                await self.async_added_to_hass()
            self._observe_underlying()
            await self._publish_current_state(datetime.now(timezone.utc))
        if not self._unsubscribers:
            entities = self._thermostat.entry_infos.get(_CONF_UNDERLYING_LIST) or []
            self._unsubscribers.append(async_track_state_change_event(
                self._thermostat.hass, entities, self._async_observation_changed
            ))
            self._unsubscribers.append(async_track_time_interval(
                self._thermostat.hass, self._async_observation_changed, timedelta(seconds=30)
            ))
            self._unsubscribers.append(self._thermostat.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_shutdown
            ))
        if not self._removed:
            self._thermostat.hass.data.setdefault(DOMAIN, {}).setdefault(
                DATA_HANDLERS, {}
            )[self._thermostat.unique_id] = self

    async def async_reset(self, context: Context | None = None) -> None:
        """Stop the VTherm before clearing and persisting regulation history."""
        async with self._reset_lock:
            if self._removed or self._controller is None or self._store is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="reset_not_ready"
                )
            self._resetting = True
            try:
                async with self._control_lock:
                    if self._scheduler is not None and self._scheduler.is_cycle_running:
                        await self._scheduler.cancel_cycle()
                if str(self._thermostat.vtherm_hvac_mode).lower() != HVAC_MODE_OFF:
                    await self._thermostat.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {
                            "entity_id": self._thermostat.entity_id,
                            "hvac_mode": HVAC_MODE_OFF,
                        },
                        blocking=True,
                        context=context,
                    )
                async with self._control_lock:
                    if self._removed:
                        raise ServiceValidationError(
                            translation_domain=DOMAIN, translation_key="reset_not_ready"
                        )
                    if str(self._thermostat.vtherm_hvac_mode).lower() != HVAC_MODE_OFF:
                        raise HomeAssistantError(
                            translation_domain=DOMAIN, translation_key="reset_not_off"
                        )
                    self._controller.reset()
                    self._last_applied_level_index = None
                    self._last_energy_at = None
                    self._thermostat.update_custom_attributes()
                    self._thermostat.async_write_ha_state()
                    if self._debug_sensor is not None:
                        self._debug_sensor.update_from_controller(self._controller)
                    try:
                        snapshot = self._cache_cycle()
                        async with self._storage_lock:
                            await self._store.async_save(snapshot)
                    except (HomeAssistantError, OSError) as err:
                        raise HomeAssistantError(
                            translation_domain=DOMAIN,
                            translation_key="reset_save_failed",
                        ) from err
            finally:
                self._resetting = False

    def remove(self) -> None:
        """Persist current state and release resources."""
        handlers = self._thermostat.hass.data.get(DOMAIN, {}).get(DATA_HANDLERS, {})
        if (self._controller is not None and not self._stopping
                and handlers.get(self._thermostat.unique_id) in (None, self)):
            self._observe_underlying()
            self._cache_cycle()
        self._removed = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        if handlers.get(self._thermostat.unique_id) is self:
            handlers.pop(self._thermostat.unique_id)
        _LOGGER.debug("%s - remove: start", self._thermostat.name)
        if self._controller is None or self._store is None:
            _LOGGER.debug(
                "%s - remove: skipped (controller/store not ready)",
                self._thermostat.name,
            )
            return

        coro = self._async_save_removed_state()
        hass = self._thermostat.hass
        if hasattr(hass, "async_create_task"):
            hass.async_create_task(coro)
            _LOGGER.debug("%s - remove: persistence task scheduled on hass", self._thermostat.name)
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(coro)
                    _LOGGER.debug(
                        "%s - remove: persistence task scheduled on event loop",
                        self._thermostat.name,
                    )
            except RuntimeError:
                _LOGGER.debug(
                    "%s - remove: no running event loop, persistence deferred",
                    self._thermostat.name,
                )
                return

        # Detach the debug sensor (entity stays in HA showing last known state
        # until the handler restarts).
        self._debug_sensor = None

    async def _async_save_removed_state(self) -> None:
        """Wait for in-flight control before saving the final handler state."""
        async with self._control_lock:
            handlers = self._thermostat.hass.data.get(DOMAIN, {}).get(DATA_HANDLERS, {})
            if handlers.get(self._thermostat.unique_id) not in (None, self):
                return
            if self._store is not None and self._controller is not None:
                await self._save_cycle()

    async def control_heating(
        self,
        timestamp: datetime | None = None,
        force: bool = False,
    ) -> None:
        """Serialize control and skip callbacks during reset or removal."""

        async with self._control_lock:
            if self._resetting or self._removed or self._stopping:
                return
            await self._async_control_heating(timestamp, force)

    async def _async_control_heating(
        self,
        timestamp: datetime | None = None,
        force: bool = False,
    ) -> None:
        """Execute one proportional control iteration."""
        _LOGGER.debug(
            "%s - control_heating: start (force=%s timestamp=%s)",
            self._thermostat.name,
            force,
            timestamp,
        )
        if self._controller is None:
            _LOGGER.warning(
                "%s - control_heating called before init_algorithm, skipping",
                self._thermostat.name,
            )
            return

        if not self._restored:
            await self.async_added_to_hass()
        now = timestamp if timestamp is not None else datetime.now(timezone.utc)
        self._observe_underlying()
        state = self._controller.state
        hvac_mode = self._thermostat.vtherm_hvac_mode
        if hvac_mode is None:
            await self._publish_current_state(now)
            return
        durations_valid = all(
            isinstance(self._opts.get(key), (int, float))
            and not isinstance(self._opts[key], bool)
            and isfinite(self._opts[key]) and 0 <= self._opts[key] <= bound
            for key, bound in ((CONF_MIN_ON_DURATION_MIN, 240),
                               (CONF_MIN_OFF_DURATION_MIN, 240),
                               (CONF_COOLDOWN_DURATION_MIN, 60))
        )
        previous_pending = state.pending
        command = self._controller.calculate_observed(
            target=self._thermostat.target_temperature,
            current=self._thermostat.current_temperature,
            hvac_mode=hvac_mode, now=now,
            slope=self._thermostat.last_temperature_slope,
            allow_turn_on=durations_valid and state.available and state.observed_cycle == "OFF",
        )
        if self._target_error is None and command is not None and self._scheduler is not None:
            state.pending = command
            try:
                if (command == "OFF" and state.off_priority and not state.is_heating
                    and (previous_pending == "ON" or not state.available)):
                    underlyings = self._thermostat.underlyings
                    if len(underlyings) != 1:
                        raise HomeAssistantError("Priority OFF command path is unavailable")
                    await underlyings[0].turn_off()
                elif str(hvac_mode).lower() != HVAC_MODE_OFF:
                    await self._scheduler.start_cycle(hvac_mode, self._controller.on_percent, True)
            except (HomeAssistantError, OSError, ValueError, RuntimeError) as err:
                state.command_error = str(err)
                _LOGGER.exception("%s - pellet command failed", self._thermostat.name)
            finally:
                await self._scheduler.cancel_cycle()
        elif self._scheduler is not None and self._scheduler.is_cycle_running:
            await self._scheduler.cancel_cycle()

        # 3b. Energy accounting: credit one cycle-worth of energy every
        # cycle_min minutes while the stove is heating, replacing the
        # _on_master_cycle_end callback (which no longer fires because the
        # cycle is cancelled immediately above).
        if state.available and self._controller.is_heating:
            cycle_duration_sec = (self._thermostat.cycle_min or 5) * 60
            if self._last_energy_at is None:
                self._last_energy_at = now
            elif (now - self._last_energy_at).total_seconds() >= cycle_duration_sec:
                _fn = getattr(self._thermostat, "incremente_energy", None)
                if callable(_fn):
                    _LOGGER.debug(
                        "%s - control_heating: crediting energy (%.0fs elapsed)",
                        self._thermostat.name,
                        (now - self._last_energy_at).total_seconds(),
                    )
                    _fn()
                self._last_energy_at = now
        else:
            self._last_energy_at = None

        # 4. Apply power level on the underlying climate entity (optional).
        if (not self._opts[CONF_DRY_CONTACT] and state.available and state.pending != "OFF"
            and self._opts.get(CONF_POWER_CONTROL_ENABLED) and self._controller.is_heating):
            _LOGGER.debug(
                "%s - control_heating: power control active while heating, applying level",
                self._thermostat.name,
            )
            await self._apply_power_level()
        else:
            _LOGGER.debug(
                "%s - control_heating: power level application skipped "
                "(enabled=%s is_heating=%s)",
                self._thermostat.name,
                self._opts.get(CONF_POWER_CONTROL_ENABLED),
                self._controller.is_heating,
            )

        await self._publish_current_state(now)

        _LOGGER.debug(
            "%s - control_heating: on_percent=%.1f reason=%s hvac_mode=%s",
            self._thermostat.name,
            self._controller.on_percent,
            self._controller.last_reason,
            hvac_mode,
        )

    def _physical_heating_state(self) -> bool | None:
        """Return the observed family without asserting physical heat."""
        try:
            entity_id = validate_target(self._thermostat.entry_infos, self._opts)
        except ValueError:
            return None
        cycle, _phase = observe_target(
            self._thermostat.hass.states.get(entity_id), self._opts[CONF_DRY_CONTACT]
        )
        return None if cycle is None else cycle == "ON"

    def _target_identity(self) -> dict:
        return {"entities": list(self._thermostat.entry_infos.get(_CONF_UNDERLYING_LIST) or []),
                "dry_contact": self._opts[CONF_DRY_CONTACT]}

    def _observe_underlying(self) -> None:
        if self._controller is None:
            return
        identity = self._target_identity()
        if identity != self._bound_target:
            self._controller.reset()
            self._controller.state.resume_reason = "invalid"
            self._last_applied_level_index = None
            self._last_energy_at = None
            self._bound_target = identity
        try:
            entity_id = validate_target(self._thermostat.entry_infos, self._opts)
        except ValueError as err:
            self._target_error = str(err)
            self._controller.state.observe(None, None, monotonic())
            return
        self._target_error = None
        on_state, off_state = "on", "off"
        underlyings = self._thermostat.underlyings
        if self._opts[CONF_DRY_CONTACT] and len(underlyings) == 1:
            try:
                on_state = underlyings[0].build_command(use_on=True)[2]
                off_state = underlyings[0].build_command(use_on=False)[2]
                if {on_state, off_state} != {"on", "off"}:
                    raise ValueError("invalid_command_state_contract")
            except (TypeError, ValueError, IndexError) as err:
                self._target_error = str(err)
                self._controller.state.observe(None, None, monotonic())
                return
        cycle, phase = observe_target(
            self._thermostat.hass.states.get(entity_id), self._opts[CONF_DRY_CONTACT],
            on_state=on_state, off_state=off_state,
        )
        self._controller.state.observe(cycle, phase, monotonic())

    async def _async_observation_changed(self, _event: Any) -> None:
        await self.control_heating()

    async def _async_shutdown(self, _event: Any) -> None:
        async with self._control_lock:
            self._stopping = True
            self._observe_underlying()
            await self._save_cycle()

    async def _save_cycle(self) -> None:
        if self._store is None or self._controller is None:
            return
        snapshot = self._cache_cycle()
        try:
            async with self._storage_lock:
                await self._store.async_save(snapshot)
        except (HomeAssistantError, OSError, ValueError) as err:
            self._storage_error = str(err)
            _LOGGER.exception("%s - cycle persistence failed", self._thermostat.name)

    def _cache_cycle(self) -> dict:
        snapshot = {**self._controller.save_state(), "target": self._target_identity()}
        self._thermostat.hass.data.setdefault(DOMAIN, {}).setdefault(
            "cycle_snapshots", {}
        )[self._thermostat.unique_id] = deepcopy(snapshot)
        return snapshot

    async def _publish_current_state(self, now: datetime) -> None:
        """Publish and persist the current controller snapshot."""
        if self._controller is None:
            return
        self._thermostat.update_custom_attributes()
        self._thermostat.async_write_ha_state()
        await self._save_cycle()
        if self._debug_sensor is not None:
            self._debug_sensor.update_from_controller(
                self._controller, now, diagnostics={
                    "dry_contact": self._opts[CONF_DRY_CONTACT],
                    "target_error": self._target_error,
                    "storage_error": self._storage_error,
                },
            )

    async def on_state_changed(self, changed: bool = True) -> None:
        """React to a thermostat state change."""
        _LOGGER.debug("%s - on_state_changed: start (changed=%s)", self._thermostat.name, changed)
        await self.control_heating()

    def on_scheduler_ready(self, scheduler: "InterfaceCycleScheduler") -> None:
        """Bind the handler to the cycle scheduler once it is available."""
        _LOGGER.debug("%s - on_scheduler_ready: start", self._thermostat.name)
        self._scheduler = scheduler
        scheduler.register_cycle_start_callback(self._on_cycle_start)
        scheduler.register_cycle_end_callback(self._on_cycle_end)
        _LOGGER.debug(
            "%s - on_scheduler_ready: scheduler bound",
            self._thermostat.name,
        )

    def should_publish_intermediate(self) -> bool:
        """Return True when VT may publish the current intermediate state."""
        _LOGGER.debug(
            "%s - should_publish_intermediate: returning %s",
            self._thermostat.name,
            self._should_publish_intermediate,
        )
        return self._should_publish_intermediate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _apply_power_level(self) -> None:
        """Apply the current power level to the underlying climate entities.

        Skipped when the level has not changed since the last call (anti-spam).
        """
        _LOGGER.debug("%s - _apply_power_level: start", self._thermostat.name)
        if self._controller is None:
            _LOGGER.debug("%s - _apply_power_level: skipped (no controller)", self._thermostat.name)
            return

        level_index = self._controller.current_level_index
        level_value = self._controller.current_level_value

        if level_value is None:
            _LOGGER.debug("%s - _apply_power_level: skipped (no level value)", self._thermostat.name)
            return

        if level_index == self._last_applied_level_index:
            _LOGGER.debug(
                "%s - _apply_power_level: skipped (unchanged level index=%s)",
                self._thermostat.name,
                level_index,
            )
            return  # Already at the correct level — no service call needed.

        attribute = self._opts.get(CONF_POWER_CONTROL_ATTRIBUTE, "fan_mode")
        underlying_list = self._thermostat.entry_infos.get(_CONF_UNDERLYING_LIST) or []
        climate_entities = [
            eid for eid in underlying_list if eid.startswith("climate.")
        ]

        _LOGGER.debug(
            "%s - _apply_power_level: applying %s=%s to %s entities",
            self._thermostat.name,
            attribute,
            level_value,
            len(climate_entities),
        )

        for entity_id in climate_entities:
            try:
                await self._thermostat.hass.services.async_call(
                    "climate",
                    f"set_{attribute}",
                    {"entity_id": entity_id, attribute: level_value},
                    blocking=False,
                )
                _LOGGER.debug(
                    "%s - _apply_power_level: set %s=%s on %s",
                    self._thermostat.name,
                    attribute,
                    level_value,
                    entity_id,
                )
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "%s - _apply_power_level: failed to set %s=%s on %s: %s",
                    self._thermostat.name,
                    attribute,
                    level_value,
                    entity_id,
                    exc,
                )

        self._last_applied_level_index = level_index
        _LOGGER.debug(
            "%s - _apply_power_level: completed (last_applied_level_index=%s)",
            self._thermostat.name,
            self._last_applied_level_index,
        )

    async def _on_cycle_start(self, *_args: Any, **_kwargs: Any) -> None:
        """Callback at the start of each cycle (v0.1: no-op)."""
        _LOGGER.debug("%s - _on_cycle_start: callback invoked", self._thermostat.name)

    async def _on_cycle_end(self, *_args: Any, **_kwargs: Any) -> None:
        """Callback at the end of each cycle (v0.1: no-op)."""
        _LOGGER.debug("%s - _on_cycle_end: callback invoked", self._thermostat.name)
