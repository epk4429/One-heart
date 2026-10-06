"""화면 표시 규칙(docs/05_계산엔진.md 3절). 단위는 만원."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def won(v: float) -> str:
    """만원 단위 숫자를 '1억 4,855만원'처럼."""
    a = int(Decimal(str(abs(v))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if v < 0 and a else ""
    if a >= 10000:
        eok, rest = divmod(a, 10000)
        return f"{sign}{eok}억" + (f" {rest:,}만원" if rest else "원")
    return f"{sign}{a:,}만원"


def years_from_months(months: int) -> float:
    return round(months / 12, 2)


def years_display(months: int | None, horizon: int, goal_type: str) -> str:
    """'약 4.9년'. 기간 안에 없으면 reach_target은 '8년 넘게', runway는 '25년 이상'."""
    if months is None:
        y = horizon // 12
        return f"{y}년 이상" if goal_type == "runway" else f"{y}년 넘게"
    return f"약 {round1(months / 12)}년"


def round1(v: float) -> str:
    """소수 첫째 자리 사사오입(4.25 → 4.3). 기획안·v3(JS toFixed)와 같게 맞춘다."""
    return str(Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def age_at(base_age: int, months: int) -> int:
    return base_age + math.floor(months / 12)


def pct(v: float) -> str:
    return f"{v:g}%"
