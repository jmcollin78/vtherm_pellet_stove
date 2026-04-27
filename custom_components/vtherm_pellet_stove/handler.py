"""Pellet stove regulation handler — Sprint 2 full implementation."""

from __future__ import annotations

import logging
import asyncio

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    CONF_COOLDOWN_DURATION_MIN,
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
    DEFAULT_OPTIONS,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .pellet.controller import PelletRegulationController

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceCycleScheduler, InterfaceThermostatRuntime

_LOGGER = logging.getLogger(__name__)

# Key from versatile_thermostat const.py for the list of underlying entity IDs.
_CONF_UNDERLYING_LIST = "underlying_entity_ids"


def _resolve_options(hass: Any, vtherm_uid: str | None) -> dict[str, Any]:
    """Return the effective options for a given VTherm unique_id.

    Priority: per-thermostat plugin entry > global defaults entry > DEFAULT_OPTIONS.
    """
    opts: dict[str, Any] = dict(DEFAULT_OPTIONS)

    global_entry = None
    per_entry = None

    for entry in hass.config_entries.async_entries(DOMAIN):
        target = entry.data.get(CONF_TARGET_VTHERM)
        if target is None and entry.unique_id == DOMAIN:
            global_entry = entry
        elif target == vtherm_uid:
            per_entry = entry

    if global_entry is not None:
        opts.update(dict(global_entry.options or global_entry.data))

    if per_entry is not None:
        opts.update(dict(per_entry.options or per_entry.data))

    return opts


