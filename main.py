"""Silent Onshape presence for the selected tab of the foremost Onshape window."""
import ctypes
from ctypes import wintypes
import logging
import json
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import requests
from dotenv import load_dotenv
from pypresence import Presence
from snapshot_bridge import SnapshotBridge
from api_budget import ApiBudget, BudgetExhausted
from active_url import UrlReader
from feature_activity import feature_activity

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
BASE_URL = 'https://cad.onshape.com/api'
CLIENT_ID = '1250116187732578354'
POLL_SECONDS = 0.5
URL_REFRESH_SECONDS = 1
PRESENCE_MIN_SECONDS = 5
_tab_cache = None
_url_reader = None
_browser_state = {}
LABELS = {'PARTSTUDIO': 'Part Studio', 'ASSEMBLY': 'Assembly', 'DRAWING': 'Drawing',
          'VARIABLESTUDIO': 'Variable Studio', 'BILLOFMATERIALS': 'Bill of Materials', 'BLOB': 'Imported File'}
log = logging.getLogger('onshape_presence')


def parse_title(title):
    title = re.sub(r'\s[-–—]\s(?:Brave|Google Chrome|Microsoft Edge|Mozilla Firefox)(?:.*)?$', '', title)
    match = re.fullmatch(r'Onshape\s[-–—]\s(.+?)\s\|\s(.+)', title)
    return (match.group(1).strip(), match.group(2).strip()) if match else None


def read_onshape_url(title):
    global _url_reader, _browser_state
    if _url_reader is None:
        _url_reader = UrlReader()
    _browser_state = _url_reader.read_state(title)
    return _browser_state.get('url', '')


def cached_tab(hwnd, title, tab):
    global _tab_cache
    now = time.monotonic()
    key = (hwnd, title)
    if _tab_cache and _tab_cache[0] == key and now - _tab_cache[1] < URL_REFRESH_SECONDS:
        return _tab_cache[2]
    resolved = tab
    try:
        url = read_onshape_url(title)
        match = re.fullmatch(r'https://cad\.onshape\.com/documents/([a-f0-9]{24})/([wvm])/([a-f0-9]{24})/e/([a-f0-9]{24})(?:[?#].*)?', url)
        if match:
            resolved = (*tab, match.groups())
    except (OSError, subprocess.TimeoutExpired):
        pass
    _tab_cache = (key, now, resolved)
    return resolved


def open_onshape_tab():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    found = []
    @callback_type
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(2048)
        user32.GetWindowTextW(hwnd, title, len(title))
        tab = parse_title(title.value)
        if not tab:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            image = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(image))
            if kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                if Path(image.value).name.lower() in {'brave.exe', 'chrome.exe', 'msedge.exe', 'firefox.exe'}:
                    found.append((hwnd, title.value, tab))
        finally:
            kernel32.CloseHandle(handle)
        return not found
    user32.EnumWindows(visit, 0)
    if not found:
        return None
    return cached_tab(*found[0])


class Onshape:
    def __init__(self):
        key = os.getenv('API_KEY')
        if not key:
            raise RuntimeError('API_KEY is missing from the project .env file.')
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Basic {key}', 'Accept': 'application/json'})
        self.cache = {}
        self.budget = ApiBudget(ROOT / 'api-budget.json')
        self.cache_path = ROOT / 'metadata-cache.json'
        try:
            self.disk_cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        except (OSError, ValueError):
            self.disk_cache = {}

    def request(self, path, params=None, headers=None):
        self.budget.consume()
        return self.session.get(BASE_URL + path, params=params, headers=headers, timeout=15)

    def get(self, path, params=None):
        response = self.request(path, params=params)
        response.raise_for_status()
        return response.json()

    def cached(self, key, fetch, seconds=86400):
        previous = self.cache.get(key)
        if previous and time.monotonic() - previous[0] < seconds:
            return previous[1]
        encoded = json.dumps(key)
        disk = getattr(self, 'disk_cache', {}).get(encoded)
        if disk and time.time() - disk[0] < seconds:
            return disk[1]
        try:
            value = fetch()
        except BudgetExhausted:
            if previous:
                return previous[1]
            if disk:
                return disk[1]
            raise
        self.cache[key] = (time.monotonic(), value)
        if hasattr(self, 'disk_cache'):
            self.disk_cache[encoded] = (time.time(), value)
            self.cache_path.write_text(json.dumps(self.disk_cache), encoding='utf-8')
        return value

    def documents(self, name):
        items = []
        offset = 0
        while True:
            page = self.get('/documents', {'limit': 20, 'offset': offset, 'q': name})
            batch = page.get('items', [])
            items.extend(batch)
            if not page.get('next') or not batch:
                return items
            offset += len(batch)

    def resolve(self, tab):
        if len(tab) == 3:
            did, wvm, wid, eid = tab[2]
            try:
                document = dict(self.cached(('document', did), lambda: self.get(f'/documents/{did}')))
            except BudgetExhausted:
                document = {'id': did, 'name': tab[0]}
            document['name'] = tab[0]
            document['_wvm'] = wvm
            try:
                elements = self.cached(('elements', did, wvm, wid), lambda: self.get(f'/documents/d/{did}/{wvm}/{wid}/elements'))
            except BudgetExhausted:
                elements = []
            element = next((e for e in elements if e.get('id') == eid), None)
            element = dict(element) if element else {'id': eid, 'elementType': 'UNKNOWN'}
            element['name'] = tab[1]
            return document, wid, element
        documents = self.cached(('documents', tab[0]), lambda: self.documents(tab[0]))
        matches = [d for d in documents if d.get('name') == tab[0]]
        if len(matches) != 1:
            return None
        document = matches[0]
        did = document['id']
        wid = (document.get('defaultWorkspace') or {}).get('id')
        if not wid:
            return None
        elements = self.cached(('elements', did, wid), lambda: self.get(f'/documents/d/{did}/w/{wid}/elements'))
        matches = [e for e in elements if e.get('name') == tab[1]]
        element = matches[0] if len(matches) == 1 else None
        return document, wid, element

