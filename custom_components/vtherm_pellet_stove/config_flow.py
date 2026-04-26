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
    CONF_POWER_LEVELS,
    CONF_SAFETY_ROOM_TEMP,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)


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


def build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the per-thermostat schema (entity selector + options)."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        )
    }
    schema.update(build_options_schema(defaults).schema)
    return vol.Schema(schema)


class PelletStoveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage Pellet Stove plugin config entries."""

    VERSION = 1

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
        """Handle the per-thermostat entry."""
        if user_input is not None:
            entity_id = user_input.get(CONF_TARGET_VTHERM)
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(entity_id)
            if reg_entry is None or reg_entry.unique_id is None:
                return self.async_show_form(
                    step_id="thermostat",
                    data_schema=build_user_schema(dict(DEFAULT_OPTIONS)),
                    errors={CONF_TARGET_VTHERM: "invalid_entity"},
                )

            target_unique_id = reg_entry.unique_id
            await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
            self._abort_if_unique_id_configured()

            data = dict(user_input)
            data[CONF_TARGET_VTHERM] = target_unique_id
            state = self.hass.states.get(entity_id)
            title = state.name if state is not None else entity_id
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="thermostat",
            data_schema=build_user_schema(dict(DEFAULT_OPTIONS)),
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
        return self.async_show_form(
            step_id="init",
            data_schema=build_options_schema(defaults),
        )
