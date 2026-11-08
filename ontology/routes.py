"""필요마다 '갈 수 있는 길'(docs/06 3.4절). 화면은 이것으로 필요별로 무엇을 보여 줄지 정한다.

길의 종류(상품 유형의 data):
- real: 금감원 공시 실제 상품 비교가 있음(real_category). 결과는 맞는 상품 있음 / 없음 / 확인 필요 중 하나로 보여 준다(ontology/fit.py summary).
- none: 상품은 있지만 공시 API에 없어 실제 상품 데이터가 아직 없음(이유를 같이 보여 준다).
- program: 정책금융·공적 제도(공식 원문 규칙은 4단계).
- consult: 상담 연결.
- self: 상품 없이 가족이 직접 지키는 약속(필요 자체에 self로 적거나, 행동 유형).
모든 필요는 길이 하나 이상 명시돼야 한다(tests/test_routes.py). 몰래 빠진 필요가 없게.
"""

from __future__ import annotations

from .search import load

ROUTE_LABEL = {"real": "실제 상품 비교", "none": "아직 실제 상품 데이터 없음", "program": "제도(공식 원문 규칙으로 판정)",
               "consult": "상담 연결", "self": "가족이 직접 지켜요"}


def routes(need_id: str) -> list[dict]:
    o = load()
    need = o["needs"][need_id]
    out = []
    for tid in need["satisfied_by"]:
        t = o["types"][tid]
        out.append({"route": t["data"], "type_id": tid, "label": t["label"], "category": t.get("real_category"),
                    "programs": t.get("programs", []),
                    "note": t.get("data_note") or (need.get("compare_note") if t["data"] == "real" else "")})
    if need.get("self"):
        out.append({"route": "self", "type_id": None, "label": "", "category": None, "note": need["self"]})
    return out


def coverage() -> dict[str, dict]:
    """필요 id → {label, routes}. 화면 설정(/api/config)으로 내보낸다."""
    o = load()
    return {nid: {"label": n["label"], "routes": routes(nid)} for nid, n in o["needs"].items()}
