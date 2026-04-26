# Changelog

## [0.1.0] — 2026-04-26

### Added

- Sprint 0: scaffolding of the `vtherm_pellet_stove` integration.
- `manifest.json`, `const.py`, `factory.py`, `handler.py` (stub), `config_flow.py`.
- Full parametrizable config-flow: hysteresis thresholds, pellet guard-rails (min on/off, cooldown, safety), power level control.
- French and English translations.
- Brand assets (placeholder PNGs).
- `pyproject.toml`, `requirements_dev.txt`, `requirements_test.txt`, `hacs.json`.
- Devcontainer for VS Code (Dockerfile, configuration.yaml, devcontainer.json).
- GitHub Actions CI: HACS validation, pytest, release workflow.
- Architecture documentation in `tech-docs/plugin-architecture.md`.
