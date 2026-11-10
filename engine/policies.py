"""계산엔진의 정책 계산: 주택연금 월지급금(2026-11-10 온톨로지에서 옮김, CLAUDE.md 5절 '계산할 때는 계산엔진만').

표·기준은 계산엔진 데이터 `data/assumptions.json`의 `reverse_mortgage`에 미리 넣어 둔다(한국주택금융공사 월지급금 예시표, 원문 인용).
온톨로지는 '주택연금 자격이 되나'(판정)까지만 하고, 금액은 여기서만 계산한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _rm() -> dict:
    return json.loads((ROOT / "data/assumptions.json").read_text(encoding="utf-8"))["reverse_mortgage"]


def owner_ages(members: list[dict], finance: list[dict]) -> list[int]:
    """집 주인 나이(나이 많은 순). 공동 명의(joint)는 가족 중 가장 나이 많은 사람을 주인 쪽으로 본다."""
    ms = {m["member_id"]: m for m in members}
    out = set()
    for i in finance:
        if i.get("kind") == "home":
            out.add(ms[i["owner_id"]]["age"] if i.get("owner_id") in ms else max(m["age"] for m in members))
    return sorted(out, reverse=True)


def reverse_mortgage_age(members: list[dict], finance: list[dict]) -> int:
    """월지급금 기준 나이: 부부 중 나이가 젊은 사람(원문 age_basis_quote). 집 주인과, 주인과 나이 차이가 spouse_gap 안인
    55세 이상 가족 중 나이 많은 사람을 부부로 보고 그중 젊은 쪽. 집이 없으면 가장 나이 많은 가족."""
    owners = owner_ages(members, finance)
    if not owners:
        return max(m["age"] for m in members)
    o, gap = owners[0], _rm()["spouse_gap"]
    mates = sorted((m["age"] for m in members if m["age"] >= 55 and m["age"] != o and abs(m["age"] - o) <= gap), reverse=True)
    return min(o, mates[0]) if mates else o


def reverse_mortgage_monthly(age: int, home_manwon: float) -> tuple[float, str] | None:
    """공사 월지급금 예시표(종신지급방식·정액형)에서 연령·주택가격으로 읽는다(만원).
    표에 없는 나이·가격은 앞뒤 칸을 직선으로 이어 계산한 추정이다. 80세 넘으면 80세 줄, 12억 넘으면 12억 칸."""
    t = _rm()["monthly_table"]
    if age < _rm()["min_age"] or home_manwon <= 0:
        return None
    ages = sorted(int(a) for a in t["rows"])
    a = min(max(age, ages[0]), ages[-1])
    lo = max(x for x in ages if x <= a)
    hi = min(x for x in ages if x >= a)
    eok = min(home_manwon / 10000, t["prices_eok"][-1])

    def at(row_age: int) -> float:
        row, ps = t["rows"][str(row_age)], t["prices_eok"]
        if eok <= ps[0]:
            return row[0] * eok / ps[0]
        i = max(k for k, p in enumerate(ps) if p <= eok)
        if i == len(ps) - 1:
            return row[-1]
        return row[i] + (row[i + 1] - row[i]) * (eok - ps[i]) / (ps[i + 1] - ps[i])
    v = at(lo) if lo == hi else at(lo) + (at(hi) - at(lo)) * (a - lo) / (hi - lo)
    exact = lo == hi and eok in t["prices_eok"]
    note = "" if exact else " · 표 사이 값은 직선으로 이어 계산한 추정"
    cap = " · 12억원 넘는 집은 12억원 칸" if home_manwon > t["prices_eok"][-1] * 10000 else ""
    return round(v / 10, 1), f"한국주택금융공사 월지급금 예시표(종신·정액형, 2026.03.01 기준) {age}세·{home_manwon / 10000:g}억원{note}{cap}"


def sell_home(home_manwon: float, new_home_ratio: float) -> dict:
    """집을 팔고 작은 집으로 옮길 때(엔진 데이터 `sell_home`의 비용 비율로): 남는 돈 = 집값 × (1 − 새 집 비율) − 집값 × 비용 비율,
    새 집 시세 = 집값 × 새 집 비율. 만원, 반올림(2026-11-10 요청 조립 코드에서 옮김)."""
    cost = json.loads((ROOT / "data/assumptions.json").read_text(encoding="utf-8"))["sell_home"]["cost_ratio"]
    return {"net": round(home_manwon * (1 - new_home_ratio) - home_manwon * cost), "new_home": round(home_manwon * new_home_ratio)}


def _home_purchase() -> dict:
    return json.loads((ROOT / "data/assumptions.json").read_text(encoding="utf-8"))["home_purchase"]


def own_money_with_ltv(price_manwon: float) -> float:
    """정책대출 LTV(엔진 데이터 home_purchase.ltv, 디딤돌 원문)만큼 빌리면 직접 마련할 돈 = 집값 × (100 − LTV)%. 만원(2026-11-11)."""
    return price_manwon * (100 - _home_purchase()["ltv"]["rate"]) / 100


def acquisition_tax(price_manwon: float) -> dict:
    """1주택 취득세(지방세법 제11조, 엔진 데이터 home_purchase.acquisition_tax). 6억 이하 1%, 9억 초과 3%.
    6억~9억 구간은 법령 계산식을 글로 확보하지 못해 금액을 내지 않는다(amount None). 만원(2026-11-11)."""
    t = _home_purchase()["acquisition_tax"]
    if price_manwon <= t["low"]["limit"]:
        return {"amount": price_manwon * t["low"]["rate"] / 100, "rate": t["low"]["rate"]}
    if price_manwon > t["high"]["limit"]:
        return {"amount": price_manwon * t["high"]["rate"] / 100, "rate": t["high"]["rate"]}
    return {"amount": None, "rate": None}
