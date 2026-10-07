"""Publish model previews with per-document blur rules."""
import atexit
import base64
import binascii
import hashlib
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import requests
from PIL import Image, ImageFilter, ImageOps
from api_budget import BudgetExhausted

ROOT = Path(__file__).resolve().parent
SNAPSHOT_REFRESH_SECONDS = 1800
RENDER_SIZE = 300
RENDER_MARGIN = 16


def should_blur(document):
    # Biobuzz is protected even if someone accidentally removes it from settings.
    name = str(document.get('name', '')).strip().casefold()
    if not name or name == 'biobuzz':
        return True
    names = {'biobuzz'}
    ids = set()
    for filename in ['snapshot-settings.json', 'snapshot-settings.local.json']:
        path = ROOT / filename
        if not path.exists():
            continue
        try:
            settings = json.loads(path.read_text(encoding='utf-8-sig'))
            configured_names = settings.get('blurred_document_names', [])
            configured_ids = settings.get('blurred_document_ids', [])
            if not isinstance(configured_names, list) or not isinstance(configured_ids, list):
                return True
            if not all(isinstance(v, str) for v in configured_names + configured_ids):
                return True
            names.update(v.strip().casefold() for v in configured_names)
            ids.update(v.strip() for v in configured_ids)
        except (OSError, ValueError, AttributeError):
            # Invalid privacy settings must never silently produce clear images.
            return True
    return name in names or document.get('id') in ids


def render_parameters(bounds):
    """Center the bounding box and fit its projected corners in an isometric view."""
    center = [(bounds['high' + axis] + bounds['low' + axis]) / 2 for axis in 'XYZ']
    spans = [bounds['high' + axis] - bounds['low' + axis] for axis in 'XYZ']
    if not all(math.isfinite(v) for v in center + spans) or min(spans) < 0:
        raise ValueError('Invalid model bounds')
    rows = [(1 / math.sqrt(2), 1 / math.sqrt(2), 0),
            (-1 / math.sqrt(6), 1 / math.sqrt(6), math.sqrt(2 / 3)),
            (1 / math.sqrt(3), -1 / math.sqrt(3), 1 / math.sqrt(3))]
    matrix = [value for row in rows for value in (*row, -sum(row[i] * center[i] for i in range(3)))]
    span = max(sum(abs(row[i]) * spans[i] for i in range(3)) for row in rows[:2])
    return {'viewMatrix': ','.join(str(v) for v in matrix),
            'pixelSize': max(span / (RENDER_SIZE - 2 * RENDER_MARGIN), 1e-9),
            'outputWidth': RENDER_SIZE, 'outputHeight': RENDER_SIZE}


def fetch_snapshot(api, document, context, element):
    did, wvm, eid = document['id'], document.get('_wvm', 'w'), element['id']
    category = {'ASSEMBLY': 'assemblies', 'PARTSTUDIO': 'partstudios'}.get(element.get('elementType'))
    if category:
        prefix = f'/{category}/d/{did}/{wvm}/{context}/e/{eid}'
        try:
            bounds = api.get(prefix + '/boundingboxes')
            rendered = api.get(prefix + '/shadedviews', render_parameters(bounds))
            image = rendered['images'][0]
            if len(image) > 3 * 1024 * 1024:
                raise ValueError('Render too large')
            return base64.b64decode(image, validate=True)
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, binascii.Error):
            pass
    # Other tab types, or unavailable render APIs, use the wider thumbnail.
    response = api.request(
        f'/thumbnails/d/{did}/{wvm}/{context}/e/{eid}/s/300x170',
        headers={'Accept': 'image/png'}, timeout=15)
    return response.content if response.ok else b''


