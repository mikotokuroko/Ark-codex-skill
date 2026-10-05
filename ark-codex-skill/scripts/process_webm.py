#!/usr/bin/env python3
"""Convert PRTS WebM exports into transparent PNG frames for a deskpet."""

import argparse
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import socketserver
import sys
import threading
import tempfile
import urllib.parse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright is required: run 'pip install playwright' first")

FPS = 20
SIZE = 1000
SUPPORTED_FPS = (20, 60)
STATE_MAP = [
    ("Special", "special"),
    ("Relax", "idle"),
    ("Interact", "interact"),
    ("Move", "move"),
    ("Sit", "sit"),
    ("Sleep", "sleep"),
]

HTML = """<!doctype html>
<html>
<body style="margin:0">
<video id="v" muted playsinline preload="auto"></video>
<canvas id="c"></canvas>
<script>
const SIZE = %d;
const v = document.getElementById('v');
const c = document.getElementById('c');
c.width = SIZE;
c.height = SIZE;
const ctx = c.getContext('2d');
async function capture(src) {
  v.src = src;
  if (v.readyState < 1) {
    await new Promise((res) => v.addEventListener('loadedmetadata', res, { once: true }));
  }
  const frames = [];
  let minX = SIZE, minY = SIZE, maxX = -1, maxY = -1;
  let done;
  const ended = new Promise((res) => { done = res; });
  v.addEventListener('ended', done, { once: true });
  function step(now, meta) {
    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.drawImage(v, 0, 0, SIZE, SIZE);
    const data = ctx.getImageData(0, 0, SIZE, SIZE).data;
    for (let y = 0; y < SIZE; y += 2) {
      for (let x = 0; x < SIZE; x += 2) {
        const a = data[(y * SIZE + x) * 4 + 3];
        if (a > 10) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    frames.push({ t: meta.mediaTime, url: c.toDataURL('image/png') });
    if (!v.ended) v.requestVideoFrameCallback(step);
  }
  v.requestVideoFrameCallback(step);
  await v.play();
  await ended;
  return {
    duration: v.duration,
    frames,
    bbox: maxX >= 0 ? [minX, minY, maxX, maxY] : null
  };
}
window.capture = capture;
</script>
</body>
</html>
""" % SIZE


def find_chrome():
    candidates = [
        os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def pick_frames(count, duration, frames):
    max_t = max(0.01, duration - 0.02)
    out = []
    for i in range(count):
        target = (i / count) * max_t
        best = min(frames, key=lambda f: abs(f["t"] - target))
        out.append(best["url"])
    return out


def state_name(token):
    known = dict(STATE_MAP)
    if token in known:
        return known[token]
    state = ''.join(ch.lower() if ch.isalnum() else '_' for ch in token).strip('_')
    if not state:
        raise ValueError("animation name has no usable state")
    return state


def discover_state_files(src, group=None, operator=None):
    """Discover all advertised WebM actions, retaining additional action names."""
    state_files = {}
    tokens = [token for token, _ in STATE_MAP]
    for fname in sorted(os.listdir(src)):
        if not fname.lower().endswith('.webm'):
            continue
        stem = os.path.splitext(fname)[0]
        if operator and operator.lower() not in stem.lower():
            continue
        full = os.path.join(src, fname)
        if os.path.getsize(full) < 1000:
            if 'special' in fname.lower():
                raise ValueError('advertised Special export is broken: ' + fname)
            continue
        parts = [p for p in stem.split('-') if p]
        if parts and parts[-1].lower().startswith('x') and parts[-1][1:].isdigit():
            parts.pop()
        if group:
            if group.lower() not in (p.lower() for p in parts):
                continue
            index = next(i for i, p in enumerate(parts) if p.lower() == group.lower())
            parts = parts[index + 1:]
        token = next((t for t in tokens if t.lower() in stem.lower()), None)
        if group or token is None:
            token = parts[-1] if parts else stem
        state = state_name(token)
        if state in state_files:
            raise ValueError(f'duplicate animation state {state!r}: {fname} and {state_files[state]}')
        state_files[state] = fname
    return state_files


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, format, *args):
        pass


def ensure_group_layout(pet_dir, manifest):
    if not isinstance(manifest.get('groups'), dict) and isinstance(manifest.get('states'), dict):
        legacy = Path(pet_dir) / 'frames'
        grouped = legacy / 'default'
        if legacy.is_dir():
            shutil.copytree(legacy, grouped, dirs_exist_ok=True)
        manifest['groups'] = {'default': dict(manifest['states'])}


