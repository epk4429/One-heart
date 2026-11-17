"""저축은행중앙회 공시 표(knowledge/sources/S_fsb_*.json) → 저축은행 신용대출 상품 노드(2026-11-17, 형님이 내려받은 자료).

금감원 공시에는 저축은행 신용대출이 회사마다 '개인신용대출' 한 줄(36줄)뿐이고 한도·중도상환수수료가 없었다.
저축은행중앙회 소비자포털의 '가계신용대출 상품별 금리현황'은 상품 이름·신용점수 구간별 평균금리·상품소개·연체이자율을 상품마다 싣고,
'중도상환수수료율'은 저축은행별 요율을 싣는다. 그래서 저축은행 신용대출 노드는 이 표에서 만든다(금감원 36줄은 원문 저장소에 그대로 두되
상품 노드로는 쓰지 않는다: 같은 상품이 두 번 나오지 않게).

- 요율은 저축은행별 '평균'이라 상품마다의 약정 수수료가 아니다. 값은 옮기되 노드의 검사 결과(terms.issues)에 그 사실을 남겨 확인 필요로 둔다.
- 한도는 이 표에도 칸이 없다(상품소개 글에 가끔 적힘). 숫자로 정하지 않고 상품소개 글을 그대로 evidence에 둔다.
- 값이 '-'이면 None(공시에 없음). 짐작해서 채우지 않는다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import loans

ROOT = Path(__file__).resolve().parents[1]
CREDIT_ID, PREPAY_ID = "S_fsb_credit_loan_202611", "S_fsb_prepay_fee_202611"
# 저축은행중앙회 표의 이름 → 금감원 공시의 회사 이름(앞 단계 글에 회사 이름이 나오는지 검사하는 G12가 같은 이름을 쓰게)
NAME = {"DB": "디비저축은행", "NH": "엔에이치저축은행", "엠에스": "MS저축은행", "교보SBI": "SBI저축은행", "키움YES": "키움예스저축은행"}
BAND_KEYS = [b[0] for b in loans.BANDS]  # 900+, 801-900, ... 300-  (표의 8개 열과 같은 순서)


def provider_name(short: str) -> str:
    return NAME.get(short, short + "저축은행")


def _grid(source_id: str) -> list[list[str]]:
    return json.loads((ROOT / f"knowledge/sources/{source_id}.json").read_text(encoding="utf-8"))["grid"]


def _num(s: str) -> float | None:
    s = (s or "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def prepay_by_company() -> dict[str, dict]:
    """저축은행 이름 → {'원문': 그 줄 글, 'variable': 가계 변동금리 %, 'fixed': 가계 고정금리 %} (신용대출 줄, 가계대출 칸 2개)."""
    out, cur = {}, None
    for r in _grid(PREPAY_ID)[3:]:
        if r[0]:
            cur = r[0]
        if r[1] == "신용대출" and cur:
            var, fix = _num(r[3]), _num(r[4])  # 가계대출 변동금리, 고정금리 (기업대출 칸 둘은 안 쓴다)
            out[cur] = {"variable": var, "fixed": fix, "cells": r[3:5]}
    return out


def _parse_products() -> list[dict]:
    prods, cur = [], None
    for r in _grid(CREDIT_ID)[3:]:
        if r[0]:
            cur = {"company": r[0], "name": re.sub(r"\s+", " ", r[1]).strip(), "rows": {}}
            prods.append(cur)
        if cur is not None and r[2]:
            cur["rows"][r[2]] = r[3:]
    return prods


def _prepay_text(company: str) -> str:
    """저축은행별 평균 요율을 글로 옮긴다(숫자는 원문 칸 그대로). 표에 있는 칸만 쓰고('-'는 그 금리 유형의 신용대출이 없다는 뜻) 둘 다 없으면 빈 글."""
    p = prepay_by_company().get(company)
    if not p:
        return ""
    parts = [f"{label} {cell}" for label, cell, v in (("변동금리", p["cells"][0], p["variable"]), ("고정금리", p["cells"][1], p["fixed"]))
             if v is not None]
    return f"가계 {' / '.join(parts)} (저축은행 평균 중도상환수수료율, 저축은행중앙회 공시)" if parts else ""


def products() -> list[dict]:
    """저축은행 신용대출 노드(ontology/loans.products_from 의 신용대출 노드와 같은 모양)."""
    meta = {"source_id": CREDIT_ID, "as_of": "202611"}
    out, seen = [], {}
    for p in _parse_products():
        rows = p["rows"]
        avg = rows.get("평균금리(%)", [])
        share = rows.get("취급비중(%)", [])
        by_band = {k: (_num(avg[i]) if i < len(avg) else None) for i, k in enumerate(BAND_KEYS)}
        total_avg = _num(avg[8]) if len(avg) > 8 else None
        cb = share[9].strip() if len(share) > 9 and share[9].strip() not in ("", "-") else None
        intro = (rows.get("상품소개") or [""])[0].strip()
        overdue = (rows.get("연체이자율(%)") or [""])[0].strip()
        texts = {k: v for k, v in (("cb_name", cb), ("intro", intro), ("dly_rate", overdue), ("erly_rpay_fee", _prepay_text(p["company"]))) if v}
        pid = f"PRD_credit_loan_fsb_{p['company']}_{p['name']}"
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > 1:
            pid += f"_{seen[pid]}"
        node = {
            "product_id": pid, "provider": provider_name(p["company"]), "provider_code": f"fsb:{p['company']}", "name": p["name"],
            "category": "credit_loan", "category_label": loans.LOAN["credit_loan"], "group": "030300", "join_way": [],
            "source_id": meta["source_id"], "as_of": meta["as_of"], "disclosed_from": None, "dev_only": True,
            "loan_kind": "신용대출",
            "rates": {"by_band": {k: (v if v else None) for k, v in by_band.items()}, "avg": total_avg or None},
            "rate_parts": {}, "texts": texts,
        }
        node["terms"] = loans.terms(node)
        if texts.get("erly_rpay_fee"):  # 저축은행 평균이지 상품 약정이 아님 → 짐작하지 않고 확인 필요로 남긴다
            node["terms"]["issues"].append("중도상환 수수료는 저축은행 평균 요율이에요(상품별 약정은 공시에 없음)")
            node["terms"]["status"] = "needs_check"
        out.append(node)
    return out
