# Changelog

## 0.2.2

- Coordinate random walks with animation cycles; resting poses stay stationary,
  destinations stop movement, and manual interactions take priority.
- Add saved activity frequency, walking proportion, speed, distance, and pause
  controls under the new behavior settings tab.
- Support animation groups, independent pet copies, and optional sound effects.
- Cache cropped animation frames to avoid repeated PNG decoding.
- Restore mouse control through Show Pet after accidental click-through.
- Isolate the missing-repository test from the developer checkout and environment.

## 0.2.1

- Show all available animations in both macOS menus using Chinese/English labels.
  Include Special only for pets that provide it; menu actions respect manual
  overrides and resume the current animation policy after one cycle.

## 0.2.0

- Add a global saved “Follow Codex activity” toggle to both macOS menus.
  Inactive playback favors Relax, sleeps after five minutes, and uses Move and
  Interact while a local Codex task runs. Manual actions temporarily take over.
- Aggregate concurrent Codex task lifecycle events and respect the current host
  launch, including silent tasks, host exit and malformed or historical records.
- Support optional Special animations without breaking existing five-state pets.
- Include 德克萨斯「意志」 and 结城理 in the macOS pet library.
- Export compatible PRTS models directly to fixed-timestamp transparent frames,
  with animation discovery, version checks and deterministic visible preflight.
- Preserve the existing Windows runtime behavior.
