# Pet export review checks

Use these checks when reviewing changes to the exporter, renderer or pet installer.

- The model header and renderer version must match. Load textures by their exact
  atlas names, including multiple texture pages when present.
- Before a full export, record the animation names and durations and render a
  visible test frame. Missing required animations are failures; absent Special is
  valid. An advertised Special that fails export is a failure.
- Advance animation time explicitly at `frame_index / fps`. Reset animation and
  skeleton state between actions. Wall-clock recording is not the canonical export.
- Check frame continuity, decoded image dimensions, alpha, duration and visible
  content. Review sampled frames across each animation for appearance and clipping;
  a readable PNG alone does not establish correct rendering.
- Video companions must preserve the canonical timeline within one output frame.
  Report any unavoidable timing difference explicitly.
- A fresh invocation must manage its own local server and browser and clean them up
  on success or failure. It must not depend on another terminal or fixed local port.
- Preserve working output until the replacement is complete and validated. Tests
  must cover failure before installation and older pets without Special.
- Verify the installed skill matches the tested repository files. Keep downloaded
  assets and generated pets outside the app bundle.

For stalled exports, require the failing stage, bounded elapsed time, error and
next diagnostic before a retry. Transfer ownership explicitly if a worker stalls;
retain its artifacts and findings so the replacement continues from evidence.
