---
name: ark-codex-skill
description: Create transparent Arknights desktop pets from PRTS base-animation exports, install them into Ark Codex Deskpet on macOS, or scaffold the original Windows app. Use for operator export, WebM-to-PNG conversion, pet validation, library installation, and pet switching.
---

# Arknights Deskpet

Build a transparent Codex deskpet from PRTS operator models while preserving the
cross-platform `manifest.json` schema.

## Installed Skill and Application Setup

When installed through `npx skills add`, this directory contains the skill scripts
and assets, but not the repository-root build configuration or Python environment.
Resolve script and reference paths relative to this SKILL.md, never the caller's
working directory.

On macOS, first locate the complete extracted release or repository checkout with
`requirements-macos.txt`, `packaging/`, and `ark-codex-skill/`. If its location is
unknown, ask the user where they extracted it. If missing, direct them to
https://github.com/mikotokuroko/Ark-codex-skill/releases and the README setup steps.
Run the Mac installer only from that complete project; do not run the copy inside
a standalone installed skill. The installer creates `<project>/.venv-macos`.
Use that environment's Python with absolute paths to this skill's export and
installation scripts. The repository-relative examples below assume the complete
project is the current directory.

## Choose a Platform

- On macOS 13+ Apple silicon, use the installed `Ark Codex Deskpet.app` and the
  macOS workflow below. Store generated pets only in Application Support.
- On Windows, keep using the original `assets/deskpet-app` scaffold and Windows
  workflow. Do not copy macOS runtime paths or launchd behavior into it.

## Pet-Generation Workflow

1. Confirm the operator name and optional skin. Use `默认` when no skin is given.
2. Run `scripts/export_pet.py` to discover and fetch the PRTS base model directly.
   It owns the local server and browser; desktop browser control is unnecessary.
   Export `Interact`, `Move`, `Relax`, `Sit`, and `Sleep`, plus `Special` whenever
   advertised. An absent Special is valid; a failed advertised animation is not.
3. Require the version check, animation inventory, visible test frame, and
   deterministic pose check to pass before full rendering. Frames use exact
   `frame_index / 20` timestamps and are 1000×1000 with transparency. Default
   is diagnostic only and is not mapped to a runtime state.
4. Validate the completed pet. It must contain `idle`, `interact`, `move`, `sit`,
   and `sleep`, with optional `special`; every `count` entry must reference an
   intact PNG frame. Inspect representative frames for appearance and clipping.
5. On macOS, install through `scripts/install_pet_macos.py`. It atomically replaces
   only the same-named user pet, excludes raw WebM files, and sends
   `refresh-library` to a running app.

For failures, read `references/direct-export.md`. The tested local adapter supports
Spine 3.8; another model version requires a matching adapter, never a guessed
combination. Stage diagnostics identify the failed step before a retry. Transfer
ownership explicitly when an export worker stalls, preserving its evidence.

The browser UI exporter `scripts/prts_export.py` and `scripts/process_webm.py`
remain an explicit fallback; read `references/prts-ui.md` before using it.
Reuse download authorization already provided by the user.

## macOS Commands

Use the repository-local `.venv-macos` created by `scripts/install_macos.sh`.
System Chrome is preferred at either supported application path; otherwise
Playwright Chromium is used from the local development environment and is never
bundled into the desktop app.

```bash
.venv-macos/bin/python ark-codex-skill/scripts/export_pet.py \
  "<operator>" --skin "默认" \
  --out "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/<unique-run>"

.venv-macos/bin/python ark-codex-skill/scripts/install_pet_macos.py \
  "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/<unique-run>/pet" \
  --name "<operator>"
```

User pets are installed in:

```text
~/Library/Application Support/Ark Codex Deskpet/Pets/
```

User pets override a bundled pet with the same Unicode name. The bundled default
pet remains read-only inside the app.

The app's saved **Follow Codex activity** menu toggle is off by default. Enabled
mode uses mostly Relax with occasional Interact/Sit/Sleep/Special, continuous Sleep
after five inactive minutes, and Move/Interact while any monitored local task runs.
Creating a pet does not change this setting.

## Windows Workflow

The original Windows template remains available unchanged under
`assets/deskpet-app`:

```bash
python scripts/scaffold_deskpet.py --target <project-dir> --pet "<operator>"
python scripts/setup_env.py <project-dir>
python scripts/prts_export.py "<operator>" --out <project-dir>/work/webm
python scripts/process_webm.py --src <project-dir>/work/webm \
  --name "<operator>" --out <project-dir>/pets/<operator>
<project-dir>/启动桌宠.bat
```
