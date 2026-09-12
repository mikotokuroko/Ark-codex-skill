# Direct PRTS export

`scripts/export_pet.py` is the primary route. Run its `--help` for arguments.
An output directory must be new; working pets are never overwritten by rendering.
The final `pet/` directory is the installable package; `assets/`, `runtime/`,
`preflight.png` and `export.json` retain provenance outside the runtime pet.
When a PRTS page is blocked but its published model ID is known, pass `--model-id` (for example, `--model-id char_4217_makoto`) to read the official CDN metadata directly.

## Stages and failure checks

1. **Discovery:** read the operator page's `spine-root` model ID or legacy
   `SPINEDATA`. Select the requested skin's 基建 model. Resolve current model URLs
   from metadata rather than copying another operator's asset names.
2. **Assets:** use a browser User-Agent for CDN requests. Each request has a
   30-second timeout and at most two attempts, with the error logged before retry.
   Atlas pages supply the exact texture filenames, including multiple pages.
3. **Compatibility:** read the skeleton header before rendering. The included
   PRTS adapter supports Spine 3.8 and is checksummed. A 3.5 skeleton is not
   compatible. Use PRTS's current converted model or add a tested matching adapter.
4. **Preflight:** require all five base animations, finite positive durations,
   a visible Relax frame and a repeatable pose after another animation. `--preflight`
   stops after these checks and saves a preview. Inspect this before a full export
   when first using a new model family or adapter.
5. **Frames:** reset pose state and sample exact timestamps. Fit a shared camera
   over the selected animation bounds, leaving padding for effects. Fail on clipped
   frames or entirely blank animations. Individual transparent effect frames can
   be valid; inspect more than the first frame.
6. **Install:** validate `pet/`, then use `install_pet_macos.py`. Optional Special
   has the same manifest/PNG checks as the five required states.

## Reproduce with local assets

Pass `--source /path/to/source.json` to bypass network discovery. The JSON contains
`skeleton`, `atlas`, and an optional internal `skin` name. Asset values can be HTTP
URLs or paths relative to that JSON file. Texture paths come from the atlas.
The command still creates and closes its own ephemeral server and browser.
Every completed run saves a `source.json` referencing its local asset copies;
pass that file to a subsequent run to reproduce it without downloading again.

Canonical output is the PNG sequence and its manifest. A video companion should
be encoded from that sequence at the manifest frame rate; real-time browser
recording introduces drift and must not be presented as the exact timeline.

## Ownership and diagnostics

One worker owns an export. Report completed stages, measured failures and the
next diagnostic. On a repeated failure, inspect metadata, version and rendering
errors before retrying. A stalled worker hands off paths and findings; the next
owner continues from that evidence. Keep troubleshooting here instead of adding
operator-specific instructions to global AGENTS.md.

Reviewer checks live in the repository's `docs/export-validation.md`.
