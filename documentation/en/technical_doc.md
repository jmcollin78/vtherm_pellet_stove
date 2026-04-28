# vtherm_pellet_stove — Technical Documentation

> Internal architecture reference for developers and maintainers of the plugin.
> For the full design document see [tech-docs/plugin-architecture.md](../../tech-docs/plugin-architecture.md).

---

## Table of contents

1. [Overview](#1-overview)
2. [Repository structure](#2-repository-structure)
3. [Component responsibilities](#3-component-responsibilities)
4. [Data model](#4-data-model)
5. [Regulation algorithm](#5-regulation-algorithm)
6. [HA lifecycle](#6-ha-lifecycle)
7. [Configuration UI](#7-configuration-ui)
8. [Persistent state](#8-persistent-state)
9. [Power level control](#9-power-level-control)
10. [Testing strategy](#10-testing-strategy)
11. [Observability — Logs and debug entity](#11-observability--logs-and-debug-entity)
12. [Adding a new feature](#12-adding-a-new-feature)

---

## 1. Overview

`vtherm_pellet_stove` is a **HACS-distributable HA integration** that registers itself as an external proportional algorithm (`pellet_regulation`) in the [vtherm_api](https://github.com/KipK/vtherm_api) public interface.

It is designed exclusively for VTherm `over_switch` thermostats targeting a `climate` entity (the pellet stove). VTherm's built-in cycle scheduler handles the actual ON/OFF timing; this plugin only provides the **on_percent calculation** and the optional power-level adjustment.

```
┌────────────────────────────────────┐
│         Home Assistant             │
│                                    │
│  ┌──────────────┐  register        │
│  │  vtherm_     │──────────────►   │
│  │  pellet_stove│                  │
│  │  (this repo) │  create handler  │
│  │              │◄─────────────    │
│  └──────┬───────┘                  │
│         │ calculate / start_cycle  │
│         ▼                          │
│  ┌──────────────┐  vswitch_on/off  │
│  │  VTherm      │────────────────► climate.stove
│  │ over_switch  │                  │
│  └──────────────┘                  │
└────────────────────────────────────┘
```

---

## 2. Repository structure

```
custom_components/vtherm_pellet_stove/
├── __init__.py          # setup / teardown, factory register/unregister, VTherm reload, sensor platform forward
├── manifest.json        # HA integration manifest (dependency: versatile_thermostat)
├── config_flow.py       # ConfigFlow (global + per-thermostat) + OptionsFlow
├── const.py             # DOMAIN, CONF_* constants, DEFAULT_OPTIONS
├── factory.py           # PelletRegulationFactory (InterfacePropAlgorithmFactory)
├── handler.py           # PelletRegulationHandler (InterfacePropAlgorithmHandler)
├── sensor.py            # PelletDebugSensor — diagnostic entity
└── pellet/              # Pure-Python business logic (no HA dependency)
    ├── __init__.py
    ├── controller.py    # PelletRegulationController — orchestration + INFO/WARNING logs
    ├── state.py         # PelletState — persistent dataclass
    ├── hysteresis.py    # HysteresisDecider — binary ON/OFF decision
    ├── cycle_guard.py   # CycleGuard — min on/off + cooldown
    ├── power_mapper.py  # PowerMapper — ΔT/slope → level index
    └── boost.py         # BoostManager — temporary max-power boost
```

---

## 3. Component responsibilities

### `__init__.py`

- Calls `VThermAPI.register_prop_algorithm(PelletRegulationFactory())` on `async_setup` / `async_setup_entry`.
- Calls `VThermAPI.unregister_prop_algorithm("pellet_regulation")` when the last plugin entry is removed.
- Triggers `_reload_pellet_vtherms()` after option changes so new parameters take effect immediately.
- For the global entry only, forwards the `sensor` platform (`async_forward_entry_setups`) enabling dynamic creation of debug sensors.
- Skips reload during HA startup to avoid disturbing the VTherm restore sequence.

### `factory.py` — `PelletRegulationFactory`

Simple factory: `name = "pellet_regulation"`, `create(thermostat) → PelletRegulationHandler`.

### `handler.py` — `PelletRegulationHandler`

HA lifecycle adapter. Implements `InterfacePropAlgorithmHandler`:

| Method                | Responsibility                                                                                                                               |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `init_algorithm`      | Resolve effective options (`_resolve_options`), build `PelletRegulationController`, create `Store`.                                          |
| `async_added_to_hass` | Load persistent state from `Store`, call `controller.restore_state`.                                                                         |
| `async_startup`       | Trigger `on_state_changed(True)` → first `control_heating` iteration.                                                                        |
| `remove`              | Schedule `store.async_save` via `hass.async_create_task`.                                                                                    |
| `control_heating`     | Call `controller.calculate`, update `thermostat.prop_algorithm`, call `scheduler.start_cycle`, apply power level, publish HA state, persist. |
| `on_state_changed`    | Forward to `control_heating` when `changed=True`.                                                                                            |
| `on_scheduler_ready`  | Store scheduler reference, register cycle callbacks.                                                                                         |
| `_apply_power_level`  | Call `climate.set_fan_mode / set_preset_mode` on underlying climate entities. Anti-spam: skip if level unchanged.                            |

**Option resolution** (`_resolve_options`):

```
DEFAULT_OPTIONS ← global entry (data → options) ← per-thermostat entry (data → options)
```

The `options` dict (from OptionsFlow) always takes precedence over `data` (from ConfigFlow).

### `pellet/` — business logic

All classes in this sub-package are **pure Python** with no HA dependency, enabling lightweight unit tests without a running HA instance.

---

## 4. Data model

### Configuration keys (`const.py`)

| Key                         | Type         | Description                                     |
| --------------------------- | ------------ | ----------------------------------------------- |
| `hysteresis_on`             | float (°C)   | ON threshold below setpoint.                    |
| `hysteresis_off`            | float (°C)   | OFF threshold above setpoint.                   |
| `min_on_percent`            | float [0..1] | `on_percent` when algorithm says OFF.           |
| `max_on_percent`            | float [0..1] | `on_percent` when algorithm says ON.            |
| `min_on_duration_min`       | int (min)    | Minimum burn time before OFF allowed.           |
| `min_off_duration_min`      | int (min)    | Minimum off time before ignition allowed.       |
| `cooldown_duration_min`     | int (min)    | Extra cooldown added to `min_off_duration_min`. |
| `safety_room_temp`          | float (°C)   | Force OFF above this ambient temperature.       |
| `power_control_enabled`     | bool         | Enable fan/preset level control.                |
| `power_control_attribute`   | enum         | `fan_mode` or `preset_mode`.                    |
| `power_levels`              | list[str]    | Ordered level values (weakest → strongest).     |
| `power_default_level_index` | int          | Default level index when slope is unknown.      |
| `power_boost_enabled`       | bool         | Enable setpoint-rise boost.                     |
| `power_boost_duration_min`  | int (min)    | Boost duration.                                 |

### `PelletState` (persisted)

```json
{
  "is_heating": true,
  "current_level_index": 2,
  "last_on_at": "2026-01-15T19:32:11+01:00",
  "last_off_at": "2026-01-15T17:02:00+01:00",
  "last_reason": "below_on_threshold",
  "boost_until": null
}
```

Stored under key `vtherm_pellet_stove.<slug_of_vtherm_unique_id>` (HA `.storage/` directory).

---

## 5. Regulation algorithm

### Decision flowchart

```
Inputs: target, current, slope, hvac_mode, now, state
         │
         ▼
hvac_mode == "off" ──Yes──► on_percent=0  reason=hvac_off
         │
         No
         ▼
current ≥ safety_room_temp ──Yes──► on_percent=0  reason=safety  (override guard-rails)
         │
         No
         ▼
HysteresisDecider.decide(is_heating, current, target)
         │
    ┌────┴────┐
   ON        OFF
    │          │
    │ is_heating=False   is_heating=True
    │          │
CycleGuard    CycleGuard
.can_turn_on  .can_turn_off
    │              │
 No─┤           No─┤
    │              │
locked_off      locked_on (hold ON)
    │              │
 Yes─┘          Yes─┘
    │              │
 on_percent=1   on_percent=0
 reason=...     reason=...
```

### `HysteresisDecider`

- `decide(is_heating, current, target)` returns `HysteresisDecision(decision, reason, is_hold)`.
- `is_hold=True` means the stove maintains its current state (temperature within the dead-band).

### `CycleGuard`

```python
can_turn_off(now, state) → bool:
    elapsed = (now - state.last_on_at).total_seconds() / 60
    return elapsed >= min_on_duration_min

can_turn_on(now, state) → bool:
    elapsed = (now - state.last_off_at).total_seconds() / 60
    return elapsed >= (min_off_duration_min + cooldown_duration_min)
```

The safety override in `PelletRegulationController._compute` bypasses `can_turn_off` entirely.

---

## 6. HA lifecycle

### Startup sequence

```
HA boot
  └─ async_setup_entry (plugin)
       ├─ _register_factory → VThermAPI.register_prop_algorithm
       ├─ entry.async_on_unload → _async_update_options listener
       └─ (if CoreState.running) _reload_pellet_vtherms

VTherm setup (after plugin, dependency declared in manifest.json)
  └─ factory.create(thermostat_runtime)
       └─ PelletRegulationHandler.__init__
            ├─ handler.init_algorithm()        ← reads options, creates controller + Store
            ├─ handler.async_added_to_hass()   ← restore_state from Store
            ├─ handler.async_startup()         ← on_state_changed(True) → control_heating
            └─ handler.on_scheduler_ready(scheduler)
```

### Regulation cycle (per `cycle_min`)

```
VTherm.async_control_heating
  └─ handler.control_heating(timestamp, force)
       ├─ controller.calculate(target, current, slope, hvac_mode, now)
       ├─ thermostat.prop_algorithm = controller
       ├─ scheduler.start_cycle(hvac_mode, on_percent, force)
       │    └─ UnderlyingSwitch.turn_on/off
       │         └─ hass.services.async_call("climate", "set_hvac_mode", ...)
       ├─ _apply_power_level()   (if enabled and is_heating)
       │    └─ hass.services.async_call("climate", "set_fan_mode", ...)
       ├─ thermostat.update_custom_attributes()
       ├─ thermostat.async_write_ha_state()
       └─ store.async_save(controller.save_state())
```

---

## 7. Configuration UI

### Flow types

| Flow            | `unique_id`           | Purpose                                           |
| --------------- | --------------------- | ------------------------------------------------- |
| Global defaults | `DOMAIN`              | Created automatically on first install.           |
| Per-thermostat  | `DOMAIN-<vtherm_uid>` | Optional override for a specific thermostat.      |
| Options (both)  | n/a                   | Edit parameters in place; triggers VTherm reload. |

### VTherm reload logic (`_reload_pellet_vtherms`)

- Iterates over all `versatile_thermostat` config entries.
- Filters those with `CONF_PROP_FUNCTION == "pellet_regulation"`.
- Per-thermostat plugin entry: reloads only the matching VTherm unique_id.
- Global defaults entry: reloads all matching VTherms **except** those with a per-thermostat override.
- Only runs when `hass.state == CoreState.running`.

---

## 8. Persistent state

The `Store` key format is `vtherm_pellet_stove.<slugify(vtherm_unique_id)>`, version 1.

- Written after every `control_heating` call.
- Read once in `async_added_to_hass` and fed to `controller.restore_state`.
- Contains all fields of `PelletState` as ISO-8601 strings for datetimes.

---

## 9. Power level control

Implemented in `PowerMapper.choose_level_index(delta_t, slope)`:

| `delta_T = target − current` | `slope` (°C/h) | Level index                  |
| ---------------------------- | -------------- | ---------------------------- |
| ≥ +2.0                       | any            | last (max)                   |
| +1.0 .. +2.0                 | < +0.3         | second-to-last               |
| +1.0 .. +2.0                 | ≥ +0.3         | upper median                 |
| +0.3 .. +1.0                 | < +0.2         | median                       |
| +0.3 .. +1.0                 | ≥ +0.2         | lower median                 |
| −0.3 .. +0.3                 | any            | first (min)                  |
| < −0.3                       | any            | `None` (stove is OFF anyway) |

Anti-spam: `_apply_power_level` compares `current_level_index` with `_last_applied_level_index` and skips the service call if unchanged.

### Boost

`BoostManager.maybe_trigger` fires when `new_target − previous_target ≥ 0.5 °C`. It sets `state.boost_until = now + timedelta(minutes=power_boost_duration_min)`. While `boost_until > now`, `_compute_level_index` returns the last index (maximum level).

---

## 10. Testing strategy

| Layer               | Module                                                                                | Tools                                             |
| ------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Pure unit           | `pellet/hysteresis`, `pellet/cycle_guard`, `pellet/power_mapper`, `pellet/controller` | `pytest` (no HA)                                  |
| Handler integration | `handler.py`                                                                          | `pytest` + `unittest.mock`, Store patched         |
| Config flow         | `config_flow.py`                                                                      | `pytest-homeassistant-custom-component` (planned) |

### Running tests

```bash
# Install dev dependencies
pip install -r requirements_dev.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=custom_components/vtherm_pellet_stove --cov-report=term-missing
```

### Store mocking pattern

The real `homeassistant.helpers.storage.Store` requires a live HA event loop and `StorageManager`. Tests patch it at import time:

```python
@pytest.fixture(autouse=True)
def _patch_ha_store():
    def _make_store(*_args, **_kwargs):
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()
        return store

    with patch("custom_components.vtherm_pellet_stove.handler.Store", side_effect=_make_store):
        yield
```

---

## 11. Observability — Logs and debug entity

### 11.1 INFO/WARNING logs in `controller.py`

The `PelletRegulationController` emits HA-compatible logs according to this matrix:

| Level     | Condition                                         | Example                                                                                        |
| --------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `WARNING` | Safety high-temp → forced shutdown                | `Living Room - SAFETY: room temp 27.2°C ≥ 26.0°C → forced shutdown after 45 min of heating`    |
| `INFO`    | Real ignition (OFF → ON transition)               | `Living Room - Stove ignited (reason=below_on_threshold) after 27 min off [target=20.0 …]`     |
| `INFO`    | Real shutdown (ON → OFF transition)               | `Living Room - Stove off (reason=above_off_threshold) after 32 min of heating [target=20.0 …]` |
| `INFO`    | Shutdown delayed by `min_on` guard-rail           | `Living Room - Shutdown delayed (min_on guard): 15/30 min of heating`                          |
| `INFO`    | Ignition delayed by `min_off+cooldown` guard-rail | `Living Room - Ignition delayed (min_off+cooldown guard): 18/25 min off`                       |
| `DEBUG`   | Every `calculate()` call                          | `PelletController - calculate target=20.0 current=19.3 on_percent=1.0 …`                       |

`INFO` and `WARNING` logs are only emitted on a state change or a guard-rail block (anti-spam).

To see them in HA, configure the logger in `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.vtherm_pellet_stove: info
```

### 11.2 Debug `sensor` entity (DIAGNOSTIC)

Each VTherm using `pellet_regulation` automatically creates a sensor entity:

- **entity_id**: `sensor.<vtherm_name>_pellet_regulation_debug` (auto-generated by HA)
- **Category**: `DIAGNOSTIC` (visible in the device's Diagnostics tab)
- **State value**: current phase — `off`, `igniting`, `burning`, `cooldown`

**Phases**:

| Phase      | Condition                                                                 |
| ---------- | ------------------------------------------------------------------------- |
| `off`      | `is_heating = false` AND min_off+cooldown guard-rail elapsed              |
| `igniting` | `is_heating = true` AND elapsed < `min_on_duration_min` (recent ignition) |
| `burning`  | `is_heating = true` AND elapsed ≥ `min_on_duration_min`                   |
| `cooldown` | `is_heating = false` AND min_off+cooldown guard-rail still active         |

The entity also exposes all active parameters (hysteresis thresholds, guard-rail values, last decisions) as attributes, making it easy to debug directly from the HA UI.

---

## 12. Adding a new feature

### Adding a new configuration parameter

1. Add `CONF_MY_PARAM` and `DEFAULT_MY_PARAM` to `const.py` and `DEFAULT_OPTIONS`.
2. Add the voluptuous field + selector in `config_flow.py → build_options_schema`.
3. Add the translation string in `translations/en.json` and `translations/fr.json`.
4. Read the value in `handler.py → init_algorithm` and pass it to the appropriate constructor.
5. Update unit tests.

### Adding a new guard-rail or decision step

1. Implement the logic in a new file under `pellet/` (no HA imports).
2. Inject it into `PelletRegulationController.__init__` and call it from `_compute`.
3. Add unit tests that cover the new decision paths.
4. Update `handler.py` if the feature requires HA service calls.

### Adding cycle callbacks

`on_scheduler_ready` already registers `_on_cycle_start` / `_on_cycle_end`. Implement the callback bodies in `handler.py` and optionally delegate to a new method on `PelletRegulationController`.
