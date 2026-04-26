# Changelog

## [0.1.0] — 2026-04-26

### Added

- **Sprint 0 — Squelette**
  - `manifest.json`, `const.py`, `factory.py`, `handler.py` (stub), `config_flow.py`.
  - Parameterizable config-flow: hysteresis thresholds, pellet guard-rails (min on/off, cooldown, safety), power level control.
  - French and English translations (`translations/{fr,en}.json`).
  - Brand assets (placeholder PNGs).
  - `pyproject.toml`, `requirements_dev.txt`, `requirements_test.txt`, `hacs.json`.
  - Devcontainer for VS Code.
  - GitHub Actions CI: HACS validation, pytest, release workflow.
  - Architecture documentation in `tech-docs/plugin-architecture.md`.

- **Sprint 1 — Logique métier**
  - `pellet/state.py` — `PelletState` dataclass with `restore_state` / `save_state`.
  - `pellet/hysteresis.py` — `HysteresisDecider`: binary ON/OFF with parameterizable thresholds.
  - `pellet/cycle_guard.py` — `CycleGuard`: `can_turn_on` / `can_turn_off`, safety override.
  - `pellet/power_mapper.py` — `PowerMapper`: ΔT/slope → level index mapping table.
  - `pellet/boost.py` — `BoostManager`: temporary max-power boost after setpoint rise.
  - `pellet/controller.py` — `PelletRegulationController`: full orchestration, exposes `prop_algorithm` contract.
  - Unit tests covering all functional scenarios (scenarios 1–6, 8, 9 from the architecture doc).

- **Sprint 2 — Intégration HA**
  - `handler.py` fully implemented: `init_algorithm`, `async_added_to_hass`, `async_startup`, `remove`, `control_heating`, `on_state_changed`, `on_scheduler_ready`, `_apply_power_level`.
  - Option resolution strategy: per-thermostat entry > global defaults entry > `DEFAULT_OPTIONS`.
  - Power level anti-spam: service call skipped if level unchanged.
  - Persistent state via `homeassistant.helpers.storage.Store`.
  - `config_flow.py`: `PelletStoveConfigFlow` + `PelletStoveOptionsFlow` with `is_matching` override.
  - Integration tests: handler scenarios 7 (option reload) and 10 (HA restart restore).

- **Sprint 3 — Documentation & release**
  - `documentation/en/vtherm_pellet_stove.md` — full user guide in English.
  - `documentation/fr/vtherm_pellet_stove.md` — guide utilisateur complet en français.
  - `documentation/en/technical_doc.md` — developer/maintainer technical reference in English.
  - `documentation/fr/technical_doc.md` — documentation technique en français.
  - Updated `README.md` and `README.fr.md` with HACS / GitHub Release / License badges and links to all documentation files.

