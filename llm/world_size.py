"""공동 목표 설정 2단계 '세상 기준': 공공 통계·제도 원문으로 만든 기준값(docs/08 4절, 2026-11-08).

'우리 가족 기준'(llm/goal_size.py, 엔진 계산) 옆에 보여 준다. 숫자는 모두 원문에서 코드가 읽는다(AI가 내지 않는다).
확보한 것만 쓴다. 지금은 내 집 마련만 있다.
- 집값: 한국부동산원 「전국주택가격동향조사」 지역·집 종류별 중위·평균 매매가격(knowledge/sources/S_reb_house_price_*.json)
- 대출로 채울 수 있는 몫: 디딤돌대출 원문의 LTV(정책대출 기준. 은행 일반 대출·DSR은 확보하지 못함)
- 취득세: 지방세법 제11조 1천분의 10(6억 이하)·1천분의 30(9억 초과). 6~9억 계산식은 원문 표(그림)라 글로 확보하지 못함
노후 생활비·양육비·장기요양 금액·간병비·중개보수는 원문을 확보하지 못해 쓰지 않는다(docs/08 4절).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from engine.fmt import won

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "knowledge" / "sources" / "S_reb_house_price_202609.json"
DOCS = ROOT / "knowledge" / "sources" / "docs"
TYPES = {"apt": "아파트", "row": "연립·다세대", "detached": "단독주택", "all": "주택 전체"}
# 고르게 할 지역: 전국·수도권·지방권 + 시도(원본 '광주'는 전남 시군과 광주 구를 함께 담고 있어 하부권역으로 나눠 보여 준다)
GROUPS = ("00000", "00001", "00002")
SPLIT = {"12000": ("12002", "12001")}  # 원본 '광주'(12000) → 광주권역, 전남권역

# 원문 인용(글자 그대로, tests/test_world_size.py가 원문에 있는지 검사)
LTV = {"source": "S_doc_nhuf_didimdol_20261103", "rate": 70,
       "quote": "LTV 70%, DTI 60% 이내. 단, 생애최초 주택구입자는 LTV 80% 적용하되, 수도권·규제지역 소재 주택 구입시 LTV 70% 적용"}
TAX = {"source": "S_doc_law_local_tax_20261108",
       "low": {"limit": 60000, "rate": 1.0, "quote": "가. 취득당시가액이 6억원 이하인 주택: 1천분의 10"},
       "high": {"limit": 90000, "rate": 3.0, "quote": "다. 취득당시가액이 9억원을 초과하는 주택: 1천분의 30"}}


@lru_cache(maxsize=1)
def _snap() -> dict:
    return json.loads(SNAP.read_text(encoding="utf-8"))


def regions() -> list[dict]:
    """화면에서 고를 지역(code, name). 순서: 전국·수도권·지방권, 시도."""
    by = {r["code"]: r for r in _snap()["regions"]}
    out = [{"code": c, "name": by[c]["name"]} for c in GROUPS if c in by]
    for r in _snap()["regions"]:
        if r["level"] != "sido":
            continue
        if r["code"] in SPLIT:
            out += [{"code": c, "name": by[c]["name"].replace("광주 ", "")} for c in SPLIT[r["code"]] if c in by]
        else:
            out.append({"code": r["code"], "name": r["name"]})
    return out


def options() -> dict:
    return {"regions": regions(), "types": [{"code": k, "name": v} for k, v in TYPES.items()],
            "month": _snap()["month"], "default": {"region": "00000", "type": "apt"}}


def _tax_line(price: float) -> str:
    if price <= TAX["low"]["limit"]:
        return f"약 {won(price * TAX['low']['rate'] / 100)}(집값의 1%)"
    if price > TAX["high"]["limit"]:
        return f"약 {won(price * TAX['high']['rate'] / 100)}(집값의 3%)"
    return "집값의 1~3% 사이(6억~9억원 구간은 법령의 계산식을 따라요)"


def home(region: str | None, typ: str | None) -> dict | None:
    """내 집 마련 세상 기준. {"lines", "sources", "region", "type"}. 지역·종류가 없으면 전국 아파트."""
    by = {r["code"]: r for r in _snap()["regions"]}
    region = region if region in {x["code"] for x in regions()} else "00000"
    typ = typ if typ in TYPES else "apt"
    v = (by[region]["values"] or {}).get(typ)
    if not v or "median_sale" not in v:
        return {"lines": [], "sources": [], "region": region, "type": typ,
                "message": "이 지역은 이 집 종류의 가격을 따로 공표하지 않아요"}
    name = next(x["name"] for x in regions() if x["code"] == region)
    med, mean = v["median_sale"], v.get("mean_sale")
    own = med * (100 - LTV["rate"]) / 100
    y, m = _snap()["month"].split("-")
    month = f"{y}년 {int(m)}월"
    lines = [
        {"label": f"{name} {TYPES[typ]} 중간 가격", "display": won(med),
         "note": "가격 순으로 줄 세웠을 때 가운데 집" + (f" · 평균 가격 {won(mean)}" if mean else "")},
        {"label": "정책대출로 빌릴 수 있는 비율", "display": f"집값의 {LTV['rate']}%까지",
         "note": "디딤돌대출 기준(생애최초는 80%, 단 수도권·규제지역은 70%). 대출 한도·소득 조건·은행 대출은 따로 확인해야 해요"},
        {"label": "그 비율이면 직접 마련할 돈", "display": f"약 {won(own)}",
         "note": f"중간 가격의 {100 - LTV['rate']}% · 집 사는 데 드는 세금·비용은 따로예요"},
        {"label": "집 살 때 내는 취득세(1주택)", "display": _tax_line(med),
         "note": "지방세법 제11조. 지방교육세 등은 따로이고, 집이 여러 채면 더 높아요"},
    ]
    return {"lines": lines, "region": region, "type": typ, "sources": [
        f"한국부동산원 「전국주택가격동향조사」 {month} 기준(표본 조사 가격)",
        "주택도시기금 내집마련디딤돌대출 안내(2026-11-03 확인)",
        "지방세법 제11조(국가법령정보센터, 2026-11-08 확인)"]}


def world(fam: dict, gi: dict, sel: dict | None) -> dict | None:
    """카테고리에 맞는 세상 기준(없으면 None)."""
    if gi["category"] == "home":
        sel = sel if isinstance(sel, dict) else {}
        out = home(sel.get("region"), sel.get("type"))
        out["options"] = options()
        return out
    return None


def check_quotes() -> list[str]:
    """원문 인용이 원문 글에 글자 그대로 있는지(없으면 문제 목록)."""
    errs = []
    for src, q in [(LTV["source"], LTV["quote"]), (TAX["source"], TAX["low"]["quote"]), (TAX["source"], TAX["high"]["quote"])]:
        p = DOCS / f"{src}.txt"
        if not p.exists() or q not in p.read_text(encoding="utf-8"):
            errs.append(f"{src}: {q[:30]}…")
    return errs
