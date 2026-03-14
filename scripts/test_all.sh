#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi

"${ROOT}/scripts/test_contracts.sh" "$@"
"${ROOT}/scripts/test_runtime.sh" "$@"
"${ROOT}/scripts/test_perception.sh" "$@"
"${ROOT}/scripts/test_stm.sh" "$@"
"${ROOT}/scripts/test_adapters.sh" "$@"
"${ROOT}/scripts/test_knowledge.sh" "$@"
"${ROOT}/scripts/test_skills.sh" "$@"
"${ROOT}/scripts/test_orchestration.sh" "$@"
"${ROOT}/scripts/test_integration.sh" "$@"
