#!/usr/bin/env bash

set -u

# PostgreSQL startup helper for football_26 (macOS focused).
# Tries:
# 1) brew services (versioned and unversioned formulas)
# 2) pg_ctl with common data directories

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-football_26_dev}"
PGUSER="${PGUSER:-postgres}"

log() {
  printf '%s\n' "$1"
}

check_postgres() {
  if command -v pg_isready >/dev/null 2>&1; then
    if pg_isready -h "${PGHOST}" -p "${PGPORT}" -q; then
      return 0
    fi
  fi
  return 1
}

try_brew_services() {
  if ! command -v brew >/dev/null 2>&1; then
    log "Homebrew not found; skipping brew services."
    return 1
  fi

  local formulas=(
    "postgresql"
    "postgresql@17"
    "postgresql@16"
    "postgresql@15"
    "postgresql@14"
  )

  for formula in "${formulas[@]}"; do
    if brew list --formula "${formula}" >/dev/null 2>&1; then
      log "Trying brew services start ${formula}..."
      if brew services start "${formula}" >/dev/null 2>&1; then
        sleep 2
        if check_postgres; then
          log "Started PostgreSQL via brew services (${formula})."
          return 0
        fi
      fi
    fi
  done

  return 1
}

try_pg_ctl() {
  if ! command -v pg_ctl >/dev/null 2>&1; then
    log "pg_ctl not found; skipping manual start."
    return 1
  fi

  local brew_prefix=""
  if command -v brew >/dev/null 2>&1; then
    brew_prefix="$(brew --prefix 2>/dev/null || true)"
  fi

  local -a possible_dirs=(
    "/usr/local/var/postgres"
    "/opt/homebrew/var/postgres"
    "/usr/local/var/postgresql@17"
    "/usr/local/var/postgresql@16"
    "/usr/local/var/postgresql@15"
    "/usr/local/var/postgresql@14"
    "/opt/homebrew/var/postgresql@17"
    "/opt/homebrew/var/postgresql@16"
    "/opt/homebrew/var/postgresql@15"
    "/opt/homebrew/var/postgresql@14"
    "${HOME}/Library/Application Support/Postgres/var-17"
    "${HOME}/Library/Application Support/Postgres/var-16"
    "${HOME}/Library/Application Support/Postgres/var-15"
    "${HOME}/Library/Application Support/Postgres/var-14"
  )

  if [[ -n "${brew_prefix}" ]]; then
    possible_dirs+=(
      "${brew_prefix}/var/postgres"
      "${brew_prefix}/var/postgresql@17"
      "${brew_prefix}/var/postgresql@16"
      "${brew_prefix}/var/postgresql@15"
      "${brew_prefix}/var/postgresql@14"
    )
  fi

  local data_dir
  for data_dir in "${possible_dirs[@]}"; do
    if [[ -d "${data_dir}" && -f "${data_dir}/PG_VERSION" ]]; then
      log "Trying pg_ctl start with data dir: ${data_dir}"
      if pg_ctl -D "${data_dir}" -l "${data_dir}/server.log" start >/dev/null 2>&1; then
        sleep 2
        if check_postgres; then
          log "Started PostgreSQL with pg_ctl (${data_dir})."
          return 0
        fi
      fi
    fi
  done

  return 1
}

show_info() {
  cat <<EOF

PostgreSQL is running.
  Host: ${PGHOST}
  Port: ${PGPORT}
  User: ${PGUSER}
  Database: ${PGDATABASE}

Next steps:
  1) python scripts/recreate_database.py
  2) python scripts/apply_migrations.py
  3) uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

EOF
}

main() {
  log "Starting PostgreSQL for football_26..."

  if check_postgres; then
    log "PostgreSQL already running."
    show_info
    exit 0
  fi

  if try_brew_services; then
    show_info
    exit 0
  fi

  if try_pg_ctl; then
    show_info
    exit 0
  fi

  cat <<EOF

Failed to start PostgreSQL automatically.

Manual checks:
  - Is Postgres installed?      which psql
  - Is service running?         pg_isready -h ${PGHOST} -p ${PGPORT}
  - Start via Homebrew:         brew services start postgresql@16
  - Start manually with pg_ctl: pg_ctl -D /path/to/data start

EOF
  exit 1
}

main "$@"

