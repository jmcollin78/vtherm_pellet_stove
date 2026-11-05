"""Shared validation and observation of the single pellet underlying."""

from __future__ import annotations

from typing import Any

from .const import CONF_BISTABLE_CONFIRMED, CONF_DRY_CONTACT


def validate_target(infos: dict, options: dict) -> str:
    """Return the unique entity ID or reject a structurally invalid target."""
    entities = infos.get("underlying_entity_ids") or []
    if not isinstance(entities, (list, tuple)) or len(entities) != 1:
        raise ValueError("single_underlying_required")
    entity_id = entities[0]
    if not isinstance(entity_id, str):
        raise ValueError("invalid_underlying")
    if options.get(CONF_DRY_CONTACT) is True:
        if (
            infos.get("thermostat_type") != "thermostat_over_switch"
            or not entity_id.startswith("switch.")
            or options.get(CONF_BISTABLE_CONFIRMED) is not True
        ):
            raise ValueError("invalid_dry_contact")
    elif not entity_id.startswith("climate."):
        raise ValueError("invalid_underlying")
    return entity_id


def observe_target(
    state: Any, dry_contact: bool, *, on_state: str = "on", off_state: str = "off"
) -> tuple[str | None, str | None]:
    """Classify exposed states without substituting a requested HVAC mode."""
    if state is None:
        return None, None
    if state.state in ("unknown", "unavailable"):
        return None, state.state
    if dry_contact:
        return ({on_state: "ON", off_state: "OFF"}.get(state.state), state.state)
    phase = state.attributes.get("burner_status")
    if phase in ("Ignition starting", "Flame On"):
        return "ON", phase
    if phase in ("Off", "Cooling down", "Cooldown", "Cleaning", "Eco idle", "Eco Idle"):
        return "OFF", "Eco idle" if phase == "Eco Idle" else phase
    return None, phase