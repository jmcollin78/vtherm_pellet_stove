# Versatile Thermostat Pellet Stove

[Lire la version française](README.fr.md)

<p align="center">
  <img src="custom_components/vtherm_pellet_stove/brand/logo.png" alt="Pellet Stove Logo" width="300" />
</p>

<p align="center">
  <strong>Pellet stove proportional regulation plugin for Versatile Thermostat</strong>
</p>

<p align="center">
  Control your pellet stove with a regulation algorithm tailored to its physical constraints — long ignition times, power levels, anti-short-cycle protection, and safety cut-offs.
</p>

---

## What is vtherm_pellet_stove?

`vtherm_pellet_stove` registers a new proportional algorithm named **`pellet_regulation`** in the [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm) API. It extends VTherm `over_switch` thermostats that target a `climate` entity (e.g. a Duepi EVO, an ESPHome stove, MCZ, EdilKamin, …).

Key features:

- **Parameterizable hysteresis** — configurable `hysteresis_on` / `hysteresis_off` thresholds.
- **Anti-short-cycle protection** — minimum on/off durations and cooldown delay keep the igniter safe.
- **Safety cut-off** — forces the stove off when the room temperature exceeds a configurable threshold.
- **Optional power level control** — adjusts `fan_mode` or `preset_mode` on the underlying climate entity based on `ΔT` and temperature slope.
- **Boost** — temporarily raises power to maximum after a setpoint increase.
- **Persistent state** — survives Home Assistant restarts.
- **HACS-compatible** — global defaults entry + per-thermostat overrides.

## Integration with Versatile Thermostat

The plugin relies on the public [vtherm_api](https://github.com/KipK/vtherm_api). Once installed:

1. Configure Versatile Thermostat in **`over_switch`** mode.
2. Set the underlying entity to your stove's `climate.*` entity.
3. Configure `vswitch_on = "set_hvac_mode/hvac_mode:heat"` and `vswitch_off = "set_hvac_mode/hvac_mode:off"`.
4. Select **`pellet_regulation`** as the proportional function.

## Installation

### Via HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jmcollin78&repository=vtherm_pellet_stove&category=Integration)

1. Add this repository to HACS as a custom integration.
2. Install **Versatile Thermostat Pellet Stove**.
3. Restart Home Assistant.
4. Add the integration from **Settings → Devices & Services**.

### Manual installation

1. Copy `custom_components/vtherm_pellet_stove` to your HA `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from **Settings → Devices & Services**.

## Documentation

- 🇬🇧 [User documentation](documentation/en/vtherm_pellet_stove.md)
- 🇬🇧 [Technical documentation](documentation/en/technical_doc.md)
- 🇫🇷 [Documentation utilisateur](documentation/fr/vtherm_pellet_stove.md)
- 🇫🇷 [Documentation technique](documentation/fr/technical_doc.md)

## Architecture

See [tech-docs/plugin-architecture.md](tech-docs/plugin-architecture.md) for the full design document.

## Authors

- [@jmcollin78](https://github.com/jmcollin78)

## License

MIT — see [LICENSE](LICENSE).
