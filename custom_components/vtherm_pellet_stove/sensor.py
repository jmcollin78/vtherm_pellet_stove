"""Entité capteur de débogage pour vtherm_pellet_stove.

Expose l'état interne du ``PelletRegulationController`` sous forme d'une
entité ``sensor`` de diagnostic, mise à jour à chaque cycle de régulation.

Phases exposées comme valeur d'état : ``off``, ``igniting``, ``burning``,
``cooldown``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from vtherm_api.log_collector import get_vtherm_logger

from .const import DOMAIN, DATA_SENSOR_ADD_CB

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceThermostatRuntime
    from .pellet.controller import PelletRegulationController

_LOGGER = get_vtherm_logger(__name__)

# ---------------------------------------------------------------------------
# HA platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Enregistre le callback ``async_add_entities`` pour création dynamique.

    Les entités capteur ne sont pas créées ici mais depuis le handler au
    moment où un VTherm utilisant ``pellet_regulation`` démarre.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[DATA_SENSOR_ADD_CB] = async_add_entities

    # Ajouter les capteurs en attente (handlers démarrés avant le setup)
    pending: list[PelletDebugSensor] = domain_data.pop("pending_sensors", [])
    if pending:
        _LOGGER.debug("Ajout de %d capteur(s) pellet en attente", len(pending))
        async_add_entities(pending, update_before_add=True)


# ---------------------------------------------------------------------------
# Sensor entity
# ---------------------------------------------------------------------------


class PelletDebugSensor(SensorEntity):
    """Capteur de débogage exposant l'état interne de la régulation pellet.

    Utilisé par le ``PelletRegulationHandler`` pour transmettre l'état du
    ``PelletRegulationController`` à Home Assistant sous forme d'une entité
    persistée dans le registre.
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "pellet_debug"
    _attr_has_entity_name = True

    def __init__(
        self,
        thermostat: "InterfaceThermostatRuntime",
    ) -> None:
        self._thermostat = thermostat
        self._phase: str = "unknown"
        self._attributes: dict[str, Any] = {}

        vtherm_uid = thermostat.unique_id
        self._attr_unique_id = f"{DOMAIN}_{vtherm_uid}_debug"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{DOMAIN}_{vtherm_uid}")},
            name=f"Pellet Stove — {thermostat.name}",
            manufacturer="VTherm Pellet Stove",
            model="Pellet Regulation",
        )

    # ------------------------------------------------------------------
    # Mise à jour depuis le handler
    # ------------------------------------------------------------------

    def update_from_controller(
        self,
        controller: "PelletRegulationController",
        now: datetime | None = None,
    ) -> None:
        """Met à jour l'état du capteur à partir du contrôleur.

        Appelé par le handler après chaque appel à ``calculate()``.
        Déclenche ``async_write_ha_state()`` si l'entité est déjà liée à HA.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        attrs = controller.get_debug_attributes(now)
        self._phase = attrs.get("phase", "unknown")
        self._attributes = attrs

        if self.hass is not None:
            self.async_write_ha_state()

    # ------------------------------------------------------------------
    # SensorEntity contract
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> str:
        """Phase courante du poêle."""
        return self._phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributs de débogage complets."""
        return dict(self._attributes)
