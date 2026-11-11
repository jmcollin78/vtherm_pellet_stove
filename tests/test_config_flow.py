"""Tests for resolving a VTherm's configured underlying entity type."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from custom_components.vtherm_pellet_stove.config_flow import (
    PelletStoveConfigFlow,
    PelletStoveOptionsFlow,
    build_target_schema,
)
from custom_components.vtherm_pellet_stove.const import (
    CONF_HYSTERESIS_ON,
    CONF_MIN_ON_DURATION_MIN,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from custom_components.vtherm_pellet_stove.config_flow import (
    resolve_underlying_domain,
)


def _make_hass(monkeypatch, underlying_entities, *, state="unavailable"):
    """Build the registry and config-entry links used by the resolver."""
    target = SimpleNamespace(
        platform="versatile_thermostat",
        config_entry_id="vt-entry",
        unique_id="vt-entry",
    )
    registry = SimpleNamespace(async_get=MagicMock(return_value=target))
    monkeypatch.setattr(er, "async_get", lambda _hass: registry)

    vtherm_entry = SimpleNamespace(
        domain="versatile_thermostat",
        data={"underlying_entity_ids": underlying_entities},
    )
    config_entries = SimpleNamespace(
        async_get_entry=MagicMock(return_value=vtherm_entry)
    )
    states = SimpleNamespace(
        get=MagicMock(return_value=SimpleNamespace(state=state, name="Pellet VTherm"))
    )
    services = SimpleNamespace(async_call=AsyncMock())
    return SimpleNamespace(config_entries=config_entries, states=states, services=services)


def _make_flow(hass):
    """Build the small flow surface needed by the step methods."""
    flow = SimpleNamespace(
        hass=hass,
        context={},
        async_set_unique_id=AsyncMock(),
        _abort_if_unique_id_configured=MagicMock(),
        async_show_form=MagicMock(side_effect=lambda **kwargs: {"type": "form", **kwargs}),
        async_create_entry=MagicMock(
            side_effect=lambda **kwargs: {"type": "create_entry", **kwargs}
        ),
    )
    flow.async_step_thermostat_options = lambda user_input=None: (
        PelletStoveConfigFlow.async_step_thermostat_options(flow, user_input)
    )
    return flow


def test_resolves_switch_under_climate_target(monkeypatch):
    hass = _make_hass(monkeypatch, ["switch.pellet_stove"])

    assert resolve_underlying_domain(hass, "climate.pellet_thermostat") == "switch"
    hass.config_entries.async_get_entry.assert_called_once_with("vt-entry")
    hass.states.get.assert_not_called()


def test_unavailable_switch_remains_classified_as_switch(monkeypatch):
    hass = _make_hass(monkeypatch, ["switch.pellet_stove"], state="unavailable")

    assert resolve_underlying_domain(hass, "climate.pellet_thermostat") == "switch"
    hass.states.get.assert_not_called()


def test_input_boolean_is_classified_as_dry_contact(monkeypatch):
    hass = _make_hass(monkeypatch, ["input_boolean.pellet_stove"])

    assert (
        resolve_underlying_domain(hass, "climate.pellet_thermostat")
        == "input_boolean"
    )
    hass.states.get.assert_not_called()


def test_unresolved_underlying_returns_none(monkeypatch):
    hass = _make_hass(monkeypatch, [])

    assert resolve_underlying_domain(hass, "climate.pellet_thermostat") is None


def test_generic_climate_is_not_classified_as_duepi(monkeypatch):
    hass = _make_hass(monkeypatch, ["climate.generic_heater"])

    assert resolve_underlying_domain(hass, "climate.pellet_thermostat") == "climate"


@pytest.mark.parametrize(
    "underlying_entity",
    ["switch.pellet_stove", "input_boolean.pellet_stove"],
)
async def test_target_step_keeps_climate_selector_and_defers_entry_creation(
    monkeypatch, underlying_entity
):
    hass = _make_hass(monkeypatch, [underlying_entity])
    flow = _make_flow(hass)
    schema = build_target_schema()
    target_selector = next(
        value
        for key, value in schema.schema.items()
        if getattr(key, "schema", None) == CONF_TARGET_VTHERM
    )

    assert target_selector.config["domain"] == ["climate"]
    result = await PelletStoveConfigFlow.async_step_thermostat(
        flow, {CONF_TARGET_VTHERM: "climate.pellet_thermostat"}
    )

    assert result["step_id"] == "thermostat_options_switch"
    flow.async_create_entry.assert_not_called()
    flow.async_set_unique_id.assert_awaited_once_with(f"{DOMAIN}-vt-entry")
    flow._abort_if_unique_id_configured.assert_called_once_with()
    assert flow.context[CONF_TARGET_VTHERM] == "vt-entry"

    result = await PelletStoveConfigFlow.async_step_thermostat_options(
        flow, {**DEFAULT_OPTIONS, CONF_HYSTERESIS_ON: 1.25}
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Pellet VTherm"
    assert result["data"] == {
        **DEFAULT_OPTIONS,
        CONF_HYSTERESIS_ON: 1.25,
        CONF_TARGET_VTHERM: "vt-entry",
    }


async def test_generic_climate_settings_have_no_dry_contact_warning(monkeypatch):
    hass = _make_hass(monkeypatch, ["climate.generic_heater"])
    flow = _make_flow(hass)
    flow.context = {
        CONF_TARGET_VTHERM: "vt-entry",
        "target_vtherm_entity_id": "climate.pellet_thermostat",
    }

    result = await PelletStoveConfigFlow.async_step_thermostat_options(flow)

    assert result["step_id"] == "thermostat_options"
    flow.async_create_entry.assert_not_called()


async def test_duepi_climate_settings_have_no_dry_contact_warning(monkeypatch):
    hass = _make_hass(monkeypatch, ["climate.duepi_evo"])
    flow = _make_flow(hass)
    flow.context = {
        CONF_TARGET_VTHERM: "vt-entry",
        "target_vtherm_entity_id": "climate.pellet_thermostat",
    }

    result = await PelletStoveConfigFlow.async_step_thermostat_options(flow)

    assert result["step_id"] == "thermostat_options"


def test_dry_contact_warning_translations_cover_all_three_forms():
    translations_dir = (
        Path(__file__).parents[1]
        / "custom_components/vtherm_pellet_stove/translations"
    )
    warning_by_language = {
        "fr": "Aucun retour sur l'état réel du poêle : ON/OFF exprime seulement une demande. Le minimum de marche doit inclure l'allumage et la chauffe utile ; le minimum d'arrêt additionné au refroidissement doit couvrir l'extinction et le repos.",
        "en": "There is no feedback about the stove's actual state: ON/OFF expresses a request only. Minimum on time must include ignition and useful heating; minimum off time plus cooldown must cover shutdown and rest.",
    }
    duration_fields = {
        "min_on_duration_min",
        "min_off_duration_min",
        "cooldown_duration_min",
    }

    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate translation key: {key}")
            result[key] = value
        return result

    for language, warning in warning_by_language.items():
        translations = json.loads(
            (translations_dir / f"{language}.json").read_text(),
            object_pairs_hook=reject_duplicate_keys,
        )
        forms = [
            translations["config"]["step"]["thermostat_options_switch"],
            translations["config"]["step"]["reconfigure_switch"],
            translations["options"]["step"]["init_switch"],
        ]
        assert all(warning in form["description"] for form in forms)
        assert all(duration_fields <= set(form["data"]) for form in forms)


async def test_options_and_reconfigure_detect_replaced_underlying(monkeypatch):
    hass = _make_hass(monkeypatch, ["climate.generic_heater"])
    pellet_entry = SimpleNamespace(
        data={CONF_TARGET_VTHERM: "vt-entry"},
        options={CONF_MIN_ON_DURATION_MIN: 18},
    )
    options_flow = SimpleNamespace(
        hass=hass,
        _config_entry=pellet_entry,
        async_show_form=MagicMock(side_effect=lambda **kwargs: {"type": "form", **kwargs}),
        async_create_entry=MagicMock(
            side_effect=lambda **kwargs: {"type": "create_entry", **kwargs}
        ),
    )
    reconfigure_flow = SimpleNamespace(
        hass=hass,
        _get_reconfigure_entry=MagicMock(return_value=pellet_entry),
        async_show_form=MagicMock(side_effect=lambda **kwargs: {"type": "form", **kwargs}),
        async_update_reload_and_abort=MagicMock(return_value={"type": "abort"}),
    )

    result = await PelletStoveOptionsFlow.async_step_init(options_flow)
    assert result["step_id"] == "init"

    result = await PelletStoveConfigFlow.async_step_reconfigure(reconfigure_flow)
    assert result["step_id"] == "reconfigure"

    hass.config_entries.async_get_entry.return_value.data[
        "underlying_entity_ids"
    ] = ["input_boolean.pellet_stove"]

    result = await PelletStoveOptionsFlow.async_step_init(options_flow)
    assert result["step_id"] == "init_switch"
    options_flow.async_create_entry.assert_not_called()

    result = await PelletStoveConfigFlow.async_step_reconfigure(reconfigure_flow)
    assert result["step_id"] == "reconfigure_switch"
    reconfigure_flow.async_update_reload_and_abort.assert_not_called()
    hass.states.get.assert_not_called()
    hass.services.async_call.assert_not_awaited()

    submitted_options = {CONF_MIN_ON_DURATION_MIN: 24}
    await PelletStoveOptionsFlow.async_step_init(options_flow, submitted_options)
    options_flow.async_create_entry.assert_called_once_with(
        title="", data=submitted_options
    )

    result = await PelletStoveConfigFlow.async_step_reconfigure(
        reconfigure_flow, submitted_options
    )
    assert result == {"type": "abort"}
    reconfigure_flow.async_update_reload_and_abort.assert_called_once_with(
        pellet_entry,
        data={**pellet_entry.data, **submitted_options},
        options={},
    )


async def test_global_defaults_entry_creation_is_unchanged():
    flow = _make_flow(SimpleNamespace())
    flow._async_current_entries = MagicMock(return_value=[])

    result = await PelletStoveConfigFlow.async_step_user(flow)

    assert result["data"] == DEFAULT_OPTIONS
    flow.async_set_unique_id.assert_awaited_once_with(DOMAIN)
    flow._abort_if_unique_id_configured.assert_called_once_with()


@pytest.mark.parametrize(
    "underlying_entities",
    [
        ["switch.pellet_stove", "climate.generic_heater"],
        ["switch.first", "switch.second"],
        ["unsupported.device"],
    ],
)
def test_ambiguous_or_unsupported_underlying_returns_none(
    monkeypatch, underlying_entities
):
    hass = _make_hass(monkeypatch, underlying_entities)

    assert resolve_underlying_domain(hass, "climate.pellet_thermostat") is None