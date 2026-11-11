"""Config flow for vtherm_pellet_stove."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

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
    CONF_SAFETY_ROOM_TEMP,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)

_VTHERM_DOMAIN = "versatile_thermostat"
_CONF_UNDERLYING_LIST = "underlying_entity_ids"
_DRY_CONTACT_DOMAINS = {"switch", "input_boolean"}


def _resolve_underlying_domain_from_entry(hass: Any, entry_id: str) -> str | None:
    """Resolve one VTherm config entry's underlying domain."""
    vtherm_entry = hass.config_entries.async_get_entry(entry_id)
    if vtherm_entry is None or vtherm_entry.domain != _VTHERM_DOMAIN:
        return None

    underlying_entities = vtherm_entry.data.get(_CONF_UNDERLYING_LIST)
    if not isinstance(underlying_entities, list) or len(underlying_entities) != 1:
        return None

    entity_id = underlying_entities[0]
    if not isinstance(entity_id, str):
        return None
    domain, separator, object_id = entity_id.partition(".")
    if not separator or not domain or not object_id:
        return None
    return domain if domain in {CLIMATE_DOMAIN} | _DRY_CONTACT_DOMAINS else None


def resolve_underlying_domain(hass: Any, target_entity_id: str) -> str | None:
    """Resolve a climate VTherm's configured underlying domain."""
    target = er.async_get(hass).async_get(target_entity_id)
    if target is None or target.platform != _VTHERM_DOMAIN:
        return None
    return _resolve_underlying_domain_from_entry(hass, target.config_entry_id)


def resolve_underlying_domain_by_unique_id(hass: Any, unique_id: str) -> str | None:
    """Resolve a VTherm's configured underlying domain from its unique ID."""
    return _resolve_underlying_domain_from_entry(hass, unique_id)


