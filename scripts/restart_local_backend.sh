#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
RUNTIME_DIR="${TMPDIR:-/tmp}/football_26_local_backend"
API_PID_FILE="${RUNTIME_DIR}/api.pid"
WORKER_PID_FILE="${RUNTIME_DIR}/worker.pid"
API_LOG="${RUNTIME_DIR}/api.log"
WORKER_LOG="${RUNTIME_DIR}/worker.log"
ACTION="${1:-restart}"

mkdir -p "${RUNTIME_DIR}"

process_command() {
  ps -p "$1" -o command= 2>/dev/null || true
}

process_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | awk '/^n/ { sub(/^n/, ""); print; exit }'
}

repo_process_ancestor() {
  local pid="$1"
  local expected_pattern="$2"
  local command cwd parent attempt
  for attempt in {1..5}; do
    command="$(process_command "${pid}")"
    cwd="$(process_cwd "${pid}")"
    if [[ "${cwd}" == "${REPO_ROOT}" && "${command}" == *"${expected_pattern}"* ]]; then
      printf '%s\n' "${pid}"
      return 0
    fi
    parent="$(ps -p "${pid}" -o ppid= 2>/dev/null | tr -d ' ' || true)"
    if [[ -z "${parent}" || "${parent}" == "0" || "${parent}" == "1" || "${parent}" == "${pid}" ]]; then
      break
    fi
    pid="${parent}"
  done
  return 1
}

is_repo_process() {
  repo_process_ancestor "$1" "$2" >/dev/null
}

