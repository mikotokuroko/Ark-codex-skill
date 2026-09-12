# Included pet assets

The macOS build includes the original 予愿安洁莉娜 pet and these additional
transparent frame sequences:

| Character | Costume | Source |
|---|---|---|
| 德克萨斯 | 意志 | https://prts.wiki/w/德克萨斯 |
| 结城理 | 默认 | https://prts.wiki/w/结城理 |

结城理 metadata: https://torappu.prts.wiki/assets/char_spine/char_4217_makoto/meta.json

Texas includes 632 frames with Special; 结城理 includes 686 frames across five
states and does not advertise Special.

Additional pets live in `ark-codex-skill/assets/deskpet-app-macos/pets/`.
Each directory contains a manifest and only the PNG frames needed at runtime.
Raw source models, export servers, browser dependencies and user settings are
not bundled with the app.

Frames are sampled at fixed timestamps at 20 fps on a transparent 1000×1000
canvas. The five required states are idle (Relax), interact, move, sit and sleep;
Special is included whenever the source model advertises it.

Game artwork and character assets belong to their respective rights holders.
Their inclusion does not grant an open-source license to the underlying artwork.
PRTS provides the model viewer and source references; the exported frames retain
the original artwork. See the source pages for their rights notices.
