"""Factory for the pellet_regulation proportional algorithm plugin."""

from __future__ import annotations

from vtherm_api.interfaces import (
    InterfacePropAlgorithmFactory,
    InterfacePropAlgorithmHandler,
    InterfaceThermostatRuntime,
)

from .const import PROP_FUNCTION_PELLET_REGULATION
from .handler import PelletRegulationHandler


class PelletRegulationFactory(InterfacePropAlgorithmFactory):
    """Create PelletRegulation handlers for VT runtime thermostats."""

    @property
    def name(self) -> str:
        """Return the pellet regulation proportional function identifier."""
        return PROP_FUNCTION_PELLET_REGULATION

    def create(
        self,
        thermostat: InterfaceThermostatRuntime,
    ) -> InterfacePropAlgorithmHandler:
        """Create a handler bound to the runtime thermostat."""
        return PelletRegulationHandler(thermostat)
