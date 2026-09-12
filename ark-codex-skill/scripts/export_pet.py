#!/usr/bin/env python3
"""Export PRTS base animations directly to canonical transparent pet frames."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

SKILL = Path(__file__).resolve().parents[1]
RUNTIME = SKILL / 'assets' / 'prts-renderer'
STATES = {'Relax': 'idle', 'Interact': 'interact', 'Move': 'move',
          'Sit': 'sit', 'Sleep': 'sleep'}
FPS, SIZE = 20, 1000


def report(stage: str, **values) -> None:
    print(json.dumps({'stage': stage, **values}, ensure_ascii=False), flush=True)


def fetch(url: str) -> bytes:
    """Two bounded attempts, with a diagnostic before retrying."""
    if urlparse(url).scheme not in {'https', 'http'}:
        raise ValueError(f'Expected an HTTP asset URL: {url}')
    for attempt in range(2):
        started = time.monotonic()
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                           'Referer': 'https://prts.wiki/'})
            with urlopen(request, timeout=30) as response:
                return response.read()
        except OSError as error:
            report('fetch-failed', url=url, attempt=attempt + 1,
                   elapsed=round(time.monotonic()-started, 2), error=str(error))
            if attempt: raise
    raise AssertionError('unreachable')


def discover(operator: str, skin: str, model_id: str | None = None) -> dict:
    metadata_url = None
    if model_id:
        identifier = model_id
    else:
        page = fetch('https://prts.wiki/w/' + quote(operator) + '?raw=1').decode('utf-8')
        match = re.search(r'<[^>]*id=["\']spine-root["\'][^>]*>', page)
        identifier_match = re.search(r'data-id=["\']([^"\']+)', match[0]) if match else None
        identifier = html.unescape(identifier_match[1]) if identifier_match else None
    if identifier:
        metadata_url = ('https://torappu.prts.wiki/assets/char_spine/'
                        + quote(identifier, safe='') + '/meta.json')
        metadata = json.loads(fetch(metadata_url))
    else:
        match = re.search(r'<script[^>]*id=["\']SPINEDATA["\'][^>]*>(.*?)</script>',
                          page, re.S)
        if not match: raise ValueError('No PRTS model metadata found; inspect saved page structure')
        metadata = json.loads(html.unescape(match[1]))
        # This is PRTS's published legacy-to-current model location mapping.
        # Version validation below still rejects incompatible data.
        metadata['prefix'] = metadata['prefix'].replace(
            'https://static.prts.wiki/spine/', 'https://static.prts.wiki/spine38/')
    try:
        model = metadata['skin'][skin]['基建']
        base = urljoin(metadata['prefix'], model['file'])
    except KeyError as error:
        raise ValueError(f'No 基建 model for skin {skin}; available skins: '
                         f'{list(metadata.get("skin", {}))}') from error
    return {'skeleton': base + '.skel', 'atlas': base + '.atlas', 'skin': model.get('skin'),
            'model_id': identifier, 'metadata': metadata_url}


def model_version(data: bytes) -> str:
    if data.lstrip().startswith(b'{'):
        return str(json.loads(data)['skeleton']['spine'])
    offset = 0
    def string() -> str:
        nonlocal offset
        length, shift = 0, 0
        while True:
            if offset >= len(data) or shift > 28: raise ValueError('Invalid Spine binary header')
            byte = data[offset]; offset += 1
            length |= (byte & 127) << shift
            if not byte & 128: break
            shift += 7
        if length < 2: return ''
        end = offset + length - 1
        if end > len(data): raise ValueError('Truncated Spine binary header')
        value = data[offset:end].decode('utf-8'); offset = end
        return value
    string()  # hash
    version = string()
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        raise ValueError(f'Invalid Spine version: {version!r}')
    return version


def atlas_pages(text: str) -> list[str]:
    pages = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        name = line.strip()
        if name and (i == 0 or not lines[i-1].strip()) and ':' not in name:
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError(f'Unsafe atlas page path: {name}')
            pages.append(name)
    if not pages: raise ValueError('Atlas has no texture pages')
    return pages


def selected_animations(animations: list[dict]) -> list[dict]:
    by_name = {a['name']: a for a in animations}
    missing = STATES.keys() - by_name.keys()
    if missing: raise ValueError('Missing required animations: ' + ', '.join(sorted(missing)))
    result = []
    for name in (*STATES, 'Special'):
        if name not in by_name: continue
        duration = float(by_name[name]['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f'Advertised animation {name} has invalid duration {duration}')
        frames = duration * FPS
        nearest = round(frames)
        count = nearest if abs(frames - nearest) <= 1e-4 else math.ceil(frames)
        result.append({'name': name, 'duration': duration,
                       'count': max(1, count)})
    return result


def verify_runtime(root: Path) -> dict:
    config = json.loads((root / 'runtime.json').read_text())
    for name, expected in config['sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Renderer checksum mismatch: {name}')
    return config


@contextmanager
def server(root: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(root), **kwargs)
        def log_message(self, *args): pass
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try: yield f'http://127.0.0.1:{httpd.server_port}'
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=5)


def image_bounds(png: bytes) -> list[int] | None:
    from PySide6.QtGui import QImage
    im = QImage.fromData(png).convertToFormat(QImage.Format.Format_RGBA8888)
    if im.isNull() or im.width() != SIZE or im.height() != SIZE:
        raise ValueError('Rendered frame is not an intact 1000×1000 image')
    data = bytes(im.constBits()); bounds = None
    for y in range(SIZE):
        row = data[y*SIZE*4+3:(y+1)*SIZE*4:4]
        if row.strip(b'\0'):
            b = [SIZE-len(row.lstrip(b'\0')), y, len(row.rstrip(b'\0'))-1, y]
            bounds = b if bounds is None else union(bounds, b)
    return bounds


def union(a, b): return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def run(args) -> Path:
    from playwright.sync_api import sync_playwright
    output = args.out.expanduser().resolve()
    if output.exists(): raise ValueError(f'Output already exists; choose a fresh directory: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    runtime = verify_runtime(args.runtime_dir)
    with tempfile.TemporaryDirectory(prefix='.prts-export-', dir=output.parent) as temporary:
        stage = Path(temporary); assets = stage/'assets'; assets.mkdir()
        shutil.copytree(args.runtime_dir, stage/'runtime')
        source = (json.loads(args.source.read_text()) if args.source else
                  discover(args.operator, args.skin, args.model_id))
        def source_bytes(value: str):
            if value.startswith(('https://', 'http://')): return fetch(value)
            path = Path(value).expanduser()
            if not path.is_absolute() and args.source: path = args.source.resolve().parent/path
            return path.read_bytes()
        skeleton = source_bytes(source['skeleton'])
        version = model_version(skeleton)
        if not version.startswith(runtime['family'] + '.'):
            raise ValueError(f'Spine {version} needs a matching renderer; installed family is {runtime["family"]}')
        (assets/'model.skel').write_bytes(skeleton)
        atlas = source_bytes(source['atlas']).decode('utf-8')
        (assets/'model.atlas').write_text(atlas)
        for name in atlas_pages(atlas):
            origin = source['atlas']
            texture = urljoin(origin, quote(name)) if origin.startswith(('https://','http://')) else str(Path(origin).parent/name)
            target = assets/name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes(texture))
        (stage/'source.json').write_text(json.dumps({'skeleton':'assets/model.skel',
            'atlas':'assets/model.atlas','skin':source.get('skin')},indent=2))
        report('assets-ready', version=version, textures=atlas_pages(atlas))
        chrome = args.chrome
        if not chrome:
            chrome = next((p for p in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Chromium.app/Contents/MacOS/Chromium'] if Path(p).is_file()), None)
        with server(stage) as address, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=chrome, headless=True,
                args=['--enable-unsafe-swiftshader','--use-angle=swiftshader'])
            try:
                page = browser.new_page(viewport={'width': SIZE, 'height': SIZE})
                page.set_default_timeout(30000)
                page.on('pageerror', lambda error: report('renderer-error', error=str(error)))
                page.goto(address+'/runtime/render.html', timeout=30000)
                animations = page.evaluate('''async config => await Promise.race([
                    window.boot(config), new Promise((_,reject)=>setTimeout(()=>reject(new Error('Model load exceeded 30s')),30000))])''',
                    {'entry': runtime['entry'], 'skeleton':'/assets/model.skel',
                     'atlas':'/assets/model.atlas', 'skin':source.get('skin')})
                selected = selected_animations(animations)
                report('animations', available=animations, selected=selected)
                fit = page.evaluate('a=>window.fit(a)', selected)
                def capture(name, timestamp):
                    url = page.evaluate('p=>window.frame(p[0],p[1])', [name,timestamp])
                    return base64.b64decode(url.split(',',1)[1])
                first = capture('Relax',0)
                bounds = image_bounds(first)
                if not bounds: raise ValueError('Preflight Relax frame is blank')
                capture(selected[-1]['name'], selected[-1]['duration']/2)
                if capture('Relax',0) != first:
                    raise ValueError('Preflight failed: pose depends on prior animation state')
                (stage/'preflight.png').write_bytes(first)
                report('preflight-passed', bounds=bounds, fit=fit, deterministic=True)
                manifest = {'fps': FPS, 'size': SIZE, 'states': {}}
                if not args.preflight:
                    for animation in selected:
                        name = animation['name']; state = STATES.get(name,'special')
                        frames = stage/'pet'/'frames'/state; frames.mkdir(parents=True)
                        total_bounds = None
                        for i in range(animation['count']):
                            png = capture(name,i/FPS); bounds = image_bounds(png)
                            if bounds:
                                if min(bounds[:2]) <= 0 or max(bounds[2:]) >= SIZE-1:
                                    raise ValueError(f'Clipped frame: {name} at {i/FPS}s')
                                total_bounds = bounds if total_bounds is None else union(total_bounds,bounds)
                            (frames/f'frame_{i:04d}.png').write_bytes(png)
                        if total_bounds is None: raise ValueError(f'All frames blank: {name}')
                        manifest['states'][state] = {'duration':round(animation['count']/FPS*1000),
                            'count':animation['count'],'bbox':total_bounds,
                            'source':f'PRTS {args.operator} {args.skin} 基建 {name}'}
                        report('animation-complete', name=name, frames=animation['count'])
                    (stage/'pet'/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
                provenance = dict(source)
                for key, asset in [('skeleton', 'model.skel'), ('atlas', 'model.atlas')]:
                    if not provenance[key].startswith(('https://', 'http://')):
                        provenance[key] = 'assets/' + asset
                (stage/'export.json').write_text(json.dumps({'operator':args.operator,'skin':args.skin,
                    'source':provenance,'model_version':version,'animations':selected,'fit':fit,
                    'preflight_only':args.preflight},ensure_ascii=False,indent=2))
            finally: browser.close()
        os.replace(stage,output)
    report('complete', output=str(output), pet=str(output/'pet') if not args.preflight else None,
           preflight_only=args.preflight)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operator'); parser.add_argument('--skin',default='默认')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source',type=Path,help='Explicit model source JSON for offline/reproducible exports')
    parser.add_argument('--model-id', help='PRTS char_spine model ID, for direct metadata discovery when the operator page is unavailable')
    parser.add_argument('--runtime-dir',type=Path,default=RUNTIME)
    parser.add_argument('--chrome'); parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    try: run(args)
    except Exception as error:
        report('failed', error=str(error)); raise SystemExit(1) from error


if __name__ == '__main__': main()
