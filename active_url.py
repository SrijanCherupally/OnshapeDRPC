"""Reuse one local accessibility helper instead of repeatedly starting PowerShell."""
import atexit
import json
from pathlib import Path
import queue
import subprocess
import threading


class UrlReader:
    def __init__(self):
        self.process = None
        self.responses = queue.Queue()
        atexit.register(self.close)

    def read(self, title, state=False):
        try:
            if self.process is None or self.process.poll() is not None:
                self.responses = queue.Queue()
                self.process = subprocess.Popen(
                    ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                     '-File', str(Path(__file__).with_name('active-url.ps1')), '-Serve'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
                process, responses = self.process, self.responses
                def collect():
                    for line in process.stdout:
                        responses.put(line.strip())
                threading.Thread(target=collect, daemon=True).start()
            self.process.stdin.write(json.dumps({'title': title, 'state': state}) + '\n')
            self.process.stdin.flush()
            return self.responses.get(timeout=8)
        except (OSError, ValueError, queue.Empty):
            self.close()
            return ''

    def read_state(self, title):
        try:
            value = json.loads(self.read(title, state=True))
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