def build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the shared options schema from the given defaults."""
    return vol.Schema(
        {
            # -- Hysteresis --------------------------------------------------
            vol.Optional(
                CONF_HYSTERESIS_ON,
                default=defaults.get(CONF_HYSTERESIS_ON),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=5.0, step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_HYSTERESIS_OFF,
                default=defaults.get(CONF_HYSTERESIS_OFF),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=5.0, step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MIN_ON_PERCENT,
                default=defaults.get(CONF_MIN_ON_PERCENT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=1.0, step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MAX_ON_PERCENT,
                default=defaults.get(CONF_MAX_ON_PERCENT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=1.0, step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            # -- Pellet guard-rails ------------------------------------------
            vol.Optional(
                CONF_MIN_ON_DURATION_MIN,
                default=defaults.get(CONF_MIN_ON_DURATION_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=240, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MIN_OFF_DURATION_MIN,
                default=defaults.get(CONF_MIN_OFF_DURATION_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=240, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_COOLDOWN_DURATION_MIN,
                default=defaults.get(CONF_COOLDOWN_DURATION_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=60, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_SAFETY_ROOM_TEMP,
                default=defaults.get(CONF_SAFETY_ROOM_TEMP),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=15.0, max=40.0, step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            # -- Power level control -----------------------------------------
            vol.Optional(
                CONF_POWER_CONTROL_ENABLED,
                default=defaults.get(CONF_POWER_CONTROL_ENABLED),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_POWER_CONTROL_ATTRIBUTE,
                default=defaults.get(CONF_POWER_CONTROL_ATTRIBUTE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["fan_mode", "preset_mode"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_POWER_DEFAULT_LEVEL_INDEX,
                default=defaults.get(CONF_POWER_DEFAULT_LEVEL_INDEX),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=10, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_POWER_BOOST_ENABLED,
                default=defaults.get(CONF_POWER_BOOST_ENABLED),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_POWER_BOOST_DURATION_MIN,
                default=defaults.get(CONF_POWER_BOOST_DURATION_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=120, step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def build_target_schema() -> vol.Schema:
    """Build the per-thermostat target selector schema."""
    return vol.Schema(
        {
            vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
            )
        }
    )


class PelletStoveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage Pellet Stove plugin config entries."""

    VERSION = 1

    def is_matching(self, other_flow: "PelletStoveConfigFlow") -> bool:
        """Return True if the other flow targets the same domain entry."""
        return other_flow.unique_id == self.unique_id

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create the global defaults entry on first install, then per-thermostat."""
        del user_input
        if not self._async_current_entries():
            # No existing entry: create the global defaults entry automatically.
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Pellet Stove defaults",
                data=dict(DEFAULT_OPTIONS),
            )

        return await self.async_step_thermostat()

    async def async_step_global(self, user_input: dict[str, Any] | None = None):
        """Handle the global defaults entry explicitly."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Pellet Stove defaults", data=user_input)

        return self.async_show_form(
            step_id="global",
            data_schema=build_options_schema(dict(DEFAULT_OPTIONS)),
        )

    async def async_step_thermostat(self, user_input: dict[str, Any] | None = None):
        """Select the target VTherm before presenting its pellet options."""
        if user_input is not None:
            entity_id = user_input.get(CONF_TARGET_VTHERM)
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(entity_id)
            if reg_entry is None or reg_entry.unique_id is None:
                return self.async_show_form(
                    step_id="thermostat",
                    data_schema=build_target_schema(),
                    errors={CONF_TARGET_VTHERM: "invalid_entity"},
                )

            target_unique_id = reg_entry.unique_id
            await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
            self._abort_if_unique_id_configured()
            self.context[CONF_TARGET_VTHERM] = target_unique_id
            self.context["target_vtherm_entity_id"] = entity_id
            return await self.async_step_thermostat_options()

        return self.async_show_form(
            step_id="thermostat",
            data_schema=build_target_schema(),
        )

    async def async_step_thermostat_options(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure and save options for the selected VTherm."""
        target_unique_id = self.context.get(CONF_TARGET_VTHERM)
        entity_id = self.context.get("target_vtherm_entity_id")
        if target_unique_id is None or entity_id is None:
            return self.async_abort(reason="invalid_target")

        if user_input is not None:
            data = {**user_input, CONF_TARGET_VTHERM: target_unique_id}
            state = self.hass.states.get(entity_id)
            title = state.name if state is not None else entity_id
            return self.async_create_entry(title=title, data=data)

        switch_underlying = (
            resolve_underlying_domain(self.hass, entity_id) in _DRY_CONTACT_DOMAINS
        )
        return self.async_show_form(
            step_id=(
                "thermostat_options_switch"
                if switch_underlying
                else "thermostat_options"
            ),
            data_schema=build_options_schema(dict(DEFAULT_OPTIONS)),
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Allow reconfiguring an existing entry.

        Works for both the global-defaults entry and per-thermostat entries.
        On submit the entry's data is updated (preserving ``CONF_TARGET_VTHERM``
        when present) and any stale ``entry.options`` are cleared so that
        ``_resolve_options`` always reads the freshly-saved values.
        The entry is then reloaded, which in turn reloads the affected VTherm
        thermostat(s) via ``async_setup_entry`` → ``_reload_pellet_vtherms``.
        """
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            # Merge new values into data while keeping CONF_TARGET_VTHERM (if
            # present) so per-thermostat entries still target the right VTherm.
            # Clearing options ensures _resolve_options falls back to data.
            new_data = {**entry.data, **user_input}
            return self.async_update_reload_and_abort(
                entry,
                data=new_data,
                options={},
            )

        defaults = dict(DEFAULT_OPTIONS)
        defaults.update(entry.options or entry.data)
        switch_underlying = (
            resolve_underlying_domain_by_unique_id(
                self.hass, entry.data.get(CONF_TARGET_VTHERM, "")
            )
            in _DRY_CONTACT_DOMAINS
        )
        return self.async_show_form(
            step_id="reconfigure_switch" if switch_underlying else "reconfigure",
            data_schema=build_options_schema(defaults),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return PelletStoveOptionsFlow(config_entry)


class PelletStoveOptionsFlow(OptionsFlow):
    """Edit Pellet Stove plugin options."""

    def __init__(self, config_entry) -> None:
        """Store the config entry being edited."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle the options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = dict(DEFAULT_OPTIONS)
        defaults.update(self._config_entry.options or self._config_entry.data)
        switch_underlying = (
            resolve_underlying_domain_by_unique_id(
                self.hass,
                self._config_entry.data.get(CONF_TARGET_VTHERM, ""),
            )
            in _DRY_CONTACT_DOMAINS
        )
        return self.async_show_form(
            step_id="init_switch" if switch_underlying else "init",
            data_schema=build_options_schema(defaults),
        )
