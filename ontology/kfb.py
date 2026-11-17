"""은행연합회 '대출관련 중도상환수수료율' 표(원문 저장소 doc_key kfb_prepay_fee_credit) → 은행 신용대출 노드의 중도상환 수수료(2026-11-17).

금감원 공시의 은행 신용대출에는 한도·중도상환수수료 항목이 없었다(모두 확인 필요). 은행연합회 소비자포털은 은행별 신용 구분의
가계대출 중도상환수수료율(고정·변동)을 싣는다. 요율은 은행 전체의 평균이라 상품 약정이 아니므로 값은 옮기되 노드의 검사 결과에
그 사실을 남겨 확인 필요로 둔다(ontology/fsb.py와 같은 원칙). 한도는 이 표에도 없다.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_KEY = "kfb_prepay_fee_credit"
# 은행연합회 표의 이름 → 금감원 공시의 회사 이름
NAME = {
    "한국산업은행": "한국산업은행", "NH농협은행": "농협은행주식회사", "신한은행": "신한은행", "우리은행": "우리은행",
    "SC제일은행": "한국스탠다드차타드은행", "하나은행": "주식회사 하나은행", "IBK기업은행": "중소기업은행", "KB국민은행": "국민은행",
    "한국씨티은행": "한국씨티은행", "Sh수협은행": "수협은행", "iM뱅크(구 대구은행)": "아이엠뱅크", "BNK부산은행": "부산은행",
    "광주은행": "광주은행", "제주은행": "제주은행", "전북은행": "전북은행", "BNK경남은행": "경남은행",
    "케이뱅크": "주식회사 케이뱅크", "카카오뱅크": "주식회사 카카오뱅크", "토스뱅크": "토스뱅크 주식회사",
}


@lru_cache(maxsize=1)
def credit_prepay() -> dict[str, dict]:
    """금감원 공시 회사 이름 → {'fixed': '0.18%' 또는 '-', 'variable': '0.11%' 또는 '-'} (가계대출 신용 줄)."""
    import json
    idx = json.loads((ROOT / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]
    s = sorted((x for x in idx if x.get("doc_key") == DOC_KEY), key=lambda x: x["source_id"])[-1]
    text = (ROOT / s["file"]).read_text(encoding="utf-8")
    out = {}
    for line in text.split("\n"):
        c = line.split("\t")
        if len(c) >= 6 and c[1] == "신용" and c[0] in NAME:
            out[NAME[c[0]]] = {"fixed": c[2], "variable": c[3], "bank": c[0]}
    return out


def _txt(v: str | None) -> bool:
    return bool(v) and re.fullmatch(r"\d+(?:\.\d+)?%", v) is not None


def prepay_text(provider: str) -> str:
    """노드에 넣을 글. 표에 있는 칸만 쓰고('-'는 그 금리 유형의 신용대출이 없다는 뜻) 없으면 빈 글. '신용대출'이라는 낱말은 쓰지 않는다(loans.parse_prepay가 담보·기업 섞인 글로 보고 거른다)."""
    p = credit_prepay().get(provider)
    if not p:
        return ""
    parts = [f"{label} {v}" for label, v in (("고정금리", p["fixed"]), ("변동금리", p["variable"])) if _txt(v)]
    return f"가계 {' / '.join(parts)} (은행 평균 중도상환수수료율, 신용 구분, 은행연합회 공시)" if parts else ""


def apply(nodes: list[dict], loans) -> list[dict]:
    """금감원 공시의 은행(권역 020000) 신용대출 노드에 중도상환 수수료를 채우고 검사 결과를 다시 만든다."""
    for n in nodes:
        if n["category"] != "credit_loan" or n["group"] != "020000":
            continue
        t = prepay_text(n["provider"])
        if not t:
            continue
        n["texts"] = {**n["texts"], "erly_rpay_fee": t}
        n["terms"] = loans.terms(n)
        n["terms"]["issues"].append("중도상환 수수료는 은행 평균 요율이에요(상품별 약정은 공시에 없음)")
        n["terms"]["status"] = "needs_check"
    return nodes
