#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PATH="${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

LABEL="${LABEL:-com.football26.news-monitor}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/football_26"
STDOUT_LOG="${LOG_DIR}/news_monitor_scheduler.out.log"
STDERR_LOG="${LOG_DIR}/news_monitor_scheduler.err.log"

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000/api}"
PGDATABASE="${PGDATABASE:-football_26_dev}"
FORCE="${FORCE:-false}"
RUN_DATE="${RUN_DATE:-}"
SOURCE_IDS="${SOURCE_IDS:-}"
SCHEDULE_HOUR="${SCHEDULE_HOUR:-8}"
SCHEDULE_MINUTE="${SCHEDULE_MINUTE:-0}"
API_HEALTHCHECK_TIMEOUT_SECONDS="${API_HEALTHCHECK_TIMEOUT_SECONDS:-5}"

launchd_target() {
  printf "gui/%s/%s" "$(id -u)" "${LABEL}"
}

trim() {
  printf "%s" "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

log_info() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "${STDOUT_LOG}"
}

log_error() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "${STDERR_LOG}" >&2
}

backend_health_url() {
  local origin="${API_BASE_URL%/}"
  if [[ "${origin}" == */api ]]; then
    origin="${origin%/api}"
  fi
  printf "%s/openapi.json" "${origin}"
}

backend_available() {
  curl -fsS -o /dev/null --max-time "${API_HEALTHCHECK_TIMEOUT_SECONDS}" "$(backend_health_url)" 2>/dev/null
}

build_payload() {
  local payload
  payload="{\"force\":${FORCE}}"

  if [[ -n "${RUN_DATE}" ]]; then
    payload="${payload%}}"
    payload+=",\"run_date\":\"${RUN_DATE}\"}"
  fi

  if [[ -n "${SOURCE_IDS}" ]]; then
    local ids_json=""
    local first=1
    local raw_id id
    IFS=',' read -r -a source_id_list <<< "${SOURCE_IDS}"
    for raw_id in "${source_id_list[@]}"; do
      id="$(trim "${raw_id}")"
      if [[ -z "${id}" ]]; then
        continue
      fi
      if [[ ${first} -eq 0 ]]; then
        ids_json+=","
      fi
      ids_json+="\"${id}\""
      first=0
    done
    payload="${payload%}}"
    payload+=",\"source_ids\":[${ids_json}]}"
  fi

  printf "%s" "${payload}"
}

run_now() {
  mkdir -p "${LOG_DIR}"
  local payload
  payload="$(build_payload)"
  log_info "POST ${API_BASE_URL}/news-monitor/run ${payload}"
  log_info "PGDATABASE=${PGDATABASE}"
  if ! backend_available; then
    log_info "Could not get the daily news because the backend is unavailable at ${API_BASE_URL}."
    return 0
  fi
  curl -fsS -X POST "${API_BASE_URL}/news-monitor/run" \
    -H "Content-Type: application/json" \
    -d "${payload}" | tee -a "${STDOUT_LOG}"
  printf "\n" | tee -a "${STDOUT_LOG}" >/dev/null
}

write_plist() {
  mkdir -p "$(dirname "${PLIST_PATH}")" "${LOG_DIR}"
  cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SCRIPT_DIR}/news_monitor_scheduler.sh</string>
    <string>run</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>API_BASE_URL</key>
    <string>${API_BASE_URL}</string>
    <key>PGDATABASE</key>
    <string>${PGDATABASE}</string>
    <key>FORCE</key>
    <string>${FORCE}</string>
EOF

  if [[ -n "${SOURCE_IDS}" ]]; then
    cat >> "${PLIST_PATH}" <<EOF
    <key>SOURCE_IDS</key>
    <string>${SOURCE_IDS}</string>
EOF
  fi

  cat >> "${PLIST_PATH}" <<EOF
  </dict>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${SCHEDULE_HOUR}</integer>
    <key>Minute</key>
    <integer>${SCHEDULE_MINUTE}</integer>
  </dict>

  <key>WorkingDirectory</key>
  <string>${REPO_ROOT}</string>

  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>

  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
EOF
}

install_scheduler() {
  write_plist
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
  printf "Installed %s at %s\n" "${LABEL}" "${PLIST_PATH}"
  printf "Scheduled daily at %02d:%02d local time\n" "${SCHEDULE_HOUR}" "${SCHEDULE_MINUTE}"
}

uninstall_scheduler() {
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  rm -f "${PLIST_PATH}"
  printf "Removed %s\n" "${PLIST_PATH}"
}

trigger_scheduler() {
  launchctl kickstart -k "$(launchd_target)"
}

status_scheduler() {
  if [[ ! -f "${PLIST_PATH}" ]]; then
    printf "Scheduler not installed: %s\n" "${PLIST_PATH}"
    exit 0
  fi
  printf "Plist: %s\n" "${PLIST_PATH}"
  printf "Logs: %s | %s\n" "${STDOUT_LOG}" "${STDERR_LOG}"
  launchctl print "$(launchd_target)" 2>/dev/null | sed -n '1,60p' || true
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <install|run|trigger|status|uninstall>

Commands:
  install    Write and load the launchd plist for a daily run
  run        Execute the news monitor API call immediately
  trigger    Ask launchd to run the installed job immediately
  status     Show installed plist and launchd status
  uninstall  Unload and remove the launchd plist

Environment overrides:
  API_BASE_URL    Default: http://127.0.0.1:8000/api
  API_HEALTHCHECK_TIMEOUT_SECONDS Default: 5
  PGDATABASE      Default: football_26_dev
  FORCE           Default: false
  RUN_DATE        Optional YYYY-MM-DD for direct 'run'
  SOURCE_IDS      Optional comma-separated source ids, e.g. espn_nfl_news,cbs_nfl_news
  SCHEDULE_HOUR   Default: 8
  SCHEDULE_MINUTE Default: 0
EOF
}

main() {
  local command="${1:-}"
  case "${command}" in
    install)
      install_scheduler
      ;;
    run)
      run_now
      ;;
    trigger)
      trigger_scheduler
      ;;
    status)
      status_scheduler
      ;;
    uninstall)
      uninstall_scheduler
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
