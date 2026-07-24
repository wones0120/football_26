#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "FAIL: no Python interpreter found (.venv/bin/python or python3)"
    exit 1
  fi
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "FAIL: npm is required for UI build checks"
  exit 1
fi

echo "[G1] Compile Python modules"
"$PYTHON_BIN" -m compileall "$ROOT_DIR/backend" "$ROOT_DIR/Database"

echo "[G1] Import FastAPI app"
"$PYTHON_BIN" -c "from backend.app.main import app; assert app is not None; print('fastapi-import-ok')"

echo "[G2] Run backend smoke tests"
"$PYTHON_BIN" -m unittest discover -s "$ROOT_DIR/backend/app/tests/product" -p "test_*.py" -v

echo "[G3] Build frontend"
npm --prefix "$ROOT_DIR/ui" run build

echo "PASS: health checks completed"
