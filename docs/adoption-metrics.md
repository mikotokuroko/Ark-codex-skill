# Adoption metrics

Track two separate measures:

- **Release downloads:** downloads of uploaded `Ark-Codex-Deskpet-*-source.zip` assets in this repository. Includes repeat downloads; not unique users or successful installations.
- **Skill installs:** installations reported by skills.sh for `mikotokuroko/Ark-codex-skill` / `ark-codex-skill`. Excludes manual installs and CLI telemetry opt-outs; not skill invocations.

Do not add these figures together as a user count. Both begin with the new distribution routes; historical use cannot be recovered. Developer validation uses `DISABLE_TELEMETRY=1`.

The README download badge shows GitHub downloads across **all release attachments**, including checksum files. For a résumé source-package count, use the ZIP-only query below. The release badge includes prereleases. Shields.io caches values, so badge updates may lag GitHub.

## Read release downloads

With GitHub CLI installed, save a dated copy of the asset counts:

```sh
gh api --paginate repos/mikotokuroko/Ark-codex-skill/releases \
  --jq '.[] | select(.draft == false) | .tag_name as $tag | .assets[] | select(.name | test("^Ark-Codex-Deskpet-.*-source\\.zip$")) | {release: $tag, asset: .name, downloads: .download_count, url: .browser_download_url}'
```

Sum the `downloads` values for the cumulative source-package download count. Exclude checksum files. Keep old release assets; replacing or deleting them loses their counters. Save snapshots with a UTC date when using a figure in a résumé.

## Read skill installs

Open the [skill listing](https://skills.sh/mikotokuroko/ark-codex-skill/ark-codex-skill), or search [skills.sh](https://skills.sh) for `mikotokuroko/Ark-codex-skill` and select `ark-codex-skill`. Confirm the owner, metric label, and time window shown. Save that label, count, date, and page URL together. A listing may not appear until eligible real installations have been reported and indexed; do not treat an absent listing as proof of zero installs.

The recommended installation command is:

```sh
npx skills add mikotokuroko/Ark-codex-skill --skill ark-codex-skill --agent codex --global
```

No per-invocation reporting has been added to the app or export scripts.

## Résumé wording

“Extended an open-source Codex desktop pet project with macOS support, reaching X release downloads and Y skill installs through skills.sh.”

Use only verified values and retain the measurement date. Describe these as separate distribution metrics, not unique users.
