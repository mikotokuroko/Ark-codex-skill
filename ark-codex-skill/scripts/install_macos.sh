#!/bin/bash
# Build, ad-hoc sign, install, and launch Ark Codex Deskpet for macOS.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly PYTHON="/opt/homebrew/opt/python@3.11/bin/python3.11"
readonly VENV="${REPOSITORY}/.venv-macos"
readonly PIP="${VENV}/bin/pip"
readonly VENV_PYTHON="${VENV}/bin/python"
readonly PYINSTALLER="${VENV}/bin/pyinstaller"
readonly APP_NAME="Ark Codex Deskpet.app"
readonly BUILT_APP="${REPOSITORY}/dist/${APP_NAME}"
readonly TARGET_DIR="${HOME}/Applications"
readonly TARGET_APP="${TARGET_DIR}/${APP_NAME}"
readonly SUPPORT_DIR="${HOME}/Library/Application Support/Ark Codex Deskpet"
readonly SETTINGS_FILE="${SUPPORT_DIR}/settings.json"
readonly AGENT_FILE="${HOME}/Library/LaunchAgents/com.astrariax.arkcodexdeskpet.watcher.plist"

fail() {
  echo "错误：$*" >&2
  exit 1
}

validate_host() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "仅支持 macOS"
  [[ "$(uname -m)" == "arm64" ]] || fail "仅支持 Apple silicon (arm64)"
  local version
  local major
  version="$(sw_vers -productVersion)"
  major="${version%%.*}"
  (( major >= 13 )) || fail "需要 macOS 13 或更高版本"
  [[ -x "${PYTHON}" ]] || fail "找不到 Homebrew Python 3.11：${PYTHON}"
  [[ "$(${PYTHON} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.11" ]] || fail "需要 Python 3.11"
  xcode-select -p >/dev/null 2>&1 || fail "需要 Xcode Command Line Tools"
  command -v codesign >/dev/null || fail "找不到 codesign"
  command -v lipo >/dev/null || fail "找不到 lipo"
  command -v plutil >/dev/null || fail "找不到 plutil"
}

create_environment() {
  if [[ -e "${VENV}" ]]; then
    [[ "${VENV}" == "${REPOSITORY}/.venv-macos" ]] || fail "虚拟环境路径异常"
    rm -rf -- "${VENV}"
  fi
  "${PYTHON}" -m venv "${VENV}"
  "${PIP}" install --no-cache-dir --requirement "${REPOSITORY}/requirements-macos.txt"
  if [[ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" && ! -x "/Applications/Chromium.app/Contents/MacOS/Chromium" ]]; then
    PLAYWRIGHT_BROWSERS_PATH="${REPOSITORY}/.playwright-browsers" \
      "${VENV_PYTHON}" -m playwright install chromium
  fi
}

build_bundle() {
  rm -rf -- "${REPOSITORY}/build" "${REPOSITORY}/dist"
  PYINSTALLER_CONFIG_DIR="${REPOSITORY}/.pyinstaller" \
    "${PYINSTALLER}" --noconfirm --clean \
    "${REPOSITORY}/packaging/ArkCodexDeskpet.spec"
  [[ -d "${BUILT_APP}" ]] || fail "PyInstaller 未生成应用"
  [[ -x "${REPOSITORY}/dist/ArkCodexWatcher" ]] || fail "未生成 watcher"
  mkdir -p "${BUILT_APP}/Contents/Helpers"
  cp "${REPOSITORY}/dist/ArkCodexWatcher" \
    "${BUILT_APP}/Contents/Helpers/ArkCodexWatcher"
  chmod 755 "${BUILT_APP}/Contents/Helpers/ArkCodexWatcher"
  if find "${BUILT_APP}" -type f -iname '*.webm' -print -quit | grep -q .; then
    fail "应用包中不应包含 WebM 文件"
  fi
}

verify_architecture() {
  local item
  local description
  while IFS= read -r -d '' item; do
    description="$(file "${item}")"
    if [[ "${description}" == *"Mach-O"* ]]; then
      lipo "${item}" -verify_arch arm64 || fail "非 arm64 可执行文件：${item}"
    fi
  done < <(find "${BUILT_APP}" -type f -perm -111 -print0)
}

sign_and_verify() {
  codesign --force --sign - --timestamp=none \
    "${BUILT_APP}/Contents/Helpers/ArkCodexWatcher"
  codesign --force --deep --sign - --timestamp=none "${BUILT_APP}"
  plutil -lint "${BUILT_APP}/Contents/Info.plist"
  plutil -lint \
    "${REPOSITORY}/packaging/com.astrariax.arkcodexdeskpet.watcher.plist"
  codesign --verify --deep --strict --verbose=2 "${BUILT_APP}"
  file "${BUILT_APP}/Contents/MacOS/Ark Codex Deskpet"
  lipo "${BUILT_APP}/Contents/MacOS/Ark Codex Deskpet" -info
  file "${BUILT_APP}/Contents/Helpers/ArkCodexWatcher"
  lipo "${BUILT_APP}/Contents/Helpers/ArkCodexWatcher" -info
}

close_existing_app() {
  if [[ -x "${TARGET_APP}/Contents/MacOS/Ark Codex Deskpet" ]]; then
    "${TARGET_APP}/Contents/MacOS/Ark Codex Deskpet" \
      --command shutdown >/dev/null 2>&1 || true
    local attempt
    for (( attempt = 0; attempt < 20; attempt++ )); do
      [[ ! -e "${HOME}/Library/Caches/Ark Codex Deskpet/instance.json" ]] && break
      sleep 0.25
    done
  fi
}

install_bundle() {
  local staging="${TARGET_DIR}/.${APP_NAME}.installing"
  local backup="${TARGET_DIR}/.${APP_NAME}.previous"
  mkdir -p "${TARGET_DIR}"
  rm -rf -- "${staging}" "${backup}"
  ditto "${BUILT_APP}" "${staging}"
  if [[ -e "${TARGET_APP}" ]]; then
    mv "${TARGET_APP}" "${backup}"
  fi
  if ! mv "${staging}" "${TARGET_APP}"; then
    [[ -e "${backup}" ]] && mv "${backup}" "${TARGET_APP}"
    fail "安装应用失败"
  fi
  rm -rf -- "${backup}"
}

main() {
  validate_host
  local first_install=false
  [[ ! -e "${SETTINGS_FILE}" ]] && first_install=true
  create_environment
  build_bundle
  verify_architecture
  sign_and_verify
  close_existing_app
  install_bundle
  if [[ "${first_install}" == true && -e "${AGENT_FILE}" ]]; then
    launchctl bootout "gui/$(id -u)" "${AGENT_FILE}" >/dev/null 2>&1 || true
    rm -f -- "${AGENT_FILE}"
  fi
  open "${TARGET_APP}"
  echo "已安装并启动：${TARGET_APP}"
  echo "用户数据保留在：${SUPPORT_DIR}"
  "${VENV_PYTHON}" "${SCRIPT_DIR}/adoption.py" installation || true
}

main "$@"
