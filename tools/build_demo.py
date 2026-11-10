"""mock 체험판 만들기: web/ 화면 + 서버 Python 코드를 HTML 파일 하나(web/demo.html)로 묶는다.

사용: python tools/build_demo.py            → web/demo.html (개발 서버·Vercel의 /demo.html, 파일로 열어도 된다)

- AI 응답: 실제 AI가 아니라 개발용 재생 공급자(llm/replay.py)가 규칙으로 바로 만든다. 녹화가 필요 없어서
  코드·온톨로지·가정값이 바뀌어도 다시 만들기만 하면 숫자가 지금 계산과 맞는다(2026-11-03 형님 결정).
- 예시 의사 표시: data/demo/stances.json (합의안 화면의 '예시 의사 채우기'. 재생 공급자의 방법 A·B·C에 맞춘 mock)
- 계산·검사·AI(재생): 서버 코드(engine·llm·server·verify·ontology·rag + 가정값·예시 가족)를 파일에 넣고 브라우저 안의 Python(Pyodide)으로 돌린다.
- 첫 화면(설정·예시 가족)은 만들 때 미리 계산해 넣어 Pyodide를 기다리지 않는다.
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
PRESETS = ("newly", "elder")
PY_DIRS = ("engine", "llm", "server", "verify", "ontology", "rag")
PY_SKIP = {"llm/eval.py", "server/usage_report.py"}
PY_DATA = ("data/assumptions.json", "data/presets/newly.json", "data/presets/elder.json", "knowledge/rag/chunks.jsonl",
           "knowledge/sources/index.json",  # index.json: 근거 원문 보기의 출처 이름·주소
           "knowledge/sources/S_reb_house_price_202609.json")  # 공동 목표 2단계 '세상 기준' 집값(llm/world_size.py)
# mock 체험판에서는 공개본 안내 문구 중 사실과 달라지는 것만 바꾼다.
TEXT_SWAPS = [
    ("<title>ONE-Heart · 가족 금융목표 합의 서비스</title>", "<title>ONE-Heart · mock 체험</title>"),
    ('data-custom-text="가족의 이야기와 금융 정보는 예시로 정해져 있고, 각자의 생각·제안에 대한 답·의사 표시는 직접 해 보세요. AI의 정리·제안·계산은 매번 실제로 이뤄져요."',
     'data-custom-text="mock 체험이에요. 가족의 답과 의사 표시는 예시 그대로 진행되고, AI의 정리·제안은 실제 AI가 아니라 규칙으로 바로 만든 예시 답이에요(비용 없음). 미래 계산·상품 비교는 지금 이 브라우저에서 실제로 해요."'),
    ("<p>이름은 별칭으로, 금액은 대략으로 넣어 주세요. 계좌번호·주민등록번호·전화번호·병명 같은 정보는 쓰지 마세요. 입력한 내용은 이 브라우저에만 남고, AI가 정리할 때 잠깐 보내지만 따로 저장하지 않아요. 우리 가족 정보로 쓰려면 체험 코드가 필요해요.</p>",
     "<p>이 mock 체험은 예시 가족만 쓰고, 서버로 아무것도 보내지 않아요. 진행 상태는 이 브라우저에만 저장돼요. 우리 가족으로 직접 해 보는 체험은 따로 있어요.</p>"),
]


def _dispatch(path: str, body: dict) -> dict:
    """지금 서버 코드로 한 번 부른다(체험판과 같은 환경: 예시 가족만, 재생 공급자, 실제 상품 켬)."""
    import os
    sys.path.insert(0, str(ROOT))
    env = {"ALLOW_CUSTOM_FAMILY": "0", "REAL_PRODUCTS": "1", "LLM_PROVIDER": "replay"}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        from server.app import dispatch
        status, out = dispatch("POST", path, json.dumps(body).encode(), {}, "build")
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
    assert status == 200 and "error" not in out, (path, out)
    return out


def demo_data() -> dict:
    """첫 화면용 미리 계산한 응답(키: web/js/demo-api.js의 fixedKey)과 예시 의사."""
    cfg = _dispatch("/api/config", {})
    assert cfg["custom_family"] is False and cfg["real_products"] is True
    fixed = {"/api/config": cfg} | {f"/api/preset|{p}": _dispatch("/api/preset", {"preset_id": p}) for p in PRESETS}
    stances = json.loads((ROOT / "data/demo/stances.json").read_text(encoding="utf-8"))
    assert all(p in stances for p in PRESETS)
    return {"fixed": fixed, "stances": stances}


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
    data = demo_data()
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
        json_block("demo-data", data),
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
