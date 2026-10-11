"""Check public image delivery without blocking presence or using Onshape APIs."""
from concurrent.futures import ThreadPoolExecutor
import time
import requests
from feature_badge import static_badge_url


class ImageDelivery:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='image-check')
        self.pending = {}
        self.checked = {}

    @staticmethod
    def reachable(url):
        try:
            with requests.get(url, timeout=5, stream=True) as response:
                return response.status_code == 200 and next(response.iter_content(8), b'').startswith(b'\x89PNG\r\n\x1a\n')
        except requests.RequestException:
            return False

    def image(self, url, fallback, on_failure=None):
        if not url.startswith('https://'):
            return fallback
        now = time.monotonic()
        future = self.pending.get(url)
        if future and future.done():
            del self.pending[url]
            try:
                valid = future.result()
            except Exception:
                valid = False
            self.checked[url] = (now, valid)
            if not valid and on_failure:
                on_failure(url)
        result = self.checked.get(url)
        if (result is None or now - result[0] >= 60) and url not in self.pending:
            self.pending[url] = self.executor.submit(self.reachable, url)
        # New remote images are only submitted after their PNG bytes are reachable.
        return url if result and result[1] else fallback

    def apply(self, payload, bridge):
        fallback = static_badge_url('Onshape')
        payload['large_image'] = self.image(payload['large_image'], fallback, bridge.image_failed)
        payload['small_image'] = self.image(payload['small_image'], fallback)
        return payload
