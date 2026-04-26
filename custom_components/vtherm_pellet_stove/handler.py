"""Pellet stove regulation handler — lifecycle stub for Sprint 0.

The full algorithm implementation is delivered in Sprint 1/2. This stub
satisfies the InterfacePropAlgorithmHandler contract so the plugin can
already be registered in VThermAPI and selected from the VTherm config flow.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .const import DOMAIN

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceCycleScheduler, InterfaceThermostatRuntime

_LOGGER = logging.getLogger(__name__)


class PelletRegulationHandler:
    """Handler implementing the VT external proportional algorithm lifecycle.

    Sprint 0: all methods are no-ops or minimal stubs. Replaced in Sprint 1/2
    by the full hysteresis + guard-rail + power-mapper logic.
    """

    def __init__(self, thermostat: "InterfaceThermostatRuntime") -> None:
        """Bind the handler to a VT thermostat runtime object."""
        self._thermostat = thermostat
        self._scheduler: "InterfaceCycleScheduler | None" = None
        self._should_publish_intermediate: bool = True

    # ------------------------------------------------------------------
    # InterfacePropAlgorithmHandler contract
    # ------------------------------------------------------------------

    def init_algorithm(self) -> None:
        """Initialise the runtime algorithm state.

        Sprint 1: instantiate PelletRegulationController and Store.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.init_algorithm (stub)",
            self._thermostat.name,
        )

    async def async_added_to_hass(self) -> None:
        """Restore persistent state when the thermostat entity is added to HA.

        Sprint 1: restore PelletState from Store.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.async_added_to_hass (stub)",
            self._thermostat.name,
        )

    async def async_startup(self) -> None:
        """Run startup actions after thermostat initialisation.

        Sprint 1: trigger on_state_changed(True) to align with current state.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.async_startup (stub)",
            self._thermostat.name,
        )

    def remove(self) -> None:
        """Release resources held by the handler.

        Sprint 1: persist current PelletState to Store.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.remove (stub)",
            self._thermostat.name,
        )

    async def control_heating(
        self,
        timestamp: datetime | None = None,
        force: bool = False,
    ) -> None:
        """Execute one proportional control iteration.

        Sprint 2: call PelletRegulationController.calculate(), forward result
        to cycle_scheduler.start_cycle(), apply fan_mode/preset_mode on the
        underlying climate entity, update_custom_attributes, async_write_ha_state.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.control_heating (stub) force=%s",
            self._thermostat.name,
            force,
        )

    async def on_state_changed(self, changed: bool = True) -> None:
        """React to a thermostat state change.

        VTherm calls this without argument; the default value ensures compatibility.
        Sprint 2: request a fresh control_heating iteration.
        """
        _LOGGER.debug(
            "%s - PelletRegulationHandler.on_state_changed changed=%s (stub)",
            self._thermostat.name,
            changed,
        )

    def on_scheduler_ready(self, scheduler: "InterfaceCycleScheduler") -> None:
        """Bind the handler to the cycle scheduler once it is available.

        Sprint 2: register cycle_start and cycle_end callbacks.
        """
        self._scheduler = scheduler
        _LOGGER.debug(
            "%s - PelletRegulationHandler.on_scheduler_ready (stub)",
            self._thermostat.name,
        )

    def should_publish_intermediate(self) -> bool:
        """Return True when VT may publish the current intermediate state."""
        return self._should_publish_intermediate
