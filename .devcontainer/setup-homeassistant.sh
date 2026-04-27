#!/usr/bin/env bash

set -euo pipefail

mkdir -p .homeassistant
ln -sfn ../custom_components .homeassistant/custom_components
ln -sfn ../../.devcontainer/lovelace_dashboards .homeassistant/.storage/lovelace_dashboards
ln -sfn ../../.devcontainer/lovelace.pellet_stove .homeassistant/.storage/lovelace.pellet_stove
