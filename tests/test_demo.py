"""녹화본 체험판(tools/build_demo.py): 녹화가 두 예시 가족을 끝까지 덮는지, 파일 하나로 묶이는지."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_demo  # noqa: E402


def test_recordings_cover_both_presets():
    rec = build_demo.load_recordings()
    assert build_demo.check_complete(rec) == []
    assert not any(k.startswith("|") for k in rec["ai"])  # 모든 AI 응답이 예시 가족에 묶여 있다


def test_demo_html_is_self_contained(tmp_path):
    out = build_demo.build(tmp_path / "demo.html")
    html = out.read_text(encoding="utf-8")
    assert 'DEMO: true' in html
    assert not re.search(r'(src|href)="(img|css|js)/', html)
    assert "fetch(window.ONEHEART.API_BASE" not in html  # 서버로 보내는 api.js가 들어가지 않았다
    rec = json.loads(re.search(r'<script type="application/json" id="demo-rec">(.*?)</script>', html, re.S).group(1))
    assert rec["fixed"]["|/api/config"]["custom_family"] is False


def test_demo_not_deployed():
    ignore = (ROOT / ".vercelignore").read_text(encoding="utf-8").split()
    assert "web/demo.html" in ignore  # 비공개(형님 결정 2026-11-02). 개발용 실제 상품 공시도 들어 있다


def test_rec_key_matches_js():
    js = (ROOT / "web/js/demo-api.js").read_text(encoding="utf-8")
    for path in ("/api/interview/review", "/api/interview/resolve", "/api/preset"):
        assert f'path === "{path}"' in js
    assert build_demo.rec_key("/api/interview/review", {"family": {"preset_id": "newly"}, "member_id": "m0",
                                                       "clarification": {"word": "x"}}) == "newly|/api/interview/review|m0|2"
