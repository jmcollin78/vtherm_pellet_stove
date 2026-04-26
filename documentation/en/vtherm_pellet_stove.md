# vtherm_pellet_stove — User Guide

> Plugin for [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) that brings a pellet-stove-aware proportional regulation algorithm (`pellet_regulation`) to Home Assistant.

---

## Table of contents

- [vtherm\_pellet\_stove — User Guide](#vtherm_pellet_stove--user-guide)
  - [Table of contents](#table-of-contents)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Installation](#2-installation)
    - [Via HACS (recommended)](#via-hacs-recommended)
    - [Manual installation](#manual-installation)
  - [Quick Start — Setting up a pellet stove VTherm in 5 steps](#quick-start--setting-up-a-pellet-stove-vtherm-in-5-steps)
    - [Step 1 — Install Versatile Thermostat](#step-1--install-versatile-thermostat)
    - [Step 2 — Install vtherm\_pellet\_stove and create the global defaults](#step-2--install-vtherm_pellet_stove-and-create-the-global-defaults)
    - [Step 3 — Create the VTherm of type over\_switch](#step-3--create-the-vtherm-of-type-over_switch)
    - [Step 4 — Add the custom ON/OFF commands](#step-4--add-the-custom-onoff-commands)
    - [Step 5 — Link vtherm\_pellet\_stove to the VTherm](#step-5--link-vtherm_pellet_stove-to-the-vtherm)
  - [3. How it works](#3-how-it-works)
  - [4. Configuring Versatile Thermostat](#4-configuring-versatile-thermostat)
  - [5. Plugin configuration](#5-plugin-configuration)
    - [5.1 Global defaults entry](#51-global-defaults-entry)
    - [5.2 Per-thermostat entry](#52-per-thermostat-entry)
    - [5.3 Options flow](#53-options-flow)
  - [6. Configuration reference](#6-configuration-reference)
    - [Hysteresis](#hysteresis)
    - [Pellet guard-rails](#pellet-guard-rails)
    - [Power level control (optional)](#power-level-control-optional)
  - [7. Full example — Duepi EVO stove](#7-full-example--duepi-evo-stove)
    - [Step 1 — Install the plugin](#step-1--install-the-plugin)
    - [Step 2 — Create the VTherm](#step-2--create-the-vtherm)
    - [Step 3 — Configure the plugin](#step-3--configure-the-plugin)
    - [Step 4 — Verify](#step-4--verify)
  - [8. State diagram](#8-state-diagram)
  - [9. Troubleshooting](#9-troubleshooting)
    - [The stove never turns on](#the-stove-never-turns-on)
    - [The stove turns on but the power level stays at the default](#the-stove-turns-on-but-the-power-level-stays-at-the-default)
    - [The stove does not turn off despite the room being warm](#the-stove-does-not-turn-off-despite-the-room-being-warm)
    - [HA restarted and the stove state is inconsistent](#ha-restarted-and-the-stove-state-is-inconsistent)

---

## 1. Prerequisites

| Requirement                                                                | Minimum version |
| -------------------------------------------------------------------------- | --------------- |
| Home Assistant                                                             | 2026.4          |
| [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) | 10.0            |
| HACS                                                                       | 1.34            |

Your pellet stove **must already be exposed as a `climate` entity** in Home Assistant (via Duepi EVO, ESPHome, MCZ, EdilKamin, or any other integration). This plugin does **not** communicate directly with stoves.

---

## 2. Installation

### Via HACS (recommended)

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jmcollin78&repository=vtherm_pellet_stove&category=Integration)

1. Open HACS → **Integrations** → menu **⋮** → **Custom repositories**.
2. Add `https://github.com/jmcollin78/vtherm_pellet_stove` as an **Integration**.
3. Search for **Versatile Thermostat Pellet Stove** and click **Download**.
4. Restart Home Assistant.

### Manual installation

1. Download the latest release from [GitHub Releases](https://github.com/jmcollin78/vtherm_pellet_stove/releases).
2. Copy the `custom_components/vtherm_pellet_stove` folder into your HA `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Quick Start — Setting up a pellet stove VTherm in 5 steps

This section walks you through the complete setup from scratch. Each step links to the detailed reference section for more information.

### Step 1 — Install Versatile Thermostat

If Versatile Thermostat is not already installed:

1. Open HACS → **Integrations**.
2. Search for **Versatile Thermostat** and click **Download**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Versatile Thermostat** and complete its initial setup.

Refer to the [Versatile Thermostat documentation](https://github.com/jmcollin78/versatile_thermostat) for details.

### Step 2 — Install vtherm_pellet_stove and create the global defaults

1. Install this plugin following [§2 Installation](#2-installation).
2. After the restart, go to **Settings → Devices & Services**.
3. Click **Add Integration** and select **Versatile Thermostat Pellet Stove**.
4. A **global defaults** entry is created automatically with sensible default values. It applies to every pellet stove VTherm that has no per-thermostat override.
5. *(Optional)* Click **Options** on the global entry to adjust the defaults (hysteresis, guard-rails, power levels…) now or later — see [§6 Configuration reference](#6-configuration-reference).

### Step 3 — Create the VTherm of type `over_switch`

1. Go to **Settings → Devices & Services → Versatile Thermostat → Add**.
2. Choose thermostat type **`over_switch`**.
3. In the **Underlying entity** field, select the `climate` entity that controls your pellet stove (e.g. `climate.duepi_evo`).
4. In the **Proportional function** (algorithm) field, select **`pellet_regulation`**.
5. Set the cycle duration (`cycle_min`) to `60` minutes.
6. Set **Minimal activation delay** to `1800` s (30 min) and **Minimal deactivation delay** to `1500` s (25 min) — these should align with `min_on_duration_min` and `min_off_duration_min + cooldown_duration_min`.
7. Complete the remaining VTherm settings (name, temperature sensor, etc.) and save.

### Step 4 — Add the custom ON/OFF commands

VTherm's `over_switch` mode sends two configurable service calls to the stove. These must be set on the **underlying entity** configuration page of the VTherm you just created:

1. Open the VTherm entity → **Options** → **Underlying entities** page.
2. In the **Switch ON command** (`vswitch_on`) field, enter:
   ```
   set_hvac_mode/hvac_mode:heat
   ```
3. In the **Switch OFF command** (`vswitch_off`) field, enter:
   ```
   set_hvac_mode/hvac_mode:off
   ```
4. Save. VTherm will now call `climate.set_hvac_mode(hvac_mode=heat)` to ignite the stove and `climate.set_hvac_mode(hvac_mode=off)` to extinguish it.

> **Why these commands?** Pellet stoves are exposed as `climate` entities, not `switch` entities. The `vswitch_on/off` syntax lets VTherm call any HA service in the format `service_name/key:value`.

### Step 5 — Link vtherm_pellet_stove to the VTherm

Choose one of the two options depending on whether you need parameters specific to this stove:

**Option A — Use the global defaults (no action needed)**

If the global default parameters suit this stove, no additional step is required. The VTherm automatically picks up the global defaults because it is configured with the `pellet_regulation` algorithm.

**Option B — Create a per-thermostat entry (recommended for fine-tuning)**

1. Go to **Settings → Devices & Services → Versatile Thermostat Pellet Stove → Add entry**.
2. Select the VTherm `climate` entity created in Step 3.
3. Adjust the parameters specifically for this stove (e.g. different `min_on_duration_min`, adapted `power_levels`).
4. Save. This entry overrides the global defaults only for this VTherm — see [§5 Plugin configuration](#5-plugin-configuration).

> Per-thermostat values always take precedence over the global defaults. You can have one entry per stove.

---

## 3. How it works

`vtherm_pellet_stove` registers the **`pellet_regulation`** algorithm in the VTherm API. When a `over_switch` VTherm is configured to use this algorithm, the plugin:

1. **Calculates `on_percent`** — a binary 0 or 1 value derived from a parameterizable hysteresis on the room temperature.
2. **Applies pellet-specific guard-rails** — minimum on/off durations and a cooldown delay to prevent excessive ignition cycles.
3. **Sends ON/OFF commands** — VTherm's cycle scheduler translates `on_percent` into `set_hvac_mode` calls on the stove's `climate` entity (via `vswitch_on` / `vswitch_off`).
4. **Optionally adjusts the power level** — the plugin calls `set_fan_mode` or `set_preset_mode` on the stove according to the temperature gap (ΔT) and slope.

```
Room too cold                         Room at setpoint
─────────────────────────────────────────────────────
current ≤ target − hysteresis_on      |
  → on_percent = 1                    |   hold / off
  → VTherm sends vswitch_on ──────►  climate.poele_pellets
                                           set_hvac_mode(heat)
```

---

## 4. Configuring Versatile Thermostat

Create a VTherm in **`over_switch`** mode and set the following options:

| VTherm option                    | Value                                                                                   |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| **Thermostat type**              | `over_switch`                                                                           |
| **Underlying entity**            | `climate.<your_stove>` (e.g. `climate.duepi_evo`)                                       |
| **Proportional function**        | `pellet_regulation`                                                                     |
| **`vswitch_on` command**         | `set_hvac_mode/hvac_mode:heat`                                                          |
| **`vswitch_off` command**        | `set_hvac_mode/hvac_mode:off`                                                           |
| **Cycle duration** (`cycle_min`) | 60 (minutes) — the cycle scheduler runs every hour                                      |
| **Minimal activation delay**     | 1800 (seconds, i.e. 30 min) — must match `min_on_duration_min`                          |
| **Minimal deactivation delay**   | 1500 (seconds, i.e. 25 min) — must match `min_off_duration_min + cooldown_duration_min` |

> **Why `over_switch`?** VTherm's `over_switch` mode exposes the `InterfacePropAlgorithmFactory` extension point that allows external plugins to register custom regulation algorithms. The `vswitch_on/off` options let you target any HA domain, including `climate`.

---

## 5. Plugin configuration

### 5.1 Global defaults entry

On **first installation**, the integration creates a single **global defaults** entry automatically (with the default values from §6). All VTherm thermostats using `pellet_regulation` that have no per-thermostat entry will inherit these values.

Go to **Settings → Devices & Services → Versatile Thermostat Pellet Stove** to edit these defaults via the **Options** button.

### 5.2 Per-thermostat entry

Click **Add entry** to create a per-thermostat override:

1. Select the VTherm `climate` entity you want to target.
2. Adjust any parameter — only this thermostat will use the overridden values.

Per-thermostat values always take precedence over the global defaults.

### 5.3 Options flow

Both the global entry and per-thermostat entries expose an **Options** button that lets you change parameters without reinstalling. Changes are applied immediately: the targeted VTherm(s) are reloaded automatically.

---

## 6. Configuration reference

### Hysteresis

| Parameter        | Default  | Description                                                        |
| ---------------- | -------- | ------------------------------------------------------------------ |
| `hysteresis_on`  | `0.5 °C` | Start heating when `current_temp ≤ target − hysteresis_on`.        |
| `hysteresis_off` | `0.3 °C` | Stop heating when `current_temp ≥ target + hysteresis_off`.        |
| `min_on_percent` | `0.0`    | `on_percent` sent to the scheduler when the algorithm decides OFF. |
| `max_on_percent` | `1.0`    | `on_percent` sent to the scheduler when the algorithm decides ON.  |

### Pellet guard-rails

| Parameter               | Default   | Description                                                                                       |
| ----------------------- | --------- | ------------------------------------------------------------------------------------------------- |
| `min_on_duration_min`   | `30 min`  | Minimum burn time before an OFF is allowed. Protects the igniter.                                 |
| `min_off_duration_min`  | `20 min`  | Minimum off time before re-ignition is allowed.                                                   |
| `cooldown_duration_min` | `5 min`   | Extra cooldown added on top of `min_off_duration_min` after each OFF.                             |
| `safety_room_temp`      | `26.0 °C` | Room temperature above which the stove is **immediately forced off** (overrides all guard-rails). |

### Power level control (optional)

| Parameter                   | Default                 | Description                                                              |
| --------------------------- | ----------------------- | ------------------------------------------------------------------------ |
| `power_control_enabled`     | `true`                  | Enable/disable the power level control feature.                          |
| `power_control_attribute`   | `fan_mode`              | HA climate attribute used to set the level: `fan_mode` or `preset_mode`. |
| `power_levels`              | `["1","2","3","4","5"]` | Ordered list of level values (weakest → strongest).                      |
| `power_default_level_index` | `2`                     | Default index when the temperature slope is unknown.                     |
| `power_boost_enabled`       | `true`                  | Enable a temporary boost to maximum after a setpoint increase.           |
| `power_boost_duration_min`  | `15 min`                | Duration of the boost phase.                                             |

---

## 7. Full example — Duepi EVO stove

This example assumes the stove is exposed as `climate.duepi_evo` with `fan_modes` = `["1", "2", "3", "4", "5"]`.

### Step 1 — Install the plugin

Follow §2.

### Step 2 — Create the VTherm

In **Settings → Devices & Services → Versatile Thermostat → Add**:

```yaml
# Equivalent YAML for reference (the UI is recommended)
type: over_switch
heater: climate.duepi_evo
vswitch_on: "set_hvac_mode/hvac_mode:heat"
vswitch_off: "set_hvac_mode/hvac_mode:off"
proportional_function: pellet_regulation
cycle_min: 60
minimal_activation_delay: 1800
minimal_deactivation_delay: 1500
```

### Step 3 — Configure the plugin

In **Settings → Devices & Services → Versatile Thermostat Pellet Stove → Options**:

| Parameter                  | Recommended value       | Reasoning                                          |
| -------------------------- | ----------------------- | -------------------------------------------------- |
| `hysteresis_on`            | `0.5`                   | Comfortable margin to avoid unnecessary ignitions. |
| `hysteresis_off`           | `0.3`                   | Narrower: once warm, cut off quickly.              |
| `min_on_duration_min`      | `30`                    | Minimum recommended by Duepi EVO documentation.    |
| `min_off_duration_min`     | `20`                    | Allow the stove to cool before re-ignition.        |
| `cooldown_duration_min`    | `5`                     | Extra margin for exhaust clearance.                |
| `safety_room_temp`         | `26.0`                  | Suitable for a living room; raise for a garage.    |
| `power_control_enabled`    | `true`                  | Activate automatic power level control.            |
| `power_control_attribute`  | `fan_mode`              | Duepi EVO uses `fan_mode` for power.               |
| `power_levels`             | `["1","2","3","4","5"]` | Match the stove's `fan_modes`.                     |
| `power_boost_duration_min` | `15`                    | 15-minute boost after setpoint rise.               |

### Step 4 — Verify

1. Check that `climate.duepi_evo` goes to `hvac_mode: heat` when the VTherm calls for heating.
2. Check the VTherm attributes in **Developer Tools → States** — look for the `pellet_regulation` attribute block:

```json
{
  "pellet_regulation": {
    "is_heating": true,
    "on_percent": 1.0,
    "current_level": "3",
    "elapsed_on_min": 12,
    "last_reason": "below_on_threshold"
  }
}
```

---

## 8. State diagram

The stove transitions through the following logical states:

```
               ┌──────────────────────────────────────────┐
               ▼                                          │
           ┌───────┐  on_percent=1 (min_off+cooldown      │
           │  Off  │  elapsed)                            │
           └───┬───┘                                      │
               │                                          │
               ▼                                          │
          ┌──────────┐  min_on_duration                   │
          │ Igniting │  not yet reached                   │
          └────┬─────┘                                    │
               │  min_on_duration reached                 │
               ▼                                          │
          ┌─────────┐  on_percent=0 (min_on               │
          │ Burning │──elapsed OR safety override) ──► Cooldown
          └─────────┘                                     │
                                                          │
                                              min_off + cooldown elapsed
```

> `Igniting` and `Burning` are logical views of `is_heating=True`. `Cooldown` is `is_heating=False` while `min_off + cooldown` has not yet elapsed.

---

## 9. Troubleshooting

### The stove never turns on

- Check that `vswitch_on = "set_hvac_mode/hvac_mode:heat"` is set on the VTherm.
- Verify that `climate.<stove>` accepts `hvac_mode: heat` (test manually in Developer Tools → Services).
- Check that `current_temperature` is available on the VTherm and is below `target − hysteresis_on`.
- Verify that `min_off_duration_min + cooldown_duration_min` has elapsed since the last OFF.

### The stove turns on but the power level stays at the default

- Ensure `power_control_enabled` is `true`.
- Check that `power_levels` matches the `fan_modes` (or `preset_modes`) reported by the stove entity.
- Look for errors in the HA log for `vtherm_pellet_stove`.

### The stove does not turn off despite the room being warm

- Check that `current_temperature ≥ target + hysteresis_off`.
- Verify that `min_on_duration_min` has elapsed since the last ignition.
- If the room temperature exceeds `safety_room_temp`, the stove should turn off immediately regardless of guard-rails.

### HA restarted and the stove state is inconsistent

- The plugin persists its state in the HA storage (`.storage/vtherm_pellet_stove.*`). If the file is missing or corrupted, the state resets to `is_heating=False`. Guard-rails are applied from that moment forward.
