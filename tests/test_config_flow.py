"""Local dry-contact configuration and preserved power settings."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vtherm_pellet_stove.config_flow import (
    PelletStoveConfigFlow, PelletStoveOptionsFlow, build_options_schema,
)
from custom_components.vtherm_pellet_stove.const import (
    CONF_BISTABLE_CONFIRMED, CONF_DRY_CONTACT, CONF_POWER_BOOST_ENABLED,
    CONF_POWER_CONTROL_ENABLED, CONF_TARGET_VTHERM, DEFAULT_OPTIONS,
)


def _entry(*, dry=False):
    return SimpleNamespace(
        entry_id="plugin", unique_id="plugin",
        data={**DEFAULT_OPTIONS, CONF_TARGET_VTHERM: "vt", CONF_DRY_CONTACT: dry,
              CONF_BISTABLE_CONFIRMED: dry}, options={},
    )


def _hass(entities=None):
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [SimpleNamespace(
        entry_id="vt", unique_id=None, options={},
        data={"thermostat_type": "thermostat_over_switch",
              "underlying_entity_ids": entities if entities is not None else ["switch.stove"]},
    )]
    return hass


def test_dry_schema_hides_power_without_changing_defaults():
    defaults = dict(DEFAULT_OPTIONS)
    schema = build_options_schema(defaults, dry_contact=True)
    fields = {key.schema for key in schema.schema}
    assert not any(key.startswith("power_") for key in fields)
    assert CONF_BISTABLE_CONFIRMED in fields
    assert schema({CONF_BISTABLE_CONFIRMED: False})[CONF_BISTABLE_CONFIRMED] is False
    assert defaults == DEFAULT_OPTIONS


@pytest.mark.parametrize("flow_kind", ["create", "options", "reconfigure"])
async def test_local_warning_before_save_and_power_values_preserved(flow_kind, monkeypatch):
    entry = _entry()
    flow = PelletStoveOptionsFlow(entry) if flow_kind == "options" else PelletStoveConfigFlow()
    flow.hass = _hass()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
    if flow_kind == "create":
        flow.async_set_unique_id = AsyncMock()
        monkeypatch.setattr(flow, "_abort_if_unique_id_configured", MagicMock())
        flow.hass.states.get.return_value = SimpleNamespace(name="Stove")
        with patch("custom_components.vtherm_pellet_stove.config_flow.er.async_get") as registry:
            registry.return_value.async_get.return_value = SimpleNamespace(unique_id="vt", platform="versatile_thermostat")
            result = await flow.async_step_thermostat({CONF_TARGET_VTHERM: "climate.vt", CONF_DRY_CONTACT: True})
    elif flow_kind == "options":
        await flow.async_step_init()
        result = await flow.async_step_mode({CONF_DRY_CONTACT: True})
    else:
        monkeypatch.setattr(flow, "_get_reconfigure_entry", MagicMock(return_value=entry))
        await flow.async_step_reconfigure()
        result = await flow.async_step_mode({CONF_DRY_CONTACT: True})
    assert result["step_id"] == "dry_contact"
    flow.async_create_entry.assert_not_called()
    flow.async_update_reload_and_abort.assert_not_called()
    assert not entry.data[CONF_DRY_CONTACT]
    submitted = result["data_schema"]({CONF_BISTABLE_CONFIRMED: True})
    await flow.async_step_dry_contact(submitted)
    saved = (flow.async_update_reload_and_abort.call_args.kwargs["data"]
             if flow_kind == "reconfigure" else flow.async_create_entry.call_args.kwargs["data"])
    assert saved[CONF_DRY_CONTACT]
    assert saved[CONF_BISTABLE_CONFIRMED]
    assert saved[CONF_POWER_CONTROL_ENABLED] is True
    assert saved[CONF_POWER_BOOST_ENABLED] is True
    assert saved[CONF_TARGET_VTHERM] == "vt"


@pytest.mark.parametrize("entities", [[], ["switch.one", "switch.two"], ["input_boolean.stove"]])
async def test_local_flow_rejects_invalid_target(entities):
    flow = PelletStoveOptionsFlow(_entry())
    flow.hass = _hass(entities)
    flow.async_create_entry = MagicMock()
    await flow.async_step_init()
    await flow.async_step_mode({CONF_DRY_CONTACT: True})
    result = await flow.async_step_dry_contact({CONF_BISTABLE_CONFIRMED: True})
    assert result["errors"]["base"] in ("single_underlying_required", "invalid_dry_contact")
    flow.async_create_entry.assert_not_called()


async def test_return_to_climate_exposes_preserved_power_settings():
    entry = _entry(dry=True)
    flow = PelletStoveOptionsFlow(entry)
    flow.hass = _hass(["climate.stove"])
    flow.async_create_entry = MagicMock()
    await flow.async_step_init()
    form = await flow.async_step_mode({CONF_DRY_CONTACT: False})
    assert form["step_id"] == "climate"
    submitted = form["data_schema"]({})
    assert submitted[CONF_POWER_CONTROL_ENABLED]
    await flow.async_step_climate(submitted)
    assert flow.async_create_entry.call_args.kwargs["data"][CONF_POWER_CONTROL_ENABLED]


async def test_bistability_confirmation_is_required_before_saving():
    flow = PelletStoveOptionsFlow(_entry())
    flow.hass = _hass()
    flow.async_create_entry = MagicMock()
    await flow.async_step_init()
    await flow.async_step_mode({CONF_DRY_CONTACT: True})
    result = await flow.async_step_dry_contact({CONF_BISTABLE_CONFIRMED: False})
    assert result["errors"] == {"base": "invalid_dry_contact"}
    flow.async_create_entry.assert_not_called()


async def test_non_vtherm_climate_cannot_be_selected():
    flow = PelletStoveConfigFlow()
    flow.hass = _hass()
    with patch("custom_components.vtherm_pellet_stove.config_flow.er.async_get") as registry:
        registry.return_value.async_get.return_value = SimpleNamespace(unique_id="vt", platform="other")
        result = await flow.async_step_thermostat({CONF_TARGET_VTHERM: "climate.other", CONF_DRY_CONTACT: True})
    assert result["errors"] == {CONF_TARGET_VTHERM: "invalid_entity"}