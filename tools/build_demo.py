"""녹화본 체험판 만들기: web/ 화면 + 녹화한 AI 응답 + 서버 Python 코드를 HTML 파일 하나(web/demo.html)로 묶는다.

사용: python tools/build_demo.py            → web/demo.html (로컬 개발 서버의 /demo.html. 비공개라 Vercel 배포에서는 .vercelignore로 뺀다)

- AI 응답: data/demo/rec/*.jsonl (dev_server.py --record 로 실제 Claude 진행을 녹화한 것)
- 예시 의사 표시: data/demo/stances.json (녹화 때 남긴 의사. 합의안 화면의 '예시 의사 채우기')
- 계산·검사: 서버 코드(engine·llm·server·verify·ontology + 가정값·예시 가족)를 파일에 넣고 브라우저 안의 Python(Pyodide)으로 돌린다.
돈이 드는 호출이 없다. 인터넷은 글꼴과 Pyodide(처음 한 번 약 10MB)에만 쓴다.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = WEB / "demo.html"
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"
AI_PATHS = {"/api/story/understand", "/api/interview/review", "/api/interview/resolve", "/api/goal/analyze",
            "/api/goal/criterion", "/api/options/design", "/api/agreement/check", "/api/agreement/revise",
            "/api/agreement/draft", "/api/recommend"}
FIXED_PATHS = {"/api/config", "/api/preset", "/api/family/check", "/api/goal/check", "/api/simulate"}
PY_DIRS = ("engine", "llm", "server", "verify", "ontology")
PY_SKIP = {"llm/eval.py", "server/usage_report.py"}
PY_DATA = ("data/assumptions.json", "data/presets/newly.json", "data/presets/elder.json")
# 녹화본에서는 공개본 안내 문구 중 사실과 달라지는 것만 바꾼다.
TEXT_SWAPS = [
    ("<title>ONE-Heart · 가족 금융목표 합의 서비스</title>", "<title>ONE-Heart · 녹화본 체험</title>"),
    ('data-custom-text="가족의 이야기와 금융 정보는 예시로 정해져 있고, 각자의 생각·제안에 대한 답·의사 표시는 직접 해 보세요. AI의 정리·제안·계산은 매번 실제로 이뤄져요."',
     'data-custom-text="녹화본 체험이에요. 가족의 답과 의사 표시는 예시 그대로 진행되고, AI의 정리·제안은 실제 Claude로 미리 만든 결과를 다시 보여 줘요(비용 없음). 미래 계산은 지금 이 브라우저에서 실제로 해요."'),
    ("<p>넣지 마세요. 대략적인 값이나 가상의 값으로 충분해요. 입력한 내용은 이 브라우저에만 저장되고, AI가 처리할 때 서버로 보내지만 서버에 저장하지 않아요. AI 기능은 체험 코드가 있어야 쓸 수 있어요.</p>",
     "<p>이 녹화본 체험은 예시 가족만 쓰고, 서버로 아무것도 보내지 않아요. 진행 상태는 이 브라우저에만 저장돼요. 우리 가족으로 직접 해 보는 체험은 따로 있어요.</p>"),
]


def rec_key(path: str, body: dict) -> str:
    """web/js/demo-api.js의 recKey와 같은 규칙."""
    pid = (body.get("family") or {}).get("preset_id") or ""
    if path == "/api/interview/review":
        return f"{pid}|{path}|{body.get('member_id')}|{2 if body.get('clarification') else 1}"
    if path == "/api/interview/resolve":
        return f"{pid}|{path}|{body.get('member_id')}"
    if path == "/api/preset":
        return f"{body.get('preset_id')}|{path}"
    return f"{pid}|{path}"


def fresh_config() -> dict:
    """지금 코드의 /api/config. 녹화본은 예시 가족만(우리 가족 막음), 비공개 파일이라 개발용 실제 상품 비교는 켠다."""
    import os
    sys.path.insert(0, str(ROOT))
    old = {k: os.environ.get(k) for k in ("ALLOW_CUSTOM_FAMILY", "REAL_PRODUCTS")}
    os.environ.update({"ALLOW_CUSTOM_FAMILY": "0", "REAL_PRODUCTS": "1"})
    try:
        from server.app import dispatch
        status, cfg = dispatch("POST", "/api/config", b"{}", {}, "build")
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
    assert status == 200 and cfg["custom_family"] is False and cfg["real_products"] is True
    return cfg


def load_recordings() -> dict:
    ai, fixed = {}, {}
    files = sorted((ROOT / "data/demo/rec").glob("*.jsonl"))
    if not files:
        sys.exit("녹화가 없어요: data/demo/rec/*.jsonl (dev_server.py --record 로 먼저 녹화)")
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["status"] != 200 or "error" in r["response"]:
                continue
            key = rec_key(r["path"], r["body"])
            if r["path"] in AI_PATHS:
                ai[key] = r["response"]  # 같은 단계를 다시 했으면 마지막 것
            elif r["path"] in FIXED_PATHS and not r["body"].get("override"):
                fixed.setdefault(key, r["response"])  # 계산 엔진을 못 불러올 때만 쓰는 대체값(첫 것)
    fixed["|/api/config"] = fresh_config()  # 화면 설정은 녹화본이 아니라 지금 서버 코드로(온톨로지가 바뀌면 같이 바뀐다)
    stances = json.loads((ROOT / "data/demo/stances.json").read_text(encoding="utf-8"))
    return {"ai": ai, "fixed": fixed, "stances": stances}


def check_complete(rec: dict) -> list[str]:
    """예시 가족마다 처음부터 끝까지 필요한 AI 응답이 다 있는지."""
    missing = []
    for pid in ("newly", "elder"):
        preset = json.loads((ROOT / f"data/presets/{pid}.json").read_text(encoding="utf-8"))
        need = ["/api/story/understand", "/api/goal/analyze", "/api/goal/criterion", "/api/options/design",
                "/api/agreement/check", "/api/agreement/draft", "/api/recommend"]
        missing += [f"{pid}: {p}" for p in need if f"{pid}|{p}" not in rec["ai"]]
        for m in preset["members"]:
            if f"{pid}|/api/interview/review|{m['member_id']}|1" not in rec["ai"]:
                missing.append(f"{pid}: 각자의 생각 {m['member_id']}")
        if pid not in rec["stances"]:
            missing.append(f"{pid}: 예시 의사 표시")
    return missing


def python_sources() -> dict[str, str]:
    out = {}
    for d in PY_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            rel = p.relative_to(ROOT).as_posix()
            if "__pycache__" in rel or rel in PY_SKIP or p.suffix not in (".py", ".json"):
                continue
            out[rel] = p.read_text(encoding="utf-8")
    for rel in PY_DATA:
        out[rel] = (ROOT / rel).read_text(encoding="utf-8")
    return out


def data_uri(rel: str) -> str:
    return "data:image/png;base64," + base64.b64encode((WEB / rel).read_bytes()).decode()


def json_block(id_: str, obj) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="{id_}">{text}</script>'


def inline_js(rel: str) -> str:
    js = (WEB / rel).read_text(encoding="utf-8")
    assert "</script" not in js.lower(), rel
    for img in ("img/mark.png", "img/logo.png"):
        js = js.replace(img, data_uri(img))
    return f"<script>\n{js}\n</script>"


def build(out: Path = OUT) -> Path:
    rec = load_recordings()
    missing = check_complete(rec)
    if missing:
        sys.exit("녹화가 덜 됐어요: " + ", ".join(missing))
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for a, b in TEXT_SWAPS:
        assert a in html, a[:60]
        html = html.replace(a, b)
    for css in ("css/oneheart.css", "css/app.css"):
        tag = f'<link rel="stylesheet" href="{css}">'
        assert tag in html, tag
        html = html.replace(tag, "<style>\n" + (WEB / css).read_text(encoding="utf-8") + "\n</style>")
    html = html.replace('href="img/favicon.png"', f'href="{data_uri("img/favicon.png")}"')
    html = html.replace('src="img/logo.png"', f'src="{data_uri("img/logo.png")}"')
    scripts = '<script src="js/config.js"></script>\n<script src="js/api.js"></script>\n<script src="js/app.js"></script>'
    assert scripts in html
    html = html.replace(scripts, "\n".join([
        '<script>window.ONEHEART = { API_BASE: "", DEMO: true };</script>',
        f'<script src="{PYODIDE}"></script>',
        json_block("demo-rec", rec),
        json_block("demo-py", python_sources()),
        inline_js("js/demo-api.js"),
        inline_js("js/app.js"),
    ]))
    assert not re.search(r'(src|href)="(img|css|js)/', html), "아직 바깥 파일을 가리키는 곳이 있어요"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    out = build()
    print(f"{out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f}KB)")
