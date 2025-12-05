#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/spotify_automation/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Virtualenv not found at ${PYTHON_BIN}."
  echo "Create one with: python3 -m venv spotify_automation/.venv && ${VENV_DIR}/bin/pip install -r requirements.txt"
  exit 1
fi

exec "${PYTHON_BIN}" "$@"
