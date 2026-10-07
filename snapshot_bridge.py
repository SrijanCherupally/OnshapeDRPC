"""Publish only heavily blurred model thumbnails through a temporary tunnel."""
import atexit
import hashlib
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent


def blur_snapshot(data):
    """Discard fine details and original metadata before an image is exposed."""
    with Image.open(BytesIO(data)) as source:
        source.load()
        rgba = source.convert('RGBA')
        background = Image.new('RGBA', rgba.size, (43, 45, 49, 255))
        background.alpha_composite(rgba)
        # Preserve the source canvas and framing; low-resolution processing
        # is only used to obscure fine details before restoring native size.
        reduced_size = tuple(max(1, round(side * 64 / 300)) for side in rgba.size)
        image = background.convert('RGB').resize(reduced_size, Image.Resampling.BOX)
        image = image.resize(rgba.size, Image.Resampling.BICUBIC)
        image = image.filter(ImageFilter.GaussianBlur(radius=8))
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()


class SnapshotBridge:
    def __init__(self, port=19288):
        self.token = secrets.token_urlsafe(32)
        self.images = {}
        self.lock = threading.Lock()
        self.hostname = None
        self.process = None
        self.last_attempt = 0
        self.last_fetch = {}
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
        self.last_fetch.clear()
        (ROOT / 'snapshot-status.json').unlink(missing_ok=True)

    def publish(self, api, document, context, element):
        if not element:
            self.clear()
            return 'onshape_logo'
        self.ensure_tunnel()
        key = (document['id'], document.get('_wvm', 'w'), context, element['id'])
        old = self.last_fetch.get(key)
        if old and time.monotonic() - old[0] < 90:
            path = old[1]
        else:
            did, wvm, wid, eid = key
            response = api.session.get(
                f'https://cad.onshape.com/api/thumbnails/d/{did}/{wvm}/{wid}/e/{eid}/s/300x300',
                headers={'Accept': 'image/png'}, timeout=15)
            if not response.ok or not response.content.startswith(b'\x89PNG\r\n\x1a\n'):
                self.clear()
                return 'onshape_logo'
            if len(response.content) > 2 * 1024 * 1024:
                self.clear()
                return 'onshape_logo'
            try:
                data = blur_snapshot(response.content)
            except (OSError, ValueError, Image.DecompressionBombError):
                self.clear()
                return 'onshape_logo'
            path = f'/{self.token}/{hashlib.sha256(data).hexdigest()[:24]}.png'
            with self.lock:
                # Only blurred bytes are stored in the publicly served image map.
                self.images = {path: data}
            self.last_fetch = {key: (time.monotonic(), path)}
        if not self.hostname:
            return 'onshape_logo'
        url = self.hostname + path
        (ROOT / 'snapshot-status.json').write_text(json.dumps({
            'tab': element['name'], 'type': element['elementType'], 'image_url': url,
            'blurred': True
        }), encoding='utf-8')
        return url

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.server.shutdown()
        self.server.server_close()
