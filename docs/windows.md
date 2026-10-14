# Ark Codex Deskpet — Windows

Requires Windows 10/11 x64. Extract the entire ZIP, then double-click **Ark Codex Deskpet.exe**. Keep `_internal` beside the executable. Python is not required for the packaged application.

The Windows build uses the same application and animation code as macOS: random walking and pauses, independent gravity, activity and walking settings, Codex activity following, animation groups and Special, multiple pet copies, scaling, mirroring, opacity, locking, click-through recovery, subtitles, sound/bubbles, pet library and acquisition.

Only **结城理** is bundled. Additional packs go in `%LOCALAPPDATA%\Ark Codex Deskpet\Pets`. Settings, cache and logs also live under `%LOCALAPPDATA%\Ark Codex Deskpet`; replacing the app folder keeps them intact.

Right-click the pet or use its notification-area icon for settings and the library. **Show Pet** restores mouse input after click-through is enabled. The tray-icon setting controls the Windows notification-area icon.

**Follow ChatGPT/Codex startup** registers a per-user startup watcher; no administrator privileges are needed. Keep the application at the same path while enabled. Disable the option before moving it, then enable it at the new location. The watcher checks for the Windows desktop processes every two seconds and only closes pets it launched itself. Manual launches remain independent. Turn this option off before deleting the application folder.

Fullscreen hiding follows the foreground window on the pet's monitor. Gravity uses that screen's bottom edge. Codex activity reads `%USERPROFILE%\.codex\sessions`; WSL/remote session directories are not monitored automatically.

## Generate new pets

As on macOS, the in-app acquisition tool needs a separate source checkout and Python environment. In the checkout run:

```powershell
py -3.11 -m venv .venv-windows
.venv-windows\Scripts\python.exe -m pip install -r requirements-windows.txt
.venv-windows\Scripts\python.exe -m playwright install chromium
```

Select that checkout in **Add Pet → Tool repository**. Export jobs run separately so the pet stays responsive. You can also copy previously exported packs into the user Pets folder and restart the app.

## Build from source

Run `packaging\build_windows.ps1` on Windows with Python 3.11 installed. The output is `dist\Ark Codex Deskpet\Ark Codex Deskpet.exe`. The GitHub Windows workflow runs shared feature tests, native click-through/process/startup tests, builds the executable, and tests the frozen app's launch, settings and IPC before creating a ZIP and checksum.

The shared runtime retains its existing source path `ark-codex-skill/assets/deskpet-app-macos/ark_deskpet`; Windows-specific integration is isolated in `windows_platform.py`. The older Windows template remains available for compatibility; the executable uses the shared runtime instead.