def run(src, name, out, group=None, fps=FPS):
    if fps not in SUPPORTED_FPS:
        raise ValueError(f'FPS must be one of {SUPPORTED_FPS}, got {fps}')
    if group and (os.path.basename(group) != group or group in {'.', '..'}):
        raise ValueError(f'unsafe group name: {group!r}')
    destination = Path(out).expanduser().resolve()
    staging_root = None
    if group:
        staging_root = Path(tempfile.mkdtemp(prefix='.webm-export-', dir=destination.parent))
        pet_dir = str(staging_root / 'pet')
        if destination.exists():
            shutil.copytree(destination, pet_dir, dirs_exist_ok=True)
    else:
        pet_dir = str(destination)
    frames_dir = os.path.join(pet_dir, "frames")
    webm_dir = os.path.join(pet_dir, "webm")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(webm_dir, exist_ok=True)

    state_files = discover_state_files(src, group, name)
    if not state_files:
        sys.exit("no valid WebM files found in " + src)
    missing = {"idle", "interact", "move", "sit", "sleep"} - state_files.keys()
    if missing and not group:
        sys.exit("missing required animations: " + ", ".join(sorted(missing)))

    for fname in state_files.values():
        source_path = Path(src).resolve() / fname
        target_path = Path(webm_dir) / fname
        if source_path != target_path:
            shutil.copy2(source_path, target_path)

    with sync_playwright() as p:
        chrome = find_chrome()
        if chrome:
            browser = p.chromium.launch(executable_path=chrome, headless=True)
        else:
            browser = p.chromium.launch(headless=True)
        handler = functools.partial(Handler, directory=src)
        httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}/"
        manifest_path = os.path.join(pet_dir, 'manifest.json')
        if group and os.path.exists(manifest_path):
            with open(manifest_path, encoding='utf-8') as f:
                manifest = json.load(f)
            ensure_group_layout(pet_dir, manifest)
        else:
            manifest = {"fps": fps, "size": SIZE, "states": {}}
        manifest.setdefault('fps', fps); manifest.setdefault('size', SIZE)
        manifest.setdefault('states', {})
        group_states = None
        if group:
            manifest.setdefault('groups', {})
            group_states = manifest['groups'].setdefault(group, {})
            group_states.clear()
            group_states['fps'] = fps
            shutil.rmtree(Path(frames_dir) / group, ignore_errors=True)
        try:
            page = browser.new_page(
                viewport={"width": 900, "height": 900}
            )
            page.goto(base, wait_until="domcontentloaded")
            for state, fname in state_files.items():
                print("capturing", state, fname)
                src_url = "/" + urllib.parse.quote(fname)
                result = page.evaluate("(src) => window.capture(src)", src_url)
                duration = float(result["duration"])
                count = max(1, round(duration * fps))
                urls = pick_frames(count, duration, result["frames"])
                state_dir = os.path.join(frames_dir, group, state) if group else os.path.join(frames_dir, state)
                os.makedirs(state_dir, exist_ok=True)
                for i, url in enumerate(urls):
                    png = base64.b64decode(url.split(",", 1)[1])
                    with open(
                        os.path.join(state_dir, f"frame_{i:04d}.png"), "wb"
                    ) as f:
                        f.write(png)
                entry = {
                    "duration": round(duration * 1000),
                    "count": len(urls),
                    "bbox": result["bbox"] or [0, 0, SIZE - 1, SIZE - 1],
                    "source": fname,
                }
                if group:
                    group_states[state] = entry
                else:
                    manifest["states"][state] = entry
                print("  wrote", len(urls), "frames")
        finally:
            httpd.shutdown()
            browser.close()

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    if group:
        backup = Path(tempfile.mkdtemp(prefix='.webm-export-backup-', dir=destination.parent)) / destination.name
        try:
            if destination.exists():
                shutil.move(str(destination), str(backup))
            os.replace(pet_dir, destination)
        except Exception:
            if not destination.exists() and backup.exists():
                shutil.move(str(backup), str(destination))
            raise
        shutil.rmtree(staging_root, ignore_errors=True)
    print("manifest", json.dumps(manifest, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, help="directory with WebM files")
    parser.add_argument("--name", required=True, help="operator name")
    parser.add_argument("--out", required=True, help="pet directory to write")
    parser.add_argument("--group", help="write under frames/<group> and merge into manifest")
    parser.add_argument("--fps", type=int, choices=SUPPORTED_FPS, default=FPS)
    args = parser.parse_args()
    run(args.src, args.name, args.out, args.group, args.fps)


if __name__ == "__main__":
    main()