def make_presence(document, element, tab_name, start, context=None, activity=None):
    kind = LABELS.get(element.get('elementType'), 'Tab') if element else 'Tab'
    details = f'{kind}: {tab_name}'
    payload = dict(name='Onshape', details=details[:128], state=f"Document: {document['name']}"[:128],
                   start=start, large_image='onshape_logo', large_text=details[:128],
                   small_image='onshape_logo', small_text='Onshape')
    if element and element.get('elementType') == 'PARTSTUDIO':
        activity = activity or {'label': 'Unavailable', 'name': ''}
        label = activity['label']
        text = 'Feature Detection Unavailable' if label == 'Unavailable' else label
        if activity.get('name') and activity['name'] != label:
            text += ': ' + activity['name']
        payload['state'] = f"{text} | Document: {document['name']}"[:128]
        payload['large_text'] = text[:128]
    if context and element:
        url = f"https://cad.onshape.com/documents/{document['id']}/{document.get('_wvm', 'w')}/{context}/e/{element['id']}"
        payload['buttons'] = [{'label': 'View in Onshape', 'url': url}]
    return payload


def run():
    handler = RotatingFileHandler(ROOT / 'presence.log', maxBytes=500000, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    lock = socket.socket()
    try:
        lock.bind(('127.0.0.1', 19287))
    except OSError:
        return
    api = Onshape()
    bridge = SnapshotBridge()
    rpc = None
    current = None
    started = int(time.time())
    last_payload = None
    last_sent = 0
    while True:
        try:
            tab = open_onshape_tab()
            api.budget.tick(bool(tab))
            if rpc is None:
                candidate = Presence(CLIENT_ID)
                try:
                    candidate.connect()
                except Exception:
                    try:
                        candidate.close()
                    except Exception:
                        pass
                    raise
                rpc = candidate
                last_payload = None
                last_sent = 0
                log.info('Connected to Discord.')
            resolved = api.resolve(tab) if tab else None
            if not resolved:
                bridge.clear()
                if last_payload is not None:
                    rpc.clear()
                    last_payload = None
                current = None
                time.sleep(POLL_SECONDS)
                continue
            document, wid, element = resolved
            # Local feature-list detection also identifies uncached Part Studios.
            if element and element.get('elementType') == 'UNKNOWN' and _browser_state.get('part_studio'):
                element['elementType'] = 'PARTSTUDIO'
            identity = (document['id'], wid, element['id'] if element else tab[1])
            if identity != current:
                started = int(time.time())
                current = identity
            activity = feature_activity(_browser_state)
            payload = make_presence(document, element, element['name'] if element else tab[1], started, wid, activity)
            if element and element.get('elementType') == 'PARTSTUDIO':
                payload['large_image'] = bridge.publish_feature(document, element, activity)
            else:
                payload['large_image'] = bridge.publish(api, document, wid, element, blocking=False)
            if payload != last_payload and time.monotonic() - last_sent >= PRESENCE_MIN_SECONDS:
                reply = rpc.update(**payload)
                accepted = reply.get('data') or {}
                image_kind = ('feature' if element and element.get('elementType') == 'PARTSTUDIO' else 'snapshot') if payload['large_image'].startswith('https://') else 'logo'
                log.info('Presence accepted: name=%s, %s / %s, image=%s',
                         accepted.get('name', payload['name']), payload['details'], payload['state'],
                         image_kind)
                last_payload = payload
                last_sent = time.monotonic()
        except requests.RequestException as error:
            log.warning('Onshape request failed: %s', type(error).__name__)
            time.sleep(15)
            continue
        except BudgetExhausted:
            log.info('API budget exhausted; retaining cached presence.')
            time.sleep(15)
            continue
        except Exception as error:
            log.warning('Discord/browser retry: %s', type(error).__name__)
            if rpc:
                try:
                    rpc.close()
                except Exception:
                    pass
            rpc = None
        time.sleep(POLL_SECONDS if rpc is not None else 15)


if __name__ == '__main__':
    run()
