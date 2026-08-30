#!/bin/bash
# Uninstall Ark Codex Deskpet while preserving user pets by default.

set -euo pipefail

readonly APP_NAME="Ark Codex Deskpet"
readonly TARGET_APP="${HOME}/Applications/${APP_NAME}.app"
readonly SUPPORT_DIR="${HOME}/Library/Application Support/${APP_NAME}"
readonly CACHE_DIR="${HOME}/Library/Caches/${APP_NAME}"
readonly LOG_DIR="${HOME}/Library/Logs/${APP_NAME}"
readonly AGENT_FILE="${HOME}/Library/LaunchAgents/com.astrariax.arkcodexdeskpet.watcher.plist"

usage() {
  echo "用法：$0 [--purge-data]"
}

main() {
  local purge_data=false
  if (( $# > 1 )); then
    usage >&2
    return 2
  fi
  if (( $# == 1 )); then
    [[ "${1}" == "--purge-data" ]] || {
      usage >&2
      return 2
    }
    purge_data=true
  fi

  if [[ -x "${TARGET_APP}/Contents/MacOS/${APP_NAME}" ]]; then
    "${TARGET_APP}/Contents/MacOS/${APP_NAME}" \
      --command shutdown >/dev/null 2>&1 || true
  fi
  launchctl bootout "gui/$(id -u)" "${AGENT_FILE}" >/dev/null 2>&1 || true
  rm -f -- "${AGENT_FILE}"
  rm -rf -- "${TARGET_APP}" "${CACHE_DIR}" "${LOG_DIR}"
  if [[ "${purge_data}" == true ]]; then
    rm -rf -- "${SUPPORT_DIR}"
    echo "已卸载，并删除设置和用户桌宠。"
  else
    echo "已卸载；设置和用户桌宠仍保留在：${SUPPORT_DIR}"
  fi
}

main "$@"
