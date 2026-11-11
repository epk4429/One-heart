"""공동 목표 설정 2단계: 목표를 숫자로 정할 때 보여 주는 '우리 가족 기준'(2026-11-08 형님 결정).

목표 금액·기한을 정하기 어려운 가족을 위해, 가족이 입력한 금융 정보로 엔진이 기준점을 낸다. AI는 숫자를 내지 않는다.
미래 계산(화면 5)과 겹치지 않게 지키는 선:
- 계산 조건은 하나뿐이다: '지금처럼'(지금의 매달 수입·지출·대출 상환 그대로, 예금·적금 금리로 불림). 선택지·투자 비율·이벤트는 없다.
- 결과는 숫자 몇 줄(그래프·범위·가능성 없음). 차이를 어떻게 메울지는 미래 계산에서 본다.
"""

from __future__ import annotations

import math

from engine import simulate
from engine.fmt import won
from engine.schema import MAX_CASHFLOW

from . import family as F
from . import goals
from . import world_size
from .plan import PlanError, build_request, check_option, normalize_goal

BASE_RETURN = "safe"          # 예금·적금만(가정값 표, 공시 금리 중앙값)
YEARS = (3, 5, 10)            # '지금처럼 모으면' 보여 주는 해


def _years_label(months: int | None) -> str:
    if not months:
        return ""
    y, m = divmod(int(months), 12)
    return f"{y}년" + (f" {m}개월" if m else "") if y else f"{m}개월"


def _run(fam: dict, goal: dict, extra_monthly: float = 0.0) -> dict:
    spec = check_option(fam, goal, {"option_id": "A", "label": "지금처럼", "return_id": BASE_RETURN})
    req = build_request(fam, goal, [spec])
    req["range"] = {"paths": 0, "seed": 1}
    if extra_monthly:
        req["options"][0]["cashflows"].append({"label": "지금보다 더 모으는 돈", "amount": round(extra_monthly, 1),
                                               "category": "adjustment"})
    sim = simulate(req, include_monthly=False)
    if "error" in sim:
        raise PlanError(str(sim["error"]))
    return sim["results"][0]


def _rate_note() -> str:
    r = next(x for x in F.assumptions()["returns"] if x["id"] == BASE_RETURN)
    return f"지금의 매달 수입·지출·대출 상환 그대로, 모은 돈은 {r['label']}(연 {r['expected_return']:g}%)으로 불린다고 가정했어요. 생활비는 물가만큼 올라요."


def _need_monthly(fam: dict, goal: dict, within: int) -> float | None:
    """기한 안에 목표에 닿으려면 지금보다 한 달에 더 모아야 하는 돈(이분 탐색, 10만원 단위로 올림). 엔진 한도로도 안 되면 None."""
    lo, hi = 0.0, MAX_CASHFLOW
    if (_run(fam, goal)["goal_hit_month"] or 10**9) <= within:
        return 0.0
    if (_run(fam, goal, hi)["goal_hit_month"] or 10**9) > within:
        return None
    for _ in range(24):
        mid = (lo + hi) / 2
        if (_run(fam, goal, mid)["goal_hit_month"] or 10**9) <= within:
            hi = mid
        else:
            lo = mid
    return math.ceil(hi / 10) * 10


