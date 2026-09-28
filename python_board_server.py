"""Offline loopback bridge. All application callbacks run on Tk's owner thread."""
from __future__ import annotations
import json
import mimetypes
import queue
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class BoardServer:
    def __init__(self, assets: Path, dispatch):
        self.assets = assets.resolve()
        self.dispatch = dispatch
        self.token = secrets.token_urlsafe(24)
        self.jobs = queue.Queue()
        self.cache = {}
        self.stopped = False
        self.last_rejection = None
        self.last_request = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, content, mime="application/json; charset=utf-8"):
                if not isinstance(content, bytes):
                    content = json.dumps(content, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "same-origin")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def path_part(self):
                prefix = "/" + owner.token + "/"
                path = unquote(urlsplit(self.path).path)
                if self.headers.get("Host") != owner.host or not path.startswith(prefix):
                    return None
                return path[len(prefix):]

            def do_GET(self):
                part = self.path_part()
                if part is None:
                    self.reply(403, {"error": "访问无效，请从主程序打开棋盘。"}); return
                path = (owner.assets / (part or "index.html")).resolve()
                if not path.is_relative_to(owner.assets) or path.suffix not in {".html", ".css", ".js", ".svg", ".png", ".ico"} or not path.is_file():
                    self.reply(404, {"error": "文件不存在"}); return
                mime = {".js": "text/javascript", ".html": "text/html", ".css": "text/css"}.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.reply(200, path.read_bytes(), mime + ("; charset=utf-8" if path.suffix in {".html", ".css", ".js"} else ""))

            def do_POST(self):
                part = self.path_part()
                origin = self.headers.get("Origin")
                session_ok = secrets.compare_digest(self.headers.get("X-Picker-Session", ""), owner.token)
                reason = ("session_path" if part is None or not part.startswith("api/") else
                          "session_header" if not session_ok else
                          "origin" if origin not in {None, "null", owner.origin} else None)
                owner.last_request = {"origin": origin, "sessionHeader": session_ok}
                if reason:
                    owner.last_rejection = {"reason": reason, "origin": origin}
                    self.reply(403, {"error": "连接校验未通过，请关闭旧页面并从新版本重新打开。", "code": reason}); return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length < 65536:
                        raise ValueError("请求大小无效")
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError("请求格式无效")
                    job = {"command": part[4:], "payload": payload, "event": threading.Event()}
                    owner.jobs.put(job)
                    if not job["event"].wait(30):
                        self.reply(503, {"error": "主程序暂忙，请稍后刷新查看结果。"}); return
                    self.reply(job["status"], job["result"])
                except (ValueError, TypeError) as exc:
                    self.reply(400, {"error": str(exc)})

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.http.daemon_threads = True
        self.host = f"127.0.0.1:{self.http.server_port}"
        self.origin = "http://" + self.host
        self.url = self.origin + "/" + self.token + "/index.html"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def poll(self):
        while not self.jobs.empty():
            job = self.jobs.get_nowait()
            key = (job["command"], job["payload"].get("requestId"))
            try:
                if key[1] and key in self.cache:
                    job["result"] = self.cache[key]
                else:
                    job["result"] = self.dispatch(job["command"], job["payload"])
                    if key[1]:
                        self.cache[key] = job["result"]
                        if len(self.cache) > 256:
                            del self.cache[next(iter(self.cache))]
                job["status"] = 200
            except Exception as exc:
                job.update(status=400, result={"error": str(exc)})
            finally:
                job["event"].set()

    def open(self):
        webbrowser.open(self.url)

    def stop(self):
        if not self.stopped:
            self.stopped = True
            threading.Thread(target=self.http.shutdown, daemon=True).start()
            self.http.server_close()
