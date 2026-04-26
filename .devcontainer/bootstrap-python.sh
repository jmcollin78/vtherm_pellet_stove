#!/usr/bin/env bash

set -euo pipefail

VENV_DIR="/workspaces/vtherm_pellet_stove/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
	python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

bash .devcontainer/setup-homeassistant.sh

python -m pip install --upgrade pip
python -m pip install -r requirements_test.txt