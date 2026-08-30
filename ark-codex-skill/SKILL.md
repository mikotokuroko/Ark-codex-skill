---
name: ark-codex-skill
description: Create transparent Arknights desktop pets from PRTS base-animation exports, install them into Ark Codex Deskpet on macOS, or scaffold the original Windows app. Use for operator export, WebM-to-PNG conversion, pet validation, library installation, and pet switching.
---

# Arknights Deskpet

Build a transparent Codex deskpet from PRTS operator models while preserving the
cross-platform `manifest.json` schema.

## Choose a Platform

- On macOS 13+ Apple silicon, use the installed `Ark Codex Deskpet.app` and the
  macOS workflow below. Store generated pets only in Application Support.
- On Windows, keep using the original `assets/deskpet-app` scaffold and Windows
  workflow. Do not copy macOS runtime paths or launchd behavior into it.

## Pet-Generation Workflow

1. Confirm the operator name and optional skin. Use `默认` when no skin is given.
2. Export the PRTS base animations `Default`, `Interact`, `Move`, `Relax`, `Sit`,
   and `Sleep` with `scripts/prts_export.py`.
3. Convert usable WebM files to 1000×1000 transparent PNG frames at 20 fps with
   `scripts/process_webm.py`. A broken tiny `Default` export may remain in the
   work directory; it is not mapped to a runtime state.
4. Validate the completed pet. It must contain `idle`, `interact`, `move`, `sit`,
   and `sleep`; every `count` entry must reference an intact PNG frame.
5. On macOS, install through `scripts/install_pet_macos.py`. It atomically replaces
   only the same-named user pet, excludes raw WebM files, and sends
   `refresh-library` to a running app.

If PRTS viewer controls change, read `references/prts-ui.md` before updating the
selectors in `scripts/prts_export.py`.

## macOS Commands

Use the repository-local `.venv-macos` created by `scripts/install_macos.sh`.
System Chrome is preferred at either supported application path; otherwise
Playwright Chromium is used from the local development environment and is never
bundled into the desktop app.

```bash
.venv-macos/bin/python ark-codex-skill/scripts/prts_export.py \
  "<operator>" --out work/webm

.venv-macos/bin/python ark-codex-skill/scripts/process_webm.py \
  --src work/webm --name "<operator>" --out "work/pets/<operator>"

.venv-macos/bin/python ark-codex-skill/scripts/install_pet_macos.py \
  "work/pets/<operator>"
```

User pets are installed in:

```text
~/Library/Application Support/Ark Codex Deskpet/Pets/
```

User pets override a bundled pet with the same Unicode name. The bundled default
pet remains read-only inside the app.

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
