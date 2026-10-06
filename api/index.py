"""Vercel Python 함수 진입점. vercel.json이 /api/* 요청을 모두 이 파일로 보낸다.

서버 코드는 server/ 패키지에 있다(Vercel은 api/ 안의 .py를 각각 함수로 보므로 진입점만 둔다).
ALLOWED_ORIGIN: 화면이 올라간 주소(예: https://아이디.github.io). 여러 개면 쉼표로. 비우면 모두 허용(개발용).
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.app import dispatch  # noqa: E402

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

    def _ip(self) -> str:
        return (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()

    def do_GET(self):
        self._send(*dispatch("GET", self.path, b"", dict(self.headers), self._ip()))

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._send(*dispatch("POST", self.path, self.rfile.read(n), dict(self.headers), self._ip()))
