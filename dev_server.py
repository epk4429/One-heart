"""로컬 개발 서버(docs/09 5절). Node 없이 web/ 정적 파일과 /api/*를 한 포트에서 띄운다.

사용: python dev_server.py [포트]             (기본 8000, .env의 LLM_PROVIDER 사용)
      python dev_server.py 8000 --replay       (LLM 없이 배선 확인용. 화면에 "재생(개발용)"이 표시됨)

서버 쪽 코드(.py·.json)나 .env가 바뀌면 스스로 다시 켜진다(껐다 켤 필요 없음). 화면 파일(web/)은 새로고침만 하면 된다.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCH_DIRS = ("api", "server", "engine", "llm", "verify", "ontology", "data/presets")
WATCH_FILES = (".env", "data/assumptions.json")


def _snapshot() -> dict:
    files = [ROOT / f for f in WATCH_FILES]
    for d in WATCH_DIRS:
        files += [p for p in (ROOT / d).rglob("*") if p.suffix in (".py", ".json")]
    out = {}
    for p in files:
        try:
            out[str(p)] = p.stat().st_mtime
        except OSError:
            pass
    return out


def supervise() -> None:
    """코드가 바뀌면 서버(자식 프로세스)를 다시 띄운다."""
    args = [sys.executable, str(ROOT / "dev_server.py"), *sys.argv[1:], "--child"]
    snap = _snapshot()
    child = subprocess.Popen(args, cwd=ROOT)
    try:
        while True:
            time.sleep(1)
            if child.returncode is None and child.poll() is not None:  # 서버가 오류로 멈춤
                print("서버가 멈췄어요(위 메시지 확인). 파일이 고쳐지면 다시 켤게요. 끝내려면 Ctrl+C.", file=sys.stderr)
            now = _snapshot()
            if now != snap:
                changed = sorted({Path(k).name for k in set(now) ^ set(snap) | {k for k in now if now[k] != snap.get(k)}})
                print(f"\n서버 쪽 파일이 바뀌어서 다시 켜요: {', '.join(changed[:5])}", file=sys.stderr)
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                time.sleep(0.5)
                snap = now
                child = subprocess.Popen(args, cwd=ROOT)
    except KeyboardInterrupt:
        child.terminate()


def serve() -> None:
    import json
    import mimetypes
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if "--replay" in sys.argv:
        os.environ["LLM_PROVIDER"] = "replay"
    from server.app import dispatch

    web = ROOT / "web"
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _json(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._json(*dispatch("GET", self.path, b"", dict(self.headers), self.client_address[0]))
            rel = self.path.split("?")[0].lstrip("/") or "index.html"
            f = (web / rel).resolve()
            if not str(f).startswith(str(web)) or not f.is_file():
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(f.name)[0] or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(f.read_bytes())

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self._json(*dispatch("POST", self.path, self.rfile.read(n), dict(self.headers), self.client_address[0]))

    class Server(ThreadingHTTPServer):
        allow_reuse_address = False  # 같은 포트에 서버가 두 개 뜨지 않게(윈도우에서는 True면 겹쳐 뜬다)

    nums = [a for a in sys.argv[1:] if a.isdigit()]
    port = int(nums[0]) if nums else 8000
    try:
        httpd = Server(("127.0.0.1", port), Handler)
    except OSError:
        print(f"{port}번 포트를 이미 다른 서버가 쓰고 있어요. 그 서버를 끄고(Ctrl+C) 다시 실행해 주세요.", file=sys.stderr)
        sys.exit(1)
    from llm.providers import DEFAULT_MODELS, load_env
    load_env()
    prov = os.environ.get("LLM_PROVIDER", "hf")
    model = "재생(개발용)" if prov == "replay" else os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(prov, "")
    print(f"ONE-Heart 개발 서버: http://localhost:{port}  ({time.strftime('%H:%M:%S')} 시작 · AI {model})", file=sys.stderr)
    httpd.serve_forever()


if __name__ == "__main__":
    if "--child" in sys.argv:
        serve()
    else:
        supervise()
