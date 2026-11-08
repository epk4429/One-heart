"""mock 체험판(tools/build_demo.py): 파일 하나로 묶이는지, 첫 화면을 미리 계산해 넣는지, 녹화 없이 재생 공급자로 도는지."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_demo  # noqa: E402


def test_demo_html_is_self_contained(tmp_path):
    out = build_demo.build(tmp_path / "demo.html")
    html = out.read_text(encoding="utf-8")
    assert 'DEMO: true' in html
    assert not re.search(r'(src|href)="(img|css|js)/', html)
    assert "fetch(window.ONEHEART.API_BASE" not in html  # 서버로 보내는 api.js가 들어가지 않았다
    data = json.loads(re.search(r'<script type="application/json" id="demo-data">(.*?)</script>', html, re.S).group(1))
    assert data["fixed"]["/api/config"]["custom_family"] is False
    assert data["fixed"]["/api/config"]["real_products"] is True
    for p in build_demo.PRESETS:
        assert data["fixed"][f"/api/preset|{p}"]["preset_id"] == p
        assert p in data["stances"]


def test_demo_uses_mock_not_recordings():
    js = (ROOT / "web/js/demo-api.js").read_text(encoding="utf-8")
    assert '"LLM_PROVIDER": "replay"' in js
    assert "demo-rec" not in js and "not_recorded" not in js
    assert 'path === "/api/preset" ? `${path}|${body.preset_id}` : path' in js  # build_demo.demo_data 키와 같은 규칙


def test_stances_match_mock_options():
    st = json.loads((ROOT / "data/demo/stances.json").read_text(encoding="utf-8"))
    for p in build_demo.PRESETS:
        members = {m["member_id"] for m in json.loads((ROOT / f"data/presets/{p}.json").read_text(encoding="utf-8"))["members"]}
        assert set(st[p]["r1"]) == members
        for opts in st[p]["r1"].values():
            assert set(opts) == {"A", "B", "C"}  # llm/replay.py _r5의 방법 id
            assert all(o["v"] in ("good", "no") and not o["text"] for o in opts.values())  # 괜찮은 방법만 누른다(조건·이유 없음)
        common = [o for o in ("A", "B", "C") if all(x[o]["v"] == "good" for x in st[p]["r1"].values())]
        assert common, p  # 모두가 고른 방법이 있어야 체험판이 공동 목표로 계속 되돌아가지 않는다
