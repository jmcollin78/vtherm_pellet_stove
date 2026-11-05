"""Config flow for vtherm_pellet_stove."""

from __future__ import annotations

from typing import Any, Callable

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

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
    CONF_SAFETY_ROOM_TEMP,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .target import validate_target


def build_options_schema(defaults: dict[str, Any], *, dry_contact: bool = False) -> vol.Schema:
    """Build the shared options schema from the given defaults."""
    schema = vol.Schema(
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
    if dry_contact:
        fields = {key: value for key, value in schema.schema.items()
                  if not str(key.schema).startswith("power_")}
        fields[vol.Required(CONF_BISTABLE_CONFIRMED, default=False)] = selector.BooleanSelector()
        return vol.Schema(fields)
    return schema


def build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the per-thermostat schema (entity selector + options)."""
    del defaults
    schema: dict[Any, Any] = {
        vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        )
    }
    schema[vol.Required(CONF_DRY_CONTACT, default=False)] = selector.BooleanSelector()
    return vol.Schema(schema)


def target_infos(hass, unique_id: str) -> dict:
    """Resolve a VTherm config entry without selecting an arbitrary entity."""
    for entry in hass.config_entries.async_entries("versatile_thermostat"):
        if entry.entry_id == unique_id or entry.unique_id == unique_id:
            return {**entry.data, **entry.options}
    raise ValueError("invalid_entity")


class _LocalSettingsFlow:
    """Share local mode selection, warning and validation between all flows."""

    hass: HomeAssistant
    async_show_form: Callable[..., Any]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_settings: dict[str, Any] = {}
        self._settings_uid: str = ""
        self._settings_title: str = ""
        self._edit_entry = None

    def _finish_settings(self, settings: dict[str, Any]):
        raise NotImplementedError

    async def async_step_mode(self, user_input=None):
        if user_input is not None:
            self._pending_settings[CONF_DRY_CONTACT] = user_input.get(CONF_DRY_CONTACT) is True
            return await self._show_local_settings()
        return self.async_show_form(
            step_id="mode", data_schema=vol.Schema({
                vol.Required(CONF_DRY_CONTACT, default=self._pending_settings.get(CONF_DRY_CONTACT, False)):
                    selector.BooleanSelector(),
            }),
        )

    async def _show_local_settings(self, user_input=None):
        dry = self._pending_settings.get(CONF_DRY_CONTACT) is True
        step_id = "dry_contact" if dry else "climate"
        errors = {}
        if user_input is not None:
            settings = {**self._pending_settings, **user_input}
            try:
                validate_target(target_infos(self.hass, self._settings_uid), settings)
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return self._finish_settings(settings)
        return self.async_show_form(
            step_id=step_id,
            data_schema=build_options_schema(self._pending_settings, dry_contact=dry),
            errors=errors,
        )

    async def async_step_dry_contact(self, user_input=None):
        return await self._show_local_settings(user_input)

    async def async_step_climate(self, user_input=None):
        return await self._show_local_settings(user_input)


class PelletStoveConfigFlow(_LocalSettingsFlow, ConfigFlow, domain=DOMAIN):
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
        """Handle the per-thermostat entry."""
        if user_input is not None:
            entity_id = user_input.get(CONF_TARGET_VTHERM)
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(entity_id)
            if (reg_entry is None or reg_entry.unique_id is None
                    or reg_entry.platform != "versatile_thermostat"):
                return self.async_show_form(
                    step_id="thermostat",
                    data_schema=build_user_schema(dict(DEFAULT_OPTIONS)),
                    errors={CONF_TARGET_VTHERM: "invalid_entity"},
                )

            target_unique_id = reg_entry.unique_id
            await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
            self._abort_if_unique_id_configured()

            self._pending_settings = {**DEFAULT_OPTIONS, **user_input}
            self._pending_settings[CONF_TARGET_VTHERM] = target_unique_id
            self._settings_uid = target_unique_id
            state = self.hass.states.get(entity_id)
            self._settings_title = state.name if state is not None else entity_id
            return await self._show_local_settings()

        return self.async_show_form(
            step_id="thermostat",
            data_schema=build_user_schema(dict(DEFAULT_OPTIONS)),
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

        if entry.data.get(CONF_TARGET_VTHERM) is not None:
            self._edit_entry = entry
            self._settings_uid = entry.data[CONF_TARGET_VTHERM]
            self._pending_settings = {**DEFAULT_OPTIONS, **entry.data, **entry.options}
            return await self.async_step_mode(user_input)

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
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=build_options_schema(defaults),
        )

    def _finish_settings(self, settings):
        entry = getattr(self, "_edit_entry", None)
        if entry is not None:
            return self.async_update_reload_and_abort(entry, data=settings, options={})
        return self.async_create_entry(title=self._settings_title, data=settings)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return PelletStoveOptionsFlow(config_entry)


class PelletStoveOptionsFlow(_LocalSettingsFlow, OptionsFlow):
    """Edit Pellet Stove plugin options."""

    def __init__(self, config_entry) -> None:
        """Store the config entry being edited."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle the options flow."""
        if self._config_entry.data.get(CONF_TARGET_VTHERM) is not None:
            self._settings_uid = self._config_entry.data[CONF_TARGET_VTHERM]
            self._pending_settings = {**DEFAULT_OPTIONS, **self._config_entry.data,
                                      **self._config_entry.options}
            return await self.async_step_mode(user_input)
        if user_input is not None:
            return self.async_create_entry(title="", data={**self._config_entry.data,
                                                           **self._config_entry.options, **user_input})

        defaults = dict(DEFAULT_OPTIONS)
        defaults.update(self._config_entry.options or self._config_entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=build_options_schema(defaults),
        )

    def _finish_settings(self, settings):
        return self.async_create_entry(title="", data=settings)
