#!/usr/bin/env bash

set -euo pipefail


source /workspaces/vtherm_pellet_stove/.venv/bin/activate

bash .devcontainer/setup-homeassistant.sh

python -m pip install --upgrade pip
python -m pip install -r requirements_test.txt