def anchors(fam: dict, gi: dict) -> dict:
    """우리 가족 기준. {"lines": [{"label","display","note"}], "facts": {fact_id: fact}, "note": 가정 설명}.
    facts는 가족이 정하는 값과 상관없는 기준점만 담는다(AI 설명 문장이 숫자를 고쳐도 낡지 않게)."""
    v = gi["fields"]
    raw = goals.derive_goal(gi, fam["members"])
    p = F.profile(fam)
    lines, facts = [], []

    def add(fid: str, value, unit: str, display: str, label: str, note: str = "", fixed: bool = True):
        # key: 가족이 정한 목표와 직접 이어지는 줄(화면이 맨 위에 한 줄로 먼저 보여 주고, 나머지는 '자세히 보기'에 접는다)
        lines.append({"label": label, "display": display, "note": note, "key": not fixed})
        if fixed:
            facts.append(F._fact(fid, value, unit, display, label))

    if raw["type"] == "reach_target":
        base = normalize_goal(fam, {**raw, "target_amount": 1_000_000, "within_months": None})
        r = _run(fam, base)
        add("size.pool", base["start_pool"], "만원", won(base["start_pool"]), "지금 모여 있는 돈", base["pool_label"])
        add("size.flow", r["monthly_flow"], "만원/월", "월 " + won(r["monthly_flow"]), "지금 한 달에 모이는 돈",
            "들어오는 돈 − 나가는 돈 − 대출 상환")
        yrs = sorted(set(YEARS) | ({round(raw["within_months"] / 12)} if raw.get("within_months") else set()))
        for y in yrs:
            if y <= len(r["yearly"]):
                end = r["yearly"][y - 1]["end"]
                add(f"size.after_{y}y", end, "만원", won(end), f"지금처럼 모으면 {y}년 뒤", "", fixed=y in YEARS)
        ta, wm = raw.get("target_amount"), raw.get("within_months")
        if ta and ta > base["start_pool"]:
            g = normalize_goal(fam, {**raw, "within_months": None})
            hit = _run(fam, g)["goal_hit_month"]
            add("", None, "", f"약 {_years_label(hit)}" if hit else f"{g['horizon_months'] // 12}년 안에는 어려워요",
                f"{won(ta)}이 모이는 때(지금처럼)", "", fixed=False)
            if wm:
                need = _need_monthly(fam, g, wm)
                shown = ("지금 속도로도 닿아요" if need == 0 else f"지금보다 월 {won(need)} 더" if need
                         else f"지금보다 월 {won(MAX_CASHFLOW)}보다 더")
                add("", None, "", shown,
                    f"{_years_label(wm)} 안에 {won(ta)}을 모으려면",
                    "" if not need else "이 차이를 어떻게 메울지는 다음 단계(미래 계산)에서 함께 봐요", fixed=False)
    elif raw["type"] == "debt_free" and p["repaying_loans"]:
        base = normalize_goal(fam, {**raw, "within_months": None})
        r = _run(fam, base)
        add("size.loan", r["start_debt"], "만원", won(r["start_debt"]), "갚아 나가는 대출 잔액")
        dm = r["debt_free_month"]
        add("size.payoff", dm, "month", f"약 {_years_label(dm)} 뒤" if dm else f"{base['horizon_months'] // 12}년 넘게",
            "지금 상환대로면 다 갚는 때")
        wm = raw.get("within_months")
        if wm and dm and wm < dm:
            add("", None, "", f"약 {_years_label(dm - wm)} 늦어요", f"{_years_label(wm)} 안에 갚으려면",
                "더 빨리 갚는 방법은 다음 단계(미래 계산)에서 함께 봐요", fixed=False)
    if gi["category"] == "retire":
        add("size.expense", p["expense_total"], "만원/월", "월 " + won(p["expense_total"]), "지금 한 달 생활비",
            "대출 상환은 빼고, 생활비·용돈 등 나가는 돈")
    return {"lines": lines, "facts": {f["fact_id"]: f for f in facts}, "note": _rate_note() if facts else ""}


def size(fam: dict, values: dict | None = None, world: dict | None = None) -> dict | None:
    """2단계 화면에 줄 것: 정할 숫자 칸, 우리 가족 기준, 세상 기준(있는 카테고리만), (다 정했으면) 계산할 목표.
    목표 카테고리가 없는 가족이면 None."""
    gi = fam.get("goal_input")
    if not gi:
        return None
    try:
        merged = goals.with_values(gi, values or {})
    except goals.GoalInputError as e:
        raise PlanError(str(e))
    fields = [{**f, "value": merged["fields"].get(f["key"]), "entered": gi["fields"].get(f["key"]) is not None}
              for f in goals.decide_fields(merged)]
    out = {"fields": fields, "missing": goals.missing(merged), "goal_raw": None, "goal": None, "message": "",
           "details": goals.details_text(merged, fam["members"]), "world": world_size.world(fam, merged, world)}
    try:
        out["anchors"] = anchors(fam, merged)
    except PlanError as e:
        out["anchors"] = {"lines": [], "facts": {}, "note": ""}
        out["message"] = str(e)
    if out["missing"]:
        return out
    raw = goals.derive_goal(merged, fam["members"])
    try:
        out["goal"] = normalize_goal(fam, raw)
        out["goal_raw"] = raw
    except PlanError as e:
        out["message"] = str(e)
    return out
