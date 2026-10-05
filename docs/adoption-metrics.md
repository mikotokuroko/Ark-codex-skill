# Adoption metrics

Track two separate measures:

- **Release downloads:** downloads of uploaded `Ark-Codex-Deskpet-*-source.zip` assets in this repository. Includes repeat downloads; not unique users or successful installations.
- **Skill installs:** installations reported by skills.sh for `mikotokuroko/Ark-codex-skill` / `ark-codex-skill`. Excludes manual installs and CLI telemetry opt-outs; not skill invocations.

Do not add these figures together as a user count. Both begin with the new distribution routes; historical use cannot be recovered. Developer validation uses `DISABLE_TELEMETRY=1`.

The README download badge shows GitHub downloads across **all release attachments**, including checksum files. For a résumé source-package count, use the ZIP-only query below. The release badge shows the latest stable release. Shields.io caches values, so badge updates may lag GitHub.

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

## Private opt-in counters

The macOS installer and direct `export_pet.py` workflow offer optional reporting, defaulting to **no**. Reports go to `https://ark-adoption.hoicheoklam.workers.dev/events`.

- `installation`: after a successful Mac app installation/launch. Counted once per local reporting state, not once per update. Deleting state or using another machine can count again. Windows scaffold installs and `npx skills add` alone are not measured.
- `pet_generation`: after a complete direct export succeeds. Failed exports and preflight-only runs are excluded. Legacy browser/WebM workflows are not measured.
- Payload: a random event ID and event type. The service adds a receipt timestamp. No prompts, character names, session data, file paths, or persistent cross-event user ID are stored.
- Cloudflare handles the network connection and sees the source IP; an edge rate limiter uses it transiently. Worker request logging is disabled and the counter database does not store IPs.
- Reporting failures never fail installation/export. Up to 100 pending events are saved locally; one is attempted per subsequent successful action, with a two-second network timeout. Retries reuse the event ID. Offline/opted-out clients and discarded queue entries are not counted.
- Noninteractive runs never assume consent. `ARK_DISABLE_REPORTING=1`, `DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, CI and pytest runs suppress sending.

Change consent from the full project:

```sh
.venv-macos/bin/python ark-codex-skill/scripts/adoption.py enable
.venv-macos/bin/python ark-codex-skill/scripts/adoption.py disable
.venv-macos/bin/python ark-codex-skill/scripts/adoption.py status
```

Disabling clears pending events. Previously received counts remain. On macOS, consent and pending events are in `~/Library/Application Support/Ark Codex Deskpet/adoption.json`. If an interrupted process leaves `adoption.lock`, reporting skips safely; remove that empty lock directory only after the installer/export has exited.

### Owner access

`GET /totals` requires `Authorization: Bearer <ADMIN_TOKEN>`. The token is a Worker secret and is never distributed with the app or committed. Read privately with:

```sh
python3 analytics/read_totals.py --token-file /path/to/private/admin-token
```

Omit `--token-file` to enter the token at a hidden prompt. Totals include `installation`, `pet_generation` and `as_of`. Use “reported opted-in installations” and “reported successful pet generations” in a résumé. Public event submission is rate-limited but cannot prove genuine usage: a distributed open-source client cannot keep a signing secret. These are adoption estimates, not audited unique users.

### Service maintenance

Worker source/config are in `analytics/`. SQLite Durable Objects persist and deduplicate each event kind separately. Deploy with `wrangler deploy --config analytics/wrangler.jsonc`; set/rotate the secret with `wrangler secret put ADMIN_TOKEN --config analytics/wrangler.jsonc`. Keep the Durable Object namespace and migration history to preserve counts. The v.0.2.0 source release includes reporting; the earlier v0.2.2-beta.1 archive does not.

## Résumé wording

“Extended an open-source Codex desktop pet project with macOS support, reaching X release downloads and Y skill installs through skills.sh.”

Use only verified values and retain the measurement date. Describe these as separate distribution metrics, not unique users.
