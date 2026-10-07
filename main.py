"""Silent Onshape presence for the selected tab of the foremost Onshape window."""
import ctypes
from ctypes import wintypes
import logging
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

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
BASE_URL = 'https://cad.onshape.com/api'
CLIENT_ID = '1250116187732578354'
POLL_SECONDS = 2
URL_REFRESH_SECONDS = 6
PRESENCE_MIN_SECONDS = 15
_tab_cache = None
LABELS = {'PARTSTUDIO': 'Part Studio', 'ASSEMBLY': 'Assembly', 'DRAWING': 'Drawing',
          'VARIABLESTUDIO': 'Variable Studio', 'BILLOFMATERIALS': 'Bill of Materials', 'BLOB': 'Imported File'}
log = logging.getLogger('onshape_presence')


def parse_title(title):
    title = re.sub(r'\s[-–—]\s(?:Brave|Google Chrome|Microsoft Edge|Mozilla Firefox)(?:.*)?$', '', title)
    match = re.fullmatch(r'Onshape\s[-–—]\s(.+?)\s\|\s(.+)', title)
    return (match.group(1).strip(), match.group(2).strip()) if match else None


def cached_tab(hwnd, title, tab):
    global _tab_cache
    now = time.monotonic()
    key = (hwnd, title)
    if _tab_cache and _tab_cache[0] == key and now - _tab_cache[1] < URL_REFRESH_SECONDS:
        return _tab_cache[2]
    resolved = tab
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(ROOT / 'active-url.ps1'), '-WindowTitle', title],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW)
        url = result.stdout.strip()
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

    def get(self, path, params=None):
        response = self.session.get(BASE_URL + path, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def cached(self, key, fetch, seconds=60):
        previous = self.cache.get(key)
        if previous and time.monotonic() - previous[0] < seconds:
            return previous[1]
        value = fetch()
        self.cache[key] = (time.monotonic(), value)
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
            document = dict(self.cached(('document', did), lambda: self.get(f'/documents/{did}')))
            document['_wvm'] = wvm
            elements = self.cached(('elements', did, wvm, wid), lambda: self.get(f'/documents/d/{did}/{wvm}/{wid}/elements'))
            element = next((e for e in elements if e.get('id') == eid), None)
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

def make_presence(document, element, tab_name, start, context=None):
    kind = LABELS.get(element.get('elementType'), 'Tab') if element else 'Tab'
    details = f'{kind}: {tab_name}'
    payload = dict(name='Onshape', details=details[:128], state=f"Document: {document['name']}"[:128],
                   start=start, large_image='onshape_logo', large_text=details[:128],
                   small_image='onshape_logo', small_text='Onshape')
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
            tab = open_onshape_tab()
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
            identity = (document['id'], wid, element['id'] if element else tab[1])
            if identity != current:
                started = int(time.time())
                current = identity
            payload = make_presence(document, element, element['name'] if element else tab[1], started, wid)
            payload['large_image'] = bridge.publish(api, document, wid, element)
            if payload != last_payload and time.monotonic() - last_sent >= PRESENCE_MIN_SECONDS:
                reply = rpc.update(**payload)
                accepted = reply.get('data') or {}
                log.info('Presence accepted: name=%s, %s / %s, snapshot=%s',
                         accepted.get('name', payload['name']), payload['details'], payload['state'],
                         payload['large_image'].startswith('https://'))
                last_payload = payload
                last_sent = time.monotonic()
        except requests.RequestException as error:
            log.warning('Onshape request failed: %s', type(error).__name__)
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