def prepare_snapshot(data, blurred):
    """Fit the full model, discard metadata, and optionally obscure fine details."""
    with Image.open(BytesIO(data)) as source:
        source.load()
        rgba = source.convert('RGBA')
        visible = rgba.getchannel('A').getbbox()
        if visible is None:
            raise ValueError('Empty render')
        # Remove only unused transparent background, then fit all visible geometry.
        fitted = ImageOps.contain(rgba.crop(visible), (276, 276), Image.Resampling.LANCZOS)
        background = Image.new('RGBA', (300, 300), (43, 45, 49, 255))
        background.alpha_composite(fitted, ((300 - fitted.width) // 2, (300 - fitted.height) // 2))
        image = background.convert('RGB')
        if blurred:
            image = image.resize((64, 64), Image.Resampling.BOX)
            image = image.resize((300, 300), Image.Resampling.BICUBIC)
            image = image.filter(ImageFilter.GaussianBlur(radius=8))
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()


def blur_snapshot(data):
    return prepare_snapshot(data, blurred=True)


class SnapshotBridge:
    def __init__(self, port=19288):
        self.token = secrets.token_urlsafe(32)
        self.images = {}
        self.lock = threading.Lock()
        self.hostname = None
        self.process = None
        self.last_attempt = 0
        self.last_fetch = {}
        self.last_status = None
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with bridge.lock:
                    data = bridge.images.get(self.path)
                if data is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'public, max-age=60')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        atexit.register(self.close)

    def ensure_tunnel(self):
        if self.process and self.process.poll() is None:
            return
        self.hostname = None
        if time.monotonic() - self.last_attempt < 60:
            return
        self.last_attempt = time.monotonic()
        executable = ROOT / 'tools' / 'cloudflared.exe'
        if not executable.exists():
            return
        self.process = subprocess.Popen(
            [str(executable), 'tunnel', '--no-autoupdate', '--protocol', 'http2',
             '--url', 'http://127.0.0.1:19288'],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW)
        process = self.process
        def read_output():
            for line in process.stderr:
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if match and self.process is process:
                    self.hostname = match.group(0)
        threading.Thread(target=read_output, daemon=True).start()

    def clear(self):
        with self.lock:
            self.images.clear()
        self.last_status = None
        (ROOT / 'snapshot-status.json').unlink(missing_ok=True)

    def publish(self, api, document, context, element):
        if not element:
            self.clear()
            return 'onshape_logo'
        self.ensure_tunnel()
        blurred = should_blur(document)
        key = (document['id'], document.get('_wvm', 'w'), context, element['id'], blurred)
        cache_file = ROOT / 'preview-cache' / (hashlib.sha256(json.dumps(key).encode()).hexdigest() + '.png')
        old = self.last_fetch.get(key)
        if (not old or old[1] not in self.images) and cache_file.exists():
            saved = cache_file.read_bytes()
            if saved.startswith(b'\x89PNG\r\n\x1a\n') and len(saved) <= 2 * 1024 * 1024:
                path = f'/{self.token}/{hashlib.sha256(saved).hexdigest()[:24]}.png'
                age = max(0, time.time() - cache_file.stat().st_mtime)
                old = (time.monotonic() - age, path)
                self.last_fetch[key] = old
                with self.lock:
                    self.images = {path: saved}
        can_refresh = not hasattr(api, 'budget') or api.budget.available(3)
        if old and (time.monotonic() - old[0] < SNAPSHOT_REFRESH_SECONDS or not can_refresh):
            path = old[1]
        else:
            if not can_refresh:
                with self.lock:
                    self.images.clear()
                return 'onshape_logo'
            try:
                raw = fetch_snapshot(api, document, context, element)
            except BudgetExhausted:
                return self.hostname + old[1] if old and self.hostname else 'onshape_logo'
            if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                self.clear()
                return 'onshape_logo'
            if len(raw) > 2 * 1024 * 1024:
                self.clear()
                return 'onshape_logo'
            try:
                data = prepare_snapshot(raw, blurred)
            except (OSError, ValueError, Image.DecompressionBombError):
                self.clear()
                return 'onshape_logo'
            path = f'/{self.token}/{hashlib.sha256(data).hexdigest()[:24]}.png'
            with self.lock:
                # Store only the processed image permitted by this document's rules.
                self.images = {path: data}
            cache_file.parent.mkdir(exist_ok=True)
            cache_file.write_bytes(data)
            self.last_fetch[key] = (time.monotonic(), path)
        if not self.hostname:
            return 'onshape_logo'
        url = self.hostname + path
        status = json.dumps({
            'tab': element['name'], 'type': element['elementType'], 'image_url': url,
            'blurred': blurred, 'document': document.get('name', '')
        })
        if status != self.last_status:
            (ROOT / 'snapshot-status.json').write_text(status, encoding='utf-8')
            self.last_status = status
        return url

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.server.shutdown()
        self.server.server_close()
