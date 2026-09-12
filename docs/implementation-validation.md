# macOS 0.2.0 validation

Verified 2026-09-12. The Windows runtime remains unchanged.

- Full suite: 78 passing tests, including deterministic scheduling, both Qt menus,
  persistence, concurrent/silent tasks, host boundaries and malformed logs.
- PyInstaller build contains three pets. All 1,597 bundled PNG frames decode with
  transparency and pass manifest validation.
- Texas 意志: 632 frames — Relax 120, Interact 34, Move 20, Sit 120, Sleep 80,
  Special 258 (12.9 seconds).
- 结城理 默认: 686 frames — Relax 160, Interact 126, Move 160, Sit 160, Sleep 80.
  The source does not advertise Special. The zero-duration Default is excluded.
- The new exports use 1000×1000 transparent frames at fixed 20 fps timestamps,
  with visible preflight, deterministic pose reset and clipping checks.
- 结城理 was fetched from PRTS CDN metadata using `--model-id char_4217_makoto`.
  The normal wiki page returned HTTP 403; direct CDN metadata and the complete
  export succeeded. Spine 3.8.99 matches the bundled 3.8 renderer.
- Recoverable repository, app, skill, pet and settings backups were retained
  outside Git before modifying or installing targets.

Enable **Follow Codex activity** / **跟随 Codex 活动** in either menu. It defaults
off and applies across characters. Existing user preferences survive upgrades.