wait_for_exit() {
  local pid="$1"
  local attempt
  for attempt in {1..30}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

stop_pid() {
  local pid="$1"
  local label="$2"
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  printf 'Stopping %s (PID %s)...\n' "${label}" "${pid}"
  kill "${pid}"
  if ! wait_for_exit "${pid}"; then
    printf '%s did not stop after 6 seconds; refusing to force-kill it.\n' "${label}" >&2
    exit 1
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if [[ "${pid}" =~ ^[0-9]+$ ]]; then
      stop_pid "${pid}" "${label}"
    fi
    rm -f "${pid_file}"
  fi
}

stop_manually_started_api() {
  local pid api_pid
  pid="$(lsof -nP -iTCP:"${APP_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
  if [[ -z "${pid}" ]]; then
    return 0
  fi
  api_pid="$(repo_process_ancestor "${pid}" "uvicorn backend.app.main:app" || true)"
  if [[ -z "${api_pid}" ]]; then
    printf 'Port %s is owned by an unrelated process (PID %s); refusing to stop it.\n' "${APP_PORT}" "${pid}" >&2
    printf 'Command: %s\n' "$(process_command "${pid}")" >&2
    exit 1
  fi
  stop_pid "${api_pid}" "manually started football_26 API"
}

stop_manually_started_workers() {
  local pid
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    if is_repo_process "${pid}" "backend.app.worker"; then
      stop_pid "${pid}" "manually started football_26 worker"
    fi
  done < <(pgrep -f "backend\.app\.worker" 2>/dev/null || true)
}

stop_backend() {
  stop_pid_file "${WORKER_PID_FILE}" "football_26 worker"
  stop_pid_file "${API_PID_FILE}" "football_26 API"
  stop_manually_started_workers
  stop_manually_started_api
}

launchd_backend_available() {
  command -v launchctl >/dev/null 2>&1 &&
    launchctl print "gui/$(id -u)/com.football26.api" >/dev/null 2>&1 &&
    launchctl print "gui/$(id -u)/com.football26.worker" >/dev/null 2>&1
}

submitted_backend_available() {
  launchd_backend_available &&
    launchctl print "gui/$(id -u)/com.football26.api" 2>/dev/null | rg -q 'type = Submitted' &&
    launchctl print "gui/$(id -u)/com.football26.worker" 2>/dev/null | rg -q 'type = Submitted'
}

start_submitted_backend() {
  # A shell-launched nohup child can be reaped with its parent by a supervised
  # terminal. Submit both processes to the user's launchd domain instead.
  launchctl submit -l com.football26.api -o "${API_LOG}" -e "${API_LOG}" -- \
    /bin/zsh -c 'cd "$1" && exec env PYTHONHASHSEED=0 "$2" -m uvicorn backend.app.main:app --host "$3" --port "$4"' \
    _ "${REPO_ROOT}" "${PYTHON_BIN}" "${APP_HOST}" "${APP_PORT}"
  launchctl submit -l com.football26.worker -o "${WORKER_LOG}" -e "${WORKER_LOG}" -- \
    /bin/zsh -c 'cd "$1" && exec env PYTHONHASHSEED=0 "$2" -m backend.app.worker' \
    _ "${REPO_ROOT}" "${PYTHON_BIN}"
  local attempt
  for attempt in {1..50}; do
    if curl -fsS --max-time 1 "http://${APP_HOST}:${APP_PORT}/api/health" >/dev/null 2>&1 &&
      launchctl print "gui/$(id -u)/com.football26.worker" 2>/dev/null | rg -q 'state = running'; then
      printf 'Launchd-submitted API and worker are healthy.\n'
      return 0
    fi
    sleep 0.2
  done
  printf 'Launchd-submitted backend did not become healthy. Recent API log:\n' >&2
  tail -n 30 "${API_LOG}" >&2 || true
  exit 1
}

restart_launchd_backend() {
  local scope="${1:-backend}"
  launchctl setenv PYTHONHASHSEED 0
  local restart_status=0
  if [[ "${scope}" != "api" ]]; then
    launchctl kickstart -k "gui/$(id -u)/com.football26.worker" || restart_status=$?
  fi
  launchctl kickstart -k "gui/$(id -u)/com.football26.api" || restart_status=$?
  launchctl unsetenv PYTHONHASHSEED
  if [[ "${restart_status}" -ne 0 ]]; then
    printf 'Unable to restart launchd-managed backend services.\n' >&2
    exit "${restart_status}"
  fi
  local attempt
  for attempt in {1..50}; do
    if curl -fsS --max-time 1 "http://${APP_HOST}:${APP_PORT}/api/health" >/dev/null 2>&1; then
      printf 'Launchd-managed %s restarted; API is healthy.\n' "${scope}"
      return 0
    fi
    sleep 0.2
  done
  printf 'Launchd-managed API did not become healthy.\n' >&2
  exit 1
}

start_backend() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'Python virtual environment not found at %s\n' "${PYTHON_BIN}" >&2
    exit 1
  fi

  # Stable Python hash order keeps parallel CBC tie resolution reproducible.
  export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"

  printf 'Starting football_26 API on http://%s:%s...\n' "${APP_HOST}" "${APP_PORT}"
  (
    cd "${REPO_ROOT}"
    nohup "${PYTHON_BIN}" -m uvicorn backend.app.main:app \
      --host "${APP_HOST}" --port "${APP_PORT}" >"${API_LOG}" 2>&1 &
    echo "$!" >"${API_PID_FILE}"
  )

  printf 'Starting durable projection/optimizer worker...\n'
  (
    cd "${REPO_ROOT}"
    nohup "${PYTHON_BIN}" -m backend.app.worker >"${WORKER_LOG}" 2>&1 &
    echo "$!" >"${WORKER_PID_FILE}"
  )

  local attempt
  for attempt in {1..50}; do
    if curl -fsS --max-time 1 "http://${APP_HOST}:${APP_PORT}/api/health" >/dev/null 2>&1; then
      printf 'Backend is healthy.\n'
      printf 'API log: %s\n' "${API_LOG}"
      printf 'Worker log: %s\n' "${WORKER_LOG}"
      return 0
    fi
    sleep 0.2
  done

  printf 'Backend did not become healthy. Recent API log:\n' >&2
  tail -n 30 "${API_LOG}" >&2 || true
  exit 1
}

show_status() {
  if launchd_backend_available; then
    local api_pid worker_pid
    api_pid="$(launchctl list | awk '$3 == "com.football26.api" { print $1 }')"
    worker_pid="$(launchctl list | awk '$3 == "com.football26.worker" { print $1 }')"
    printf 'API: launchd-managed (PID %s)\n' "${api_pid:--}"
    printf 'Worker: launchd-managed (PID %s)\n' "${worker_pid:--}"
    return 0
  fi
  if curl -fsS --max-time 1 "http://${APP_HOST}:${APP_PORT}/api/health" >/dev/null 2>&1; then
    printf 'API: healthy at http://%s:%s\n' "${APP_HOST}" "${APP_PORT}"
  else
    printf 'API: not responding at http://%s:%s\n' "${APP_HOST}" "${APP_PORT}"
  fi
  if [[ -f "${WORKER_PID_FILE}" ]] && kill -0 "$(cat "${WORKER_PID_FILE}")" 2>/dev/null; then
    printf 'Worker: running (PID %s)\n' "$(cat "${WORKER_PID_FILE}")"
  else
    printf 'Worker: not managed by this script\n'
  fi
}

case "${ACTION}" in
  start)
    if launchd_backend_available; then
      restart_launchd_backend
    elif [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
      stop_backend
      start_submitted_backend
    else
      stop_manually_started_api
      start_backend
    fi
    ;;
  stop)
    if submitted_backend_available; then
      launchctl remove com.football26.worker
      launchctl remove com.football26.api
    elif launchd_backend_available; then
      printf 'Backend is launchd-managed; stop it with launchctl instead.\n' >&2
      exit 1
    else
      stop_backend
    fi
    ;;
  restart)
    if launchd_backend_available; then
      restart_launchd_backend
    elif [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
      stop_backend
      start_submitted_backend
    else
      stop_backend
      start_backend
    fi
    ;;
  status)
    show_status
    ;;
  reload-api)
    # Route-only source reload must leave durable worker jobs running.
    if launchd_backend_available; then
      restart_launchd_backend api
    else
      printf 'API-only reload requires the established launchd-managed local backend; no processes were stopped.\n' >&2
      exit 1
    fi
    ;;
  *)
    printf 'Usage: %s [start|stop|restart|status|reload-api]\n' "$0" >&2
    exit 2
    ;;
esac
