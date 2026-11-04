"""가족 입력(가족방·구성원·이야기·금융정보)의 검사와 요약.

체험자는 누구든 자기 가족 상황을 넣는다. 서버는 입력을 저장하지 않고, 요청마다 받은 입력을 이 모듈로 검사한다.
금액 단위는 만원이고 체험자는 양수로 넣는다. 들어오는 돈인지 나가는 돈인지는 종류(kind)가 정한다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from engine.fmt import won

from . import goals

ROOT = Path(__file__).resolve().parents[1]

# 종류 → (주기, 부호, 화면 이름)
KINDS = {
    "income": ("monthly", 1, "매달 들어오는 돈(월급·연금 등)"),
    "transfer_in": ("monthly", 1, "가족이 보태 주는 돈"),
    "expense": ("monthly", -1, "매달 나가는 생활비"),
    "transfer_out": ("monthly", -1, "가족에게 드리는 돈(용돈 등)"),
    "deposit": ("once", 1, "예금·적금"),
    "investment": ("once", 1, "주식·펀드"),
    "lease_deposit": ("once", 1, "전세 보증금"),
    "home": ("once", 1, "집(시세)"),
    "loan": ("once", -1, "대출"),
}
LOAN_TYPES = {"lease": "전세대출(이자만 내요)", "mortgage": "주택담보대출", "credit": "신용·기타 대출"}
DISCLOSURE = ("share", "hide")  # 공개 / 비공개. (예전 '합계만'은 2026-11-04에 없앴다. 저장된 값은 비공개로 읽는다)

LIMITS = {"members": (2, 6), "finance": 30, "name": 20, "role": 12, "label": 30, "story": 1500, "reason": 300,
          "answer": 500, "room_name": 30, "amount": 1_000_000, "monthly_amount": 10_000}

QUESTIONS = [
    {"text": "앞으로 우리 가족이 어떤 모습이면 좋겠어요? 가장 지키고 싶은 것도 함께 말해 주세요.",
     "easy": "가장 지키고 싶은 게 뭐예요?"},
    {"text": "돈과 관련해서 가장 걱정되는 건 뭔가요?", "easy": "요즘 제일 걱정되는 게 뭐예요?"},
    {"text": "양보할 수 있는 것과, 양보하기 어려운 것을 하나씩 말해 주세요.", "easy": "바꿔도 괜찮은 건 뭐예요?"},
]


class FamilyError(ValueError):
    pass


@lru_cache(maxsize=1)
def assumptions() -> dict:
    return json.loads((ROOT / "data/assumptions.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def preset(preset_id: str) -> dict:
    if preset_id not in ("newly", "elder"):
        raise FamilyError("없는 예시 가족이에요")
    return json.loads((ROOT / f"data/presets/{preset_id}.json").read_text(encoding="utf-8"))


def _s(v, field: str, limit: int, *, required: bool = True) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise FamilyError(f"{field}: 글자여야 해요")
    v = v.strip()
    if required and not v:
        raise FamilyError(f"{field}: 비어 있어요")
    if len(v) > limit:
        raise FamilyError(f"{field}: {limit}자까지 쓸 수 있어요")
    return v


def _n(v, field: str, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise FamilyError(f"{field}: 숫자여야 해요")
    if not lo <= v <= hi:
        raise FamilyError(f"{field}: {lo:g}~{hi:g} 사이여야 해요")
    return round(float(v), 1)


def validate(raw: dict) -> dict:
    """체험자 입력을 검사하고 정리한다. 서버로 들어오는 모든 가족 입력은 여기를 거친다."""
    if not isinstance(raw, dict):
        raise FamilyError("가족 정보가 없어요")
    ms = raw.get("members")
    lo, hi = LIMITS["members"]
    if not isinstance(ms, list) or not lo <= len(ms) <= hi:
        raise FamilyError(f"구성원은 {lo}~{hi}명이어야 해요")
    members, seen = [], set()
    for i, m in enumerate(ms):
        mid = str(m.get("member_id") or "")
        if not re.fullmatch(r"m\d{1,2}", mid) or mid in seen:
            raise FamilyError(f"구성원 {i + 1}: id가 잘못됐어요")
        seen.add(mid)
        name = _s(m.get("name"), f"구성원 {i + 1} 이름", LIMITS["name"])
        members.append({"member_id": mid, "name": name, "initial": name[0],
                        "role": _s(m.get("role"), f"{name}님의 관계", LIMITS["role"]),
                        "age": int(_n(m.get("age"), f"{name}님의 나이", 1, 110)),
                        "easy_mode": bool(m.get("easy_mode", False))})
    room = raw.get("room") or {}
    host = room.get("host_member_id")
    if host not in seen:
        host = members[0]["member_id"]
    story = raw.get("story") or {}
    author = story.get("author_id") if story.get("author_id") in seen else host
    finance = []
    items = raw.get("finance") or []
    if not isinstance(items, list) or len(items) > LIMITS["finance"]:
        raise FamilyError(f"금융 항목은 {LIMITS['finance']}개까지예요")
    ids = set()
    for i, f in enumerate(items):
        fid = str(f.get("item_id") or "")
        if not re.fullmatch(r"f\d{1,3}", fid) or fid in ids:
            raise FamilyError(f"금융 항목 {i + 1}: id가 잘못됐어요")
        ids.add(fid)
        kind = f.get("kind")
        if kind not in KINDS:
            raise FamilyError(f"금융 항목 {i + 1}: 종류를 골라 주세요")
        label = _s(f.get("label"), f"금융 항목 {i + 1} 이름", LIMITS["label"])
        period = KINDS[kind][0]
        cap = LIMITS["monthly_amount"] if period == "monthly" else LIMITS["amount"]
        item = {"item_id": fid, "owner_id": f.get("owner_id") if f.get("owner_id") in seen else "joint",
                "kind": kind, "label": label, "amount": _n(f.get("amount"), f"'{label}' 금액", 0, cap)}
        if kind == "loan":
            lt = f.get("loan_type", "credit")
            if lt not in LOAN_TYPES:
                raise FamilyError(f"'{label}': 대출 종류를 골라 주세요")
            item["loan_type"] = lt
            item["rate"] = _n(f.get("rate", 0), f"'{label}' 금리", 0, 30)
            if lt != "lease":
                item["payment"] = _n(f.get("payment", 0), f"'{label}' 월 상환액", 0, LIMITS["monthly_amount"])
                if item["amount"] > 0 and item["payment"] <= item["amount"] * item["rate"] / 1200:
                    raise FamilyError(f"'{label}': 월 상환액이 한 달 이자({won(item['amount'] * item['rate'] / 1200)})보다 커야 해요")
        finance.append(item)
    if not any(f["kind"] in ("income", "transfer_in") for f in finance):
        raise FamilyError("매달 들어오는 돈(월급·연금 등)을 하나 이상 넣어 주세요")
    disc = {k: ("hide" if v == "summary_only" else v) for k, v in (raw.get("disclosure") or {}).items()
            if k in ids and v in DISCLOSURE + ("summary_only",)}
    try:
        goal_input = goals.validate_input(raw.get("goal_input"), set(seen))
    except goals.GoalInputError as e:
        raise FamilyError(str(e))
    today = str(raw.get("today") or "2026-10")
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", today):
        raise FamilyError("오늘 날짜 형식이 잘못됐어요")
    return {
        "preset_id": raw.get("preset_id") if raw.get("preset_id") in ("newly", "elder") else None,
        "today": today,
        "room": {"name": _s(room.get("name"), "가족방 이름", LIMITS["room_name"]),
                 "reason": _s(room.get("reason"), "가족방을 만든 이유", LIMITS["reason"], required=False),
                 "host_member_id": host},
        "members": members,
        "story": {"author_id": author, "text": _s(story.get("text"), "가족 이야기", LIMITS["story"], required=False)},
        "goal_input": goal_input,
        "finance": finance,
        "disclosure": disc,
    }


def today_label(family: dict, plus_months: int = 0) -> str:
    y, m = map(int, family["today"].split("-"))
    t = y * 12 + (m - 1) + plus_months
    return f"{t // 12}년 {t % 12 + 1}월"


def member(family: dict, mid: str) -> dict:
    return next(m for m in family["members"] if m["member_id"] == mid)


def signed(item: dict) -> float:
    return KINDS[item["kind"]][1] * item["amount"]


def profile(family: dict) -> dict:
    """금융정보 합계(코드가 계산). 역할 5와 엔진 입력이 이 값을 쓴다."""
    f = family["finance"]

    def tot(*kinds):
        return round(sum(i["amount"] for i in f if i["kind"] in kinds), 1)

    loans = [i for i in f if i["kind"] == "loan"]
    lease_loans = [i for i in loans if i["loan_type"] == "lease"]
    oldest = max(family["members"], key=lambda m: m["age"])
    return {
        "income_total": tot("income", "transfer_in"),
        "expense_total": tot("expense", "transfer_out"),
        "liquid_total": tot("deposit", "investment"),
        "lease_deposit_total": tot("lease_deposit"),
        "lease_loan_total": round(sum(i["amount"] for i in lease_loans), 1),
        "home_total": tot("home"),
        "loan_total": tot("loan"),
        "loan_payment_total": round(sum(i.get("payment", 0) if i["loan_type"] != "lease" else i["amount"] * i["rate"] / 1200
                                        for i in loans), 1),
        "repaying_loans": [i["item_id"] for i in loans if i["loan_type"] != "lease"],
        "oldest_member_id": oldest["member_id"],
    }


def _fact(fid: str, value, unit: str, display: str, label: str) -> dict:
    return {"fact_id": fid, "value": value, "unit": unit, "display": display, "label": label}


def facts(family: dict, goal: dict | None = None) -> dict[str, dict]:
    """계산 이전 단계(공동 목표·합의안)에서 AI가 {{fact:ID}}로 쓸 수 있는 숫자. 모두 가족 입력에서 온다."""
    p = profile(family)
    out = [
        _fact("fin.income_total", p["income_total"], "만원/월", "월 " + won(p["income_total"]), "매달 들어오는 돈 합계"),
        _fact("fin.expense_total", p["expense_total"], "만원/월", "월 " + won(p["expense_total"]), "매달 나가는 돈 합계"),
        _fact("fin.liquid_total", p["liquid_total"], "만원", won(p["liquid_total"]), "예금·투자 합계"),
    ]
    six = round((p["expense_total"] + p["loan_payment_total"]) * 6, 1)
    out.append(_fact("fin.six_month_outflow", six, "만원", won(six), "6개월치 나가는 돈(생활비·용돈·대출 상환)"))
    for key, label in (("home_total", "집 시세"), ("loan_total", "대출 잔액 합계"), ("lease_deposit_total", "전세 보증금")):
        if p[key]:
            out.append(_fact(f"fin.{key[:-6]}", p[key], "만원", won(p[key]), label))
    for i in family["finance"]:
        if family["disclosure"].get(i["item_id"]) == "hide":
            continue  # 본인이 비공개로 한 항목은 공유 단계 AI에도 낱개로 주지 않는다
        unit = "만원/월" if KINDS[i["kind"]][0] == "monthly" else "만원"
        out.append(_fact(f"item.{i['item_id']}", i["amount"], unit,
                         ("월 " if unit == "만원/월" else "") + won(i["amount"]), i["label"]))
    if goal:
        if goal.get("target_amount"):
            out.append(_fact("goal.target_amount", goal["target_amount"], "만원", won(goal["target_amount"]),
                             goal.get("label") or "목표 금액"))
        if goal.get("within_months"):
            y = goal["within_months"] / 12
            out.append(_fact("goal.within", goal["within_months"], "month",
                             f"{y:g}년" if y == int(y) else f"{goal['within_months']}개월", "목표 기한"))
    return {x["fact_id"]: x for x in out}


def shared_finance(family: dict) -> list[dict]:
    """공유 단계 AI에 주는 금융정보: 본인이 고른 공개 범위를 따른다(비공개 항목은 낱개로 주지 않는다)."""
    out = []
    for i in family["finance"]:
        if family["disclosure"].get(i["item_id"], "share") == "hide":
            continue
        x = {k: i[k] for k in ("item_id", "owner_id", "kind", "label", "amount") if k in i}
        for k in ("loan_type", "rate", "payment"):
            if k in i:
                x[k] = i[k]
        out.append(x)
    return out
