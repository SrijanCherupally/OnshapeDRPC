"""Keep the last feature until 15 minutes without relevant local interaction."""
import ctypes
from ctypes import wintypes
import time

IDLE_SECONDS = 15 * 60


class SessionTimer:
    """Time the open Onshape session, allowing brief tab-loading gaps."""
    def __init__(self):
        self.started = None
        self.missing_since = None

    def update(self, visible, now=None):
        now = time.time() if now is None else now
        if visible:
            if self.missing_since is not None and now - self.missing_since >= 30:
                self.started = None
            if self.started is None:
                self.started = int(now)
            self.missing_since = None
        elif self.started is not None:
            if self.missing_since is None:
                self.missing_since = now
            if now - self.missing_since >= 30:
                self.started = None
        return self.started


def local_input_sample(hwnd):
    class LastInputInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return {'foreground': False, 'tick': None, 'age': IDLE_SECONDS}
    age = ((kernel32.GetTickCount() & 0xffffffff) - info.dwTime) & 0xffffffff
    return {'foreground': user32.GetForegroundWindow() == hwnd,
            'tick': info.dwTime, 'age': age / 1000}


class ActivityTracker:
    def __init__(self):
        self.tabs = {}
        self.previous_tick = None

    def update(self, identity, kind, observed, sample, now=None):
        now = time.monotonic() if now is None else now
        entry = self.tabs.setdefault(identity, {'last_use': now, 'feature': None, 'editor': None})
        new_input = sample['tick'] is not None and sample['tick'] != self.previous_tick
        self.previous_tick = sample['tick']
        editor = observed if observed['label'] not in {'Idle', 'Unavailable'} else None
        if kind == 'PARTSTUDIO' and editor:
            entry['feature'] = dict(editor)
        relevant = kind == 'ASSEMBLY' or kind == 'PARTSTUDIO' and editor is not None
        editor_changed = editor is not None and editor != entry['editor']
        if relevant and sample['foreground'] and (new_input or editor_changed):
            entry['last_use'] = now - sample['age']
        entry['editor'] = dict(editor) if editor else None
        if kind not in {'PARTSTUDIO', 'ASSEMBLY'}:
            return observed
        if now - entry['last_use'] >= IDLE_SECONDS:
            return {'label': 'Idle', 'name': ''}
        if kind == 'ASSEMBLY':
            return {'label': 'Assembly', 'name': ''}
        return entry['feature'] or {'label': 'Viewing', 'name': ''}
