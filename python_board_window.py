"""Dedicated WebView2 UI process; the existing Tk data owner stays on its thread."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


class BoardWindow:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="class-picker-window-")
        self.control = Path(self.temp.name) / "control.json"
        self.log = Path(self.temp.name) / "window.log"
        self.process = None
        self.sequence = 0

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def send(self, action, url=None):
        self.sequence += 1
        stage = self.control.with_suffix('.tmp')
        stage.write_text(json.dumps({'sequence': self.sequence, 'action': action, 'url': url}), encoding='utf-8')
        # A short read by the UI process can deny replacement on Windows.
        for attempt in range(20):
            try:
                os.replace(stage, self.control)
                break
            except PermissionError:
                if attempt == 19: raise
                time.sleep(.025)

    def open(self, url):
        if self.alive():
            self.send('show', url)
            return
        self.send('show', url)
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command.append(str(Path(__file__).parent / 'python_app.py'))
        command.extend(['--board-window', url, str(self.control)])
        env = os.environ.copy()
        if not getattr(sys, 'frozen', False):
            env['PYTHONPATH'] = str(Path(__file__).parent / 'python_build_deps') + os.pathsep + env.get('PYTHONPATH', '')
        with self.log.open('wb') as output:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=env)

    def close(self):
        if self.alive(): self.send('close')

    def diagnostic(self):
        return self.log.read_text(encoding='utf-8', errors='replace')[-2500:] if self.log.exists() else ''


def apply_window_control(window, item, current_url):
    """Apply a command without shrinking an existing maximized/fullscreen window."""
    action = item.get('action')
    if action == 'close':
        window.destroy()
        return current_url, True
    if action == 'fullscreen':
        window.toggle_fullscreen()
        return current_url, False
    if action == 'show':
        if item.get('url') and item['url'] != current_url:
            current_url = item['url']
            window.load_url(current_url)
        window.show()
    return current_url, False


def run_window(url, control_path):
    import webview
    control = Path(control_path)
    webview.settings['ALLOW_DOWNLOADS'] = False
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    window = webview.create_window('班级随机点名 · 3D 棋盘', url, width=1440, height=900,
                                   min_size=(980, 640), background_color='#17161c')
    closed = threading.Event()
    window.events.closed += closed.set

    def controls():
        sequence = -1
        current_url = url
        while not closed.wait(.15):
            if not control.exists():
                window.destroy(); return
            try:
                item = json.loads(control.read_text(encoding='utf-8'))
                if item['sequence'] == sequence: continue
                sequence = item['sequence']
                current_url, should_close = apply_window_control(window, item, current_url)
                if should_close: return
            except (OSError, ValueError):
                continue
    webview.start(controls, gui='edgechromium', debug=False, private_mode=True)