class PelletRegulationHandler:
    """Handler implementing the VT external proportional algorithm lifecycle."""

    def __init__(self, thermostat: "InterfaceThermostatRuntime") -> None:
        """Bind the handler to a VT thermostat runtime object."""
        self._thermostat = thermostat
        self._scheduler: "InterfaceCycleScheduler | None" = None
        self._should_publish_intermediate: bool = True
        self._controller: PelletRegulationController | None = None
        self._store: Store | None = None
        self._opts: dict[str, Any] = dict(DEFAULT_OPTIONS)
        self._last_applied_level_index: int | None = None

    # ------------------------------------------------------------------
    # InterfacePropAlgorithmHandler contract
    # ------------------------------------------------------------------

    def init_algorithm(self) -> None:
        """Initialise the runtime algorithm state."""
        hass = self._thermostat.hass
        vtherm_uid = self._thermostat.unique_id

        self._opts = _resolve_options(hass, vtherm_uid)

        self._controller = PelletRegulationController(
            hysteresis_on=float(self._opts[CONF_HYSTERESIS_ON]),
            hysteresis_off=float(self._opts[CONF_HYSTERESIS_OFF]),
            min_on_percent=float(self._opts[CONF_MIN_ON_PERCENT]),
            max_on_percent=float(self._opts[CONF_MAX_ON_PERCENT]),
            min_on_duration_min=int(self._opts[CONF_MIN_ON_DURATION_MIN]),
            min_off_duration_min=int(self._opts[CONF_MIN_OFF_DURATION_MIN]),
            cooldown_duration_min=int(self._opts[CONF_COOLDOWN_DURATION_MIN]),
            safety_room_temp=float(self._opts[CONF_SAFETY_ROOM_TEMP]),
            power_control_enabled=bool(self._opts[CONF_POWER_CONTROL_ENABLED]),
            power_levels=list(self._opts.get(CONF_POWER_LEVELS) or []) or None,
            power_default_level_index=int(self._opts[CONF_POWER_DEFAULT_LEVEL_INDEX]),
            power_boost_enabled=bool(self._opts[CONF_POWER_BOOST_ENABLED]),
            power_boost_duration_min=int(self._opts[CONF_POWER_BOOST_DURATION_MIN]),
        )

        # Expose the controller as prop_algorithm so VTherm safety manager
        # can read on_percent at any time.
        self._thermostat.prop_algorithm = self._controller

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

    async def async_added_to_hass(self) -> None:
        """Restore persistent state when the thermostat entity is added to HA."""
        if self._controller is None or self._store is None:
            return

        data = await self._store.async_load()
        if data:
            self._controller.restore_state(data)
            _LOGGER.debug(
                "%s - async_added_to_hass: restored state is_heating=%s reason=%s",
                self._thermostat.name,
                self._controller.is_heating,
                self._controller.last_reason,
            )

    async def async_startup(self) -> None:
        """Run startup actions after thermostat initialisation."""
        await self.on_state_changed(True)

    def remove(self) -> None:
        """Persist current state and release resources."""
        if self._controller is None or self._store is None:
            return

        coro = self._store.async_save(self._controller.save_state())
        hass = self._thermostat.hass
        if hasattr(hass, "async_create_task"):
            hass.async_create_task(coro)
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(coro)
            except RuntimeError:
                pass

    async def control_heating(
        self,
        timestamp: datetime | None = None,
        force: bool = False,
    ) -> None:
        """Execute one proportional control iteration."""
        if self._controller is None:
            _LOGGER.warning(
                "%s - control_heating called before init_algorithm, skipping",
                self._thermostat.name,
            )
            return

        now = timestamp if timestamp is not None else datetime.now(timezone.utc)

        target = self._thermostat.target_temperature
        current = self._thermostat.current_temperature
        slope = self._thermostat.last_temperature_slope
        hvac_mode = self._thermostat.vtherm_hvac_mode or "off"

        if target is None:
            _LOGGER.debug(
                "%s - control_heating: no target temperature, skipping",
                self._thermostat.name,
            )
            return

        # 1. Compute on_percent via the pellet controller.
        on_percent = self._controller.calculate(
            target_temp=target,
            current_temp=current,
            slope=slope,
            hvac_mode=hvac_mode,
            now=now,
        )

        # 2. Keep prop_algorithm reference current (VTherm reads it elsewhere).
        self._thermostat.prop_algorithm = self._controller

        # 3. Forward result to the cycle scheduler.
        if self._scheduler is not None:
            await self._scheduler.start_cycle(hvac_mode, on_percent, force)
        else:
            _LOGGER.debug(
                "%s - control_heating: scheduler not yet available",
                self._thermostat.name,
            )

        # 4. Apply power level on the underlying climate entity (optional).
        if self._opts.get(CONF_POWER_CONTROL_ENABLED) and self._controller.is_heating:
            await self._apply_power_level()

        # 5. Publish HA state.
        self._thermostat.update_custom_attributes()
        self._thermostat.async_write_ha_state()

        # 6. Persist controller state.
        if self._store is not None:
            await self._store.async_save(self._controller.save_state())

        _LOGGER.debug(
            "%s - control_heating: on_percent=%.1f reason=%s hvac_mode=%s",
            self._thermostat.name,
            on_percent,
            self._controller.last_reason,
            hvac_mode,
        )

    async def on_state_changed(self, changed: bool = True) -> None:
        """React to a thermostat state change."""
        _LOGGER.debug(
            "%s - on_state_changed changed=%s",
            self._thermostat.name,
            changed,
        )
        if changed:
            await self.control_heating()

    def on_scheduler_ready(self, scheduler: "InterfaceCycleScheduler") -> None:
        """Bind the handler to the cycle scheduler once it is available."""
        self._scheduler = scheduler
        scheduler.register_cycle_start_callback(self._on_cycle_start)
        scheduler.register_cycle_end_callback(self._on_cycle_end)
        _LOGGER.debug(
            "%s - on_scheduler_ready: scheduler bound",
            self._thermostat.name,
        )

    def should_publish_intermediate(self) -> bool:
        """Return True when VT may publish the current intermediate state."""
        return self._should_publish_intermediate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _apply_power_level(self) -> None:
        """Apply the current power level to the underlying climate entities.

        Skipped when the level has not changed since the last call (anti-spam).
        """
        if self._controller is None:
            return

        level_index = self._controller.current_level_index
        level_value = self._controller.current_level_value

        if level_value is None:
            return

        if level_index == self._last_applied_level_index:
            return  # Already at the correct level — no service call needed.

        attribute = self._opts.get(CONF_POWER_CONTROL_ATTRIBUTE, "fan_mode")
        underlying_list = self._thermostat.entry_infos.get(_CONF_UNDERLYING_LIST) or []
        climate_entities = [
            eid for eid in underlying_list if eid.startswith("climate.")
        ]

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

    async def _on_cycle_start(self, *_args: Any, **_kwargs: Any) -> None:
        """Callback at the start of each cycle (v0.1: no-op)."""

    async def _on_cycle_end(self, *_args: Any, **_kwargs: Any) -> None:
        """Callback at the end of each cycle (v0.1: no-op)."""
