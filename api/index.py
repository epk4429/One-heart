"""Vercel Python 함수 진입점. vercel.json이 /api/* 요청을 모두 이 파일로 보낸다.

서버 코드는 server/ 패키지에 있다(Vercel은 api/ 안의 .py를 각각 함수로 보므로 진입점만 둔다).
ALLOWED_ORIGIN: 화면이 올라간 주소(예: https://아이디.github.io). 여러 개면 쉼표로. 비우면 모두 허용(개발용).
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.app import dispatch  # noqa: E402

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
         ".svg": "image/svg+xml", ".ico": "image/x-icon", ".json": "application/json"}

ALLOWED = [o.strip().rstrip("/") for o in (os.environ.get("ALLOWED_ORIGIN") or "").split(",") if o.strip()]


class handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if not ALLOWED:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in ALLOWED:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _route(self) -> str:
        """원래 요청 경로. Vercel rewrites가 /api/index로 바꿔 보내므로 vercel.json이 붙인 __path를 먼저 본다."""
        u = urlsplit(self.path)
        orig = parse_qs(u.query).get("__path")
        return orig[0] if orig else u.path

    def _ip(self) -> str:
        return (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()

    def _static(self) -> None:
        """화면 파일(web/)을 내준다. Vercel이 모든 주소를 이 함수로 보내는 경우에도 화면이 열리게."""
        rel = self._route().lstrip("/") or "index.html"
        f = os.path.realpath(os.path.join(WEB, rel))
        if not f.startswith(os.path.realpath(WEB) + os.sep) or not os.path.isfile(f):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("없는 페이지예요".encode("utf-8"))
            return
        ext = os.path.splitext(f)[1].lower()
        ctype = TYPES.get(ext, "application/octet-stream")
        with open(f, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self._route()
        if not path.startswith("/api/"):
            return self._static()
        self._send(*dispatch("GET", path, b"", dict(self.headers), self._ip()))

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._send(*dispatch("POST", self._route(), self.rfile.read(n), dict(self.headers), self._ip()))
