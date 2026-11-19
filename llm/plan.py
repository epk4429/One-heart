"""공동 목표와 AI가 설계한 방법(선택지)을 엔진 입력으로 바꾼다(역할 5의 출력 검사 = 출처 검사).

AI(역할 5)는 가족의 금융정보를 바탕으로 방법마다 "무엇을 바꿀지"만 정한다.
- 수익률은 가정값 표(data/assumptions.json)의 id로만 고른다.
- 있는 항목(생활비·용돈 등)의 금액을 바꾸거나, 새 월 조정·기간 이벤트·나가는 큰돈을 더할 수 있다. 모두 이유가 있어야 하고,
  크기는 가족 수입에 비례한 상한 안이어야 한다.
- 들어오는 큰돈(집 팔기)이나 주택연금 금액은 AI가 정하지 않고 코드가 가정값 표로 계산한다(정책 블록).
검사를 통과하지 못하면 PlanError의 메시지를 AI에게 그대로 돌려줘 고치게 한다.
"""

from __future__ import annotations

from engine.fmt import pct, won

from .family import KINDS, assumptions, member, profile, today_label
from .goals import is_baby

GOAL_TYPES = {"reach_target": "목표 금액 모으기", "runway": "예금으로 지낼 수 있는 기간", "debt_free": "대출 다 갚기"}
OPTION_IDS = ("A", "B", "C")
RANGE_PATHS = 1000


class PlanError(ValueError):
    pass


# ---------- 공동 목표 ----------
def normalize_goal(family: dict, raw: dict) -> dict:
    a = assumptions()
    p = profile(family)
    if not isinstance(raw, dict) or raw.get("type") not in GOAL_TYPES:
        raise PlanError(f"목표 종류(type)는 {', '.join(GOAL_TYPES)} 중 하나여야 해요")
    t = raw["type"]
    goal = {"type": t, "label": str(raw.get("label") or GOAL_TYPES[t])[:40]}
    if t == "reach_target":
        v = raw.get("target_amount")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= 1_000_000:
            raise PlanError("목표 금액(target_amount, 만원)이 필요해요")
        goal["target_amount"] = round(float(v), 1)
    if t == "debt_free" and not p["repaying_loans"]:
        raise PlanError("갚아 나가는 대출(주택담보·신용 대출)이 있어야 '대출 다 갚기' 목표를 쓸 수 있어요")
    w = raw.get("within_months")
    if w is not None:
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not 6 <= w <= 360:
            raise PlanError("기한(within_months)은 6~360개월이어야 해요")
        goal["within_months"] = int(w)
    mids = {m["member_id"] for m in family["members"]}
    base = raw.get("base_member_id") if raw.get("base_member_id") in mids else p["oldest_member_id"]
    goal["base_member_id"] = base
    base_age = member(family, base)["age"]
    hz = a["horizon_months"]
    if t == "reach_target":
        horizon = max(hz["reach_target"], 2 * goal.get("within_months", 0))
    elif t == "runway":
        horizon = (hz["runway_until_age"] - base_age) * 12
    else:
        horizon = min(hz["debt_free"], -(-int(_payoff_months(family) * 1.25 + 12) // 12) * 12)  # 해 단위로 올림
    goal["horizon_months"] = int(min(hz["max"], max(60, horizon)))
    if goal.get("within_months", 0) > goal["horizon_months"]:
        goal["within_months"] = goal["horizon_months"]
    goal["base_age"] = base_age
    # 목표 풀: 목표를 이룰 때 쓸 수 있는 돈
    lease_in_pool = (family.get("goal_input") or {}).get("category") not in ("lump", "other")  # 목돈·기타 목표는 살고 있는 집의 보증금을 쓰지 않는다(2026-11-20, 임의결정 113). 내 집 마련은 보증금을 돌려받아 집값에 보탠다
    if t == "reach_target" and lease_in_pool:
        pool = p["liquid_total"] + p["lease_deposit_total"] - p["lease_loan_total"]
        parts = [f"예금·투자 {won(p['liquid_total'])}"]
        if p["lease_deposit_total"]:
            parts.append(f"전세 보증금 {won(p['lease_deposit_total'])}")
        if p["lease_loan_total"]:
            parts.append(f"전세대출 −{won(p['lease_loan_total'])}")
        goal["pool_includes_lease"] = True
        goal["idle_pool"] = round(p["lease_deposit_total"] - p["lease_loan_total"], 1)  # 보증금·전세대출 몫에는 예금 이자가 붙지 않는다
    else:
        pool = p["liquid_total"]
        parts = [f"예금·투자 {won(p['liquid_total'])}"]
        goal["pool_includes_lease"] = False
    goal["start_pool"] = round(pool, 1)
    fl0 = raw.get("floor") if isinstance(raw.get("floor"), (int, float)) and not isinstance(raw.get("floor"), bool) else 0
    if t == "reach_target" and goal["target_amount"] <= goal["start_pool"] - max(fl0, 0):  # 비상금을 뺀 돈이 이미 목표 이상이면 계산할 게 없다(2026-11-15)
        raise PlanError(f"목표 금액은 보유 자산({won(goal['start_pool'])}, {' + '.join(parts)})"
                        + (f"에서 비상금 {won(fl0)}을 뺀 {won(goal['start_pool'] - fl0)}" if fl0 else "") + "보다 커야 해요")
    goal["pool_label"] = " + ".join(parts).replace("+ 전세대출 −", "− 전세대출 ")
    # 현실성(2026-11-15, 할 일 1-9): 비상금 선·주식(비상금으로 안 셈)·월급 상승률·집값 상승률·가족이 입력한 앞으로의 일
    fl = raw.get("floor")
    goal["floor"] = round(float(fl), 1) if isinstance(fl, (int, float)) and not isinstance(fl, bool) and fl >= 0 else 0.0
    goal["illiquid"] = round(sum(i["amount"] for i in family["finance"] if i["kind"] == "investment"), 1)
    ig = raw.get("income_growth")
    goal["income_growth"] = float(ig) if isinstance(ig, (int, float)) and not isinstance(ig, bool) and 0 <= ig <= 20         else a["income_growth"]["rate"]
    cat = (family.get("goal_input") or {}).get("category")
    tg = raw.get("target_growth")
    goal["target_growth"] = (float(tg) if isinstance(tg, (int, float)) and not isinstance(tg, bool) and 0 <= tg <= 20
                             else a["house_growth"]["rate"]) if t == "reach_target" and cat == "home" else 0.0
    goal["life"] = life_facts(family, goal)
    rd = raw.get("return_delta")  # 재점검에서 가족이 넣은 수익률 변화(%포인트). 합의안을 다시 정할 때도 그대로 가져간다(2026-11-15 형님 결정)
    goal["return_delta"] = round(float(rd), 2) if isinstance(rd, (int, float)) and not isinstance(rd, bool) and -10 <= rd <= 10 else 0.0
    goal["deficit"] = deficit_info(family, goal)  # 적자 상태(코드 판정, 2026-11-15): 어디서 목표를 만들든 같은 판정
    return goal


def life_facts(family: dict, goal: dict) -> dict:
    """가족이 '우리 가족 이야기'에서 입력한 앞으로의 일을 계산할 달로 바꾼다(AI가 아니라 코드가 계산에 넣는다, 2026-11-15).
    retire: 은퇴하는 달·은퇴 후 생활비·연금 / care: 간병비가 시작되는 달·금액 / baby(목돈 모으기의 출산·육아): 휴직 시작·끝 달·휴직하는 사람·휴직 중 수입."""
    gi = family.get("goal_input") or {}
    v, cat = gi.get("fields") or {}, gi.get("category")
    H = goal["horizon_months"]
    out = _life_main(family, goal, gi, v, cat, H)
    if cat != "retire" and v.get("work_end_member_id") and v.get("work_end_age"):  # 곧 은퇴(퇴직)하는 분의 월급을 그 나이부터 끊는다(2026-11-20)
        who = next((m for m in family["members"] if m["member_id"] == v["work_end_member_id"]), None)
        if who:
            out = {**out, "work_end": {"member_id": who["member_id"], "age": v["work_end_age"], "pension": v.get("work_end_pension"),
                                       "month": max(1, min(H, int(round((v["work_end_age"] - who["age"]) * 12)) + 1))}}
    return out


def _life_main(family: dict, goal: dict, gi: dict, v: dict, cat, H: int) -> dict:
    if cat == "retire" and v.get("retire_age") and v.get("base_member_id"):
        base_age = member(family, v["base_member_id"])["age"]
        return {"kind": "retire", "month": max(1, min(H, int(round((v["retire_age"] - base_age) * 12)) + 1)),
                "age": v["retire_age"], "base_member_id": v["base_member_id"],
                "monthly_need": v.get("monthly_need"), "pension": v.get("pension_monthly")}
    if cat == "care" and v.get("monthly_cost"):
        start = max(1, min(H, int(round((v.get("start_years") or 0) * 12)) + 1))
        end = min(H, start + int(round(v["care_years"] * 12)) - 1) if v.get("care_years") else 0  # 간병 기간(선택 입력, 2026-11-15 형님 결정)
        return {"kind": "care", "month": start, "to": end, "years": v.get("care_years"), "monthly_cost": v["monthly_cost"]}
    if is_baby(gi) and v.get("leave_months") and v.get("leave_member_id"):  # 목돈 모으기(출산·육아): '언제까지'로 정한 때부터 휴직
        s = max(1, min(H, int(round((v.get("within_years") or 0) * 12)) + 1))
        return {"kind": "baby", "from": s, "to": min(H, s + int(v["leave_months"]) - 1), "member_id": v["leave_member_id"],
                "income": v.get("leave_income") or 0.0}
    return {}


def _payoff_months(family: dict) -> float:
    """갚아 나가는 대출을 지금 월 상환액대로 갚을 때 가장 오래 걸리는 달 수(원리금 균등 공식)."""
    import math
    worst = 12.0
    for i in family["finance"]:
        if i["kind"] != "loan" or i["loan_type"] == "lease" or not i["amount"]:
            continue
        r, b, p = i["rate"] / 1200, i["amount"], i.get("payment", 0)
        if p <= b * r:
            return 360.0
        n = b / p if r == 0 else -math.log(1 - r * b / p) / math.log(1 + r)
        worst = max(worst, n)
    return worst


# ---------- 방법(선택지) ----------
def _bounds(family: dict) -> dict:
    lim = assumptions()["limits"]
    inc = profile(family)["income_total"]
    return {"adjust": max(lim["adjustment_floor"], round(inc * lim["adjustment_ratio"])),
            "event": max(lim["adjustment_floor"], round(inc * lim["event_ratio"])),
            "lump": max(1000, round(inc * lim["lump_months_of_income"])),
            "max_adjustments": lim["max_adjustments"], "max_events": lim["max_events"], "max_lumps": lim["max_lumps"]}


def _reverse_mortgage_monthly(family: dict, goal: dict) -> tuple[float, str] | None:
    """주택연금 월 수령액: 계산엔진(engine/policies.py)이 엔진 데이터의 공사 월지급금 예시표로 계산한다(2026-11-10, CLAUDE.md 5절).
    온톨로지는 '자격이 되나'(판정)만 한다. 2026-11-03 전에는 가상 비율(임의결정 26)이었다."""
    from engine.policies import reverse_mortgage_age, reverse_mortgage_monthly
    from ontology.programs import judge
    home = profile(family)["home_total"]
    if not home or judge("PG_reverse_mortgage", family)["status"] == "not_eligible":
        return None  # 판정(온톨로지): 집 주인 부부가 55세 미만 등 공식 조건에 확실히 안 맞으면 미래 계산에 방법으로 내놓지 않는다
    m = reverse_mortgage_monthly(reverse_mortgage_age(family["members"], family["finance"]), home)
    return (round(m[0]), m[1]) if m else None


def policy_menu(family: dict, goal: dict) -> list[dict]:
    """AI가 고를 수 있는 정책 블록(금액은 코드가 계산)."""
    a = assumptions()
    p = profile(family)
    out = []
    rm = _reverse_mortgage_monthly(family, goal)
    if rm:
        out.append({"policy": "reverse_mortgage", "label": "주택연금(지금 집에 계속 살면서 매달 받기)",
                    "monthly": rm[0], "basis": rm[1], "params": {"from_month": "1~기간 안의 달"},
                    "effect": "매달 들어오는 돈이 늘고, 나중에 물려줄 집의 몫은 줄어요"})
    if p["home_total"]:
        sh = a["sell_home"]
        out.append({"policy": "sell_home", "label": "집을 팔고 작은 집으로 옮기기",
                    "params": {"month": "1~기간 안의 달", "new_home_ratio": sh["new_home_ratios"]},
                    "basis": f"남는 돈 = 집값 × (1 − 새 집 비율) − 비용 {sh['cost_ratio'] * 100:g}%",
                    "effect": "한 번에 큰돈이 들어오고, 살던 집을 떠나요"})
    if goal.get("deficit"):  # 적자 상태(2026-11-15, 시안12): 대출 기간을 늘려 월 상환액을 낮추는 방법(월 상환액은 엔진이 계산)
        for lid in p["repaying_loans"]:
            loan = next(i for i in family["finance"] if i["item_id"] == lid)
            out.append({"policy": "extend_term", "label": f"{loan['label']} 기간 늘리기(월 상환액 낮추기)",
                        "params": {"item_id": lid, "years": "앞으로 갚을 기간(년, 1~40, 지금 남은 기간보다 길게)"},
                        "effect": "매달 나가는 돈이 줄고, 대신 총 이자가 늘어요. 실제로 가능한지는 금융회사 확인이 필요해요"})
    for lid in p["repaying_loans"]:
        loan = next(i for i in family["finance"] if i["item_id"] == lid)
        out.append({"policy": "extra_repayment", "label": f"{loan['label']} 추가 상환", "params": {"item_id": lid,
                    "amount": f"한 달에 더 갚을 돈(만원, {_bounds(family)['adjust']} 이하)"},
                    "effect": "모이는 돈은 줄고, 대출을 더 빨리 갚아요"})
        out.append({"policy": "lump_repayment", "label": f"{loan['label']} 예금으로 일시 상환", "params": {
                    "item_id": lid, "month": "1~기간 안의 달", "amount": f"한 번에 갚을 돈(만원, 지금 예금·투자 {won(p['liquid_total'])} 이하)"},
                    "effect": "예금이 그만큼 줄고, 대출 원금이 바로 줄어 이자와 기간이 줄어요"})
    return out


def _req_str(o: dict, k: str, where: str, n: int = 40) -> str:
    v = o.get(k)
    if not isinstance(v, str) or not v.strip():
        raise PlanError(f"{where}.{k}(글)이 필요해요")
    return v.strip()[:n]


def _num(o: dict, k: str, where: str, lo: float, hi: float, integer: bool = False) -> float:
    v = o.get(k)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PlanError(f"{where}.{k}는 숫자여야 해요")
    if not lo <= v <= hi:
        raise PlanError(f"{where}.{k}={v}: {lo:g}~{hi:g} 사이여야 해요")
    if integer and int(v) != v:
        raise PlanError(f"{where}.{k}는 정수여야 해요")
    return int(v) if integer else round(float(v), 1)


def check_option(family: dict, goal: dict, spec: dict, *, allowed_ids=OPTION_IDS, cut_limit: float | None = None) -> dict:
    """방법 하나를 검사해 정리된 spec을 돌려준다. 틀리면 PlanError."""
    if not isinstance(spec, dict):
        raise PlanError("방법은 객체여야 해요")
    oid = spec.get("option_id")
    if oid not in allowed_ids:
        raise PlanError(f"option_id는 {', '.join(allowed_ids)} 중 하나여야 해요")
    w = f"방법 {oid}"
    b = _bounds(family)
    H = goal["horizon_months"]
    rets = {r["id"]: r for r in assumptions()["returns"]}
    if spec.get("return_id") not in rets:
        raise PlanError(f"{w}.return_id는 {', '.join(rets)} 중 하나여야 해요")
    items = {i["item_id"]: i for i in family["finance"]}
    hidden = {k for k, v in family["disclosure"].items() if v == "hide"}
    out = {"option_id": oid, "label": _req_str(spec, "label", w, 30),
           "description": str(spec.get("description") or "")[:120], "return_id": spec["return_id"],
           "monthly_changes": [], "adjustments": [], "events": [], "lump_sums": [], "policies": []}
    for j, c in enumerate(spec.get("monthly_changes") or []):
        cw = f"{w}.monthly_changes[{j}]"
        it = items.get(c.get("item_id"))
        if not it or KINDS[it["kind"]][0] != "monthly" or c.get("item_id") in hidden:
            raise PlanError(f"{cw}.item_id는 공개된 '매달' 항목 id여야 해요")
        hi = max(it["amount"] * 2, it["amount"] + b["adjust"])
        out["monthly_changes"].append({"item_id": it["item_id"], "amount": _num(c, "amount", cw, 0, hi),
                                       "reason": _req_str(c, "reason", cw, 140)})
    adj = spec.get("adjustments") or []
    if len(adj) > b["max_adjustments"]:
        raise PlanError(f"{w}.adjustments는 {b['max_adjustments']}개까지예요")
    mids = {m["member_id"] for m in family["members"]}
    for j, x in enumerate(adj):
        xw = f"{w}.adjustments[{j}]"
        a = {"label": _req_str(x, "label", xw), "amount": _num(x, "amount", xw, -b["adjust"], b["adjust"]),
             "reason": _req_str(x, "reason", xw, 140)}
        if a["amount"] == 0:
            raise PlanError(f"{xw}.amount가 0이에요")
        if x.get("member_id") in mids:
            a["member_id"] = x["member_id"]
        out["adjustments"].append(a)
    ev = spec.get("events") or []
    if len(ev) > b["max_events"]:
        raise PlanError(f"{w}.events는 {b['max_events']}개까지예요")
    for j, e in enumerate(ev):
        ew = f"{w}.events[{j}]"
        f_m = _num(e, "from_month", ew, 1, H, True)
        t_m = _num(e, "to_month", ew, f_m, H, True)
        kind = e.get("kind") if e.get("kind") in ("income", "expense") else "expense"
        out["events"].append({"label": _req_str(e, "label", ew), "from_month": f_m, "to_month": t_m,
                              "amount": _num(e, "amount", ew, -b["event"], b["event"]), "kind": kind,
                              "reason": _req_str(e, "reason", ew, 140)})
    ls = spec.get("lump_sums") or []
    if len(ls) > b["max_lumps"]:
        raise PlanError(f"{w}.lump_sums는 {b['max_lumps']}개까지예요")
    for j, l in enumerate(ls):
        lw = f"{w}.lump_sums[{j}]"
        amt = _num(l, "amount", lw, -b["lump"], -1)
        out["lump_sums"].append({"label": _req_str(l, "label", lw), "month": _num(l, "month", lw, 1, H, True),
                                 "amount": amt, "reason": _req_str(l, "reason", lw, 140)})
    menu = {m["policy"]: m for m in policy_menu(family, goal)}
    used = set()
    for j, pol in enumerate(spec.get("policies") or []):
        pw = f"{w}.policies[{j}]"
        name = pol.get("policy")
        if name not in menu and name not in ("extra_repayment", "lump_repayment", "extend_term"):
            raise PlanError(f"{pw}.policy는 쓸 수 있는 정책({', '.join(sorted(set(menu)))}) 중 하나여야 해요")
        if name == "reverse_mortgage":
            out["policies"].append({"policy": name, "from_month": _num(pol, "from_month", pw, 1, H, True)
                                    if "from_month" in pol else 1})
        elif name == "sell_home":
            ratios = assumptions()["sell_home"]["new_home_ratios"]
            r = pol.get("new_home_ratio")
            if r not in ratios:
                raise PlanError(f"{pw}.new_home_ratio는 {ratios} 중 하나여야 해요")
            out["policies"].append({"policy": name, "month": _num(pol, "month", pw, 1, H, True), "new_home_ratio": r})
        elif name == "extend_term":  # 대출 기간 늘리기: 새 월 상환액은 계산엔진(engine/policies.py)이 낸다
            from engine.policies import extend_term
            lid = pol.get("item_id")
            if lid not in profile(family)["repaying_loans"]:
                raise PlanError(f"{pw}.item_id는 갚아 나가는 대출 id여야 해요")
            loan = items[lid]
            years = _num(pol, "years", pw, 1, 40, True)
            ex = extend_term(loan["amount"], loan["rate"], loan.get("payment", 0), years)
            if ex["monthly_saving"] <= 0:
                raise PlanError(f"{pw}: 앞으로 {years}년으로 늘려도 월 상환액이 지금({won(loan.get('payment', 0))})보다 줄지 않아요. 더 긴 기간을 골라 주세요")
            out["policies"].append({"policy": name, "item_id": lid, "years": years, **ex})
        elif name == "lump_repayment":
            lid = pol.get("item_id")
            if lid not in profile(family)["repaying_loans"]:
                raise PlanError(f"{pw}.item_id는 갚아 나가는 대출 id여야 해요")
            deposits = sum(i["amount"] for i in family["finance"] if i["kind"] == "deposit")
            room = max(1, deposits - goal.get("floor", 0.0))  # 예금(주식 제외)에서 비상금 선을 남기는 만큼만(2026-11-15)
            out["policies"].append({"policy": name, "item_id": lid, "month": _num(pol, "month", pw, 1, H, True),
                                    "amount": _num(pol, "amount", pw, 1, room)})
        else:
            lid = pol.get("item_id")
            if lid not in profile(family)["repaying_loans"]:
                raise PlanError(f"{pw}.item_id는 갚아 나가는 대출 id여야 해요")
            out["policies"].append({"policy": name, "item_id": lid, "amount": _num(pol, "amount", pw, 1, b["adjust"])})
        used.add(name)
    if {"reverse_mortgage", "sell_home"} <= used:
        raise PlanError(f"{w}: 주택연금과 집 팔기는 함께 고를 수 없어요")
    # 현실성 검사(2026-11-15, 할 일 1-9 A2): 생활비·용돈 줄이기 한도. 방법을 짜는 단계(역할 5·5r)에서만 검사한다(cut_limit).
    # 한도 = 지금 지출의 20%, 가족이 각자의 생각에서 '이만큼 줄일 수 있다'고 말한 금액이 더 크면 그 금액(✅ 2026-11-15 형님 결정)
    if cut_limit is not None:
        spend = {i["item_id"]: i["amount"] for i in family["finance"] if i["kind"] in ("expense", "transfer_out")}
        cut = sum(max(0.0, spend[c["item_id"]] - c["amount"]) for c in out["monthly_changes"] if c["item_id"] in spend)
        cut += sum(a["amount"] for a in out["adjustments"] if a["amount"] > 0)  # 양수 adjustments = 아껴서 더 모으는 돈
        total = sum(spend.values())
        if total and cut > cut_limit + 0.05:
            raise PlanError(f"{w}: 생활비·용돈을 한 달 {won(cut)} 줄이는 건 지금 지출({won(total)})에 비해 현실적이지 않아요. "
                            f"한 달 {won(cut_limit)}까지만 줄여 주세요")
    if spec.get("floor") is not None:
        out["floor"] = _num(spec, "floor", w, goal.get("floor", 0.0), 1_000_000)  # 가족이 정한 선보다 낮게는 못 정한다
    return out


BASELINE_LABEL = "지금처럼(비교용)"


def is_unchanged(spec: dict) -> bool:
    """생활·돈 쓰는 방식을 하나도 바꾸지 않은 방법(돈 불리는 방식만 다를 수는 있음)."""
    return not (spec["monthly_changes"] or spec["adjustments"] or spec["events"] or spec["lump_sums"] or spec["policies"]
                or spec.get("floor") is not None)


def mark_baseline(specs: list[dict]) -> list[dict]:
    """C가 아무것도 바꾸지 않은 방법이면 '지금처럼(비교용)'으로 이름을 붙인다(2026-11-15 형님 결정: 비교용으로 인정).
    A·B는 바꾸는 방법이어야 하므로 이름을 바꾸지 않는다(검사기가 따로 잡는다)."""
    for s in specs:
        if s["option_id"] == "C" and is_unchanged(s):
            s["label"] = BASELINE_LABEL
            s["description"] = s.get("description") or "지금 생활을 그대로 두면 어떻게 되는지 비교해 보는 기준이에요."
        elif "지금처럼" in s["label"] and not is_unchanged(s):  # 무언가 바꿨는데 '지금처럼'이라고 하면 이름과 내용이 어긋난다(2026-11-15)
            only_floor = s.get("floor") is not None and not (s["monthly_changes"] or s["adjustments"] or s["events"]
                                                             or s["lump_sums"] or s["policies"])
            s["label"] = "지금처럼 쓰고 비상금 넉넉히" if only_floor else                 (s["label"].replace("(비교용)", "").replace("지금처럼", "").strip(" ,·()") or "여유 있게")
    return specs


def floor_errors(goal: dict, specs: list[dict], results: list[dict]) -> list[str]:
    """방법마다 기간 중 예금(주식 제외)이 비상금 선 아래로 내려가면 거부한다(2026-11-15, A2). 노후·간병(runway)은
    비상금만 남는 때가 곧 결과라 검사하지 않는다. 지금 예금이 이미 선보다 적으면 지금보다 더 내려가지만 않으면 된다."""
    if goal["type"] == "runway" or goal.get("deficit"):  # 적자 상태는 거부하지 않고 '비상금 아래로 내려가는 때'를 보여 준다(2026-11-15)
        return []
    start_cash = goal["start_pool"] - goal.get("idle_pool", 0.0) - goal.get("illiquid", 0.0)
    errs = []
    by = {r["option_id"]: r for r in results}
    for s in specs:
        r = by.get(s["option_id"])
        if not r or r.get("min_cash") is None:
            continue
        need = min(r.get("floor", goal.get("floor", 0.0)), max(start_cash, 0.0))
        if r["min_cash"] < need - 0.5:
            errs.append(f"방법 {s['option_id']}: 기간 중 예금이 {won(r['min_cash'])}까지 내려가 비상금 선({won(need)}) 아래로 가요. "
                        "생활비 줄이기·일시 지출·추가 상환을 줄여 예금이 선 아래로 내려가지 않게 해 주세요")
    return errs


def _cat(kind: str) -> str:
    return {"income": "income", "transfer_in": "transfer", "expense": "expense", "transfer_out": "transfer"}[kind]


def net_return(ret: dict) -> float:
    """계산에 쓰는 수익률(%/년). 예금·적금처럼 이자에 세금이 붙는 가정값(after_tax)은 이자소득세(15.4%)를 뺀 세후, 주식이 섞인 것은 세금 전 그대로(2026-11-15 형님 결정)."""
    if ret.get("after_tax"):
        return round(ret["expected_return"] * (1 - assumptions()["interest_tax"]["rate"] / 100), 2)
    return ret["expected_return"]


def engine_option(family: dict, goal: dict, spec: dict) -> dict:
    """정리된 spec → 엔진 Option. meta에는 화면·해석용 설명을 담는다."""
    rets = {r["id"]: r for r in assumptions()["returns"]}
    ret = rets[spec["return_id"]]
    over = {c["item_id"]: c for c in spec["monthly_changes"]}
    cashflows, changes = [], []
    life = goal.get("life") or {}
    working = {m["member_id"] for m in family["members"] if m.get("work") in ("working", None)}  # 예전에 저장한 가족(일 정보 없음)은 일하는 것으로
    for it in family["finance"]:
        if KINDS[it["kind"]][0] != "monthly":
            continue
        amt = over[it["item_id"]]["amount"] if it["item_id"] in over else it["amount"]
        if it["item_id"] in over and amt != it["amount"]:
            changes.append(f"{it['label']} 월 {won(it['amount'])} → {won(amt)} ({over[it['item_id']]['reason']})")
        if not amt:
            continue
        wage = it["kind"] == "income" and (it["owner_id"] in working or (it["owner_id"] == "joint" and bool(working)))
        windows = [(1, 0)]
        if life.get("kind") == "retire":  # 은퇴하는 달부터 월급이 없고, '은퇴 후 필요한 돈'을 정했으면 생활비·용돈도 그 금액으로 바뀐다
            rm = life["month"]  # 이미 은퇴했으면(rm = 1) 지금 생활비가 곧 은퇴 후 생활비라 바꾸지 않는다(방법의 생활비 줄이기가 반영되게, 2026-11-15)
            if wage or (it["kind"] in ("expense", "transfer_out") and life.get("monthly_need") and rm > 1):
                windows = [(1, rm - 1)] if rm > 1 else []
        if life.get("kind") == "baby" and wage and it["owner_id"] == life["member_id"]:  # 휴직 동안 그분의 월급은 빠진다
            windows = [w for w in ((1, life["from"] - 1), (life["to"] + 1, 0)) if w[1] == 0 or w[1] >= w[0]]
            windows = [w for w in windows if w[0] <= goal["horizon_months"]]
        we = life.get("work_end")
        if we and wage and it["owner_id"] == we["member_id"]:  # 곧 은퇴(퇴직)하는 분의 월급은 그 달 직전까지만
            end = we["month"] - 1
            windows = [(f_m, end if t_m == 0 else min(t_m, end)) for f_m, t_m in windows]
            windows = [w for w in windows if w[1] >= w[0]]
        for f_m, t_m in windows:
            cashflows.append({"label": it["label"], "amount": KINDS[it["kind"]][1] * amt, "category": _cat(it["kind"]),
                              "item_id": it["item_id"], "grows": wage, "from_month": f_m, "to_month": t_m})
    for c in life_cashflows(goal):
        cashflows.append(c)
    for a in spec["adjustments"]:
        cashflows.append({"label": a["label"], "amount": a["amount"], "category": "adjustment"})
        changes.append(f"{a['label']} 월 {'+' if a['amount'] > 0 else ''}{won(a['amount'])} ({a['reason']})")
    events = [{"label": e["label"], "from_month": e["from_month"], "to_month": e["to_month"],
               "monthly_delta": e["amount"], "category": e["kind"]} for e in spec["events"]]
    for e in spec["events"]:
        changes.append(f"{e['label']}: {e['from_month']}~{e['to_month']}개월째 월 {'+' if e['amount'] > 0 else ''}"
                       f"{won(e['amount'])} ({e['reason']})")
    lumps = [{"month": l["month"], "amount": l["amount"], "label": l["label"]} for l in spec["lump_sums"]]
    for l in spec["lump_sums"]:
        changes.append(f"{l['label']}: {l['month']}개월째 {won(l['amount'])} ({l['reason']})")
    aux_changes, extra, prepay, loan_payments = [], [], [], []
    H = goal["horizon_months"]
    for pol in spec["policies"]:
        if pol["policy"] == "reverse_mortgage":
            monthly, basis = _reverse_mortgage_monthly(family, goal)
            events.append({"label": "주택연금", "from_month": pol["from_month"], "to_month": H, "monthly_delta": monthly,
                           "category": "income"})
            aux_changes.append({"type": "accrue", "account_id": "rm_debt", "from_month": pol["from_month"], "to_month": H,
                                "monthly_amount": monthly, "rate": assumptions()["reverse_mortgage"]["debt_rate"]})
            changes.append(f"주택연금 {pol['from_month']}개월째부터 월 {won(monthly)}({basis})")
        elif pol["policy"] == "sell_home":
            from engine.policies import sell_home  # 금액은 계산엔진이(CLAUDE.md 5절)
            sold = sell_home(profile(family)["home_total"], pol["new_home_ratio"])
            net = sold["net"]
            lumps.append({"month": pol["month"], "amount": net, "label": "집 팔고 남는 돈"})
            aux_changes.append({"type": "set", "account_id": "home", "month": pol["month"], "value": sold["new_home"]})
            changes.append(f"{pol['month']}개월째 집을 팔고 시세 {pol['new_home_ratio'] * 100:g}% 집으로 옮겨요. 남는 돈 {won(net)}")
            room = net  # 집을 팔면 그 집의 주택담보대출부터 판 돈으로 갚는다(2026-11-15 형님 결정, 남은 잔액은 엔진이 그달 잔액만큼만 갚음)
            for ln in [i for i in family["finance"] if i["kind"] == "loan" and i["loan_type"] == "mortgage" and i["amount"]]:
                if room <= 0:
                    break
                amt = min(ln["amount"], room)
                prepay.append({"loan_id": ln["item_id"], "month": pol["month"], "amount": round(amt, 1)})
                room -= amt
                changes.append(f"판 돈으로 {ln['label']}을 먼저 갚아요(그달 남은 잔액만큼)")
        elif pol["policy"] == "extend_term":
            loan = next(i for i in family["finance"] if i["item_id"] == pol["item_id"])
            loan_payments.append({"loan_id": pol["item_id"], "payment": pol["payment"]})
            changes.append(f"{loan['label']} 기간을 앞으로 {pol['years']}년으로 늘려 월 상환액 {won(loan.get('payment', 0))} → {won(pol['payment'])}"
                           f"(대신 총 이자 약 {won(pol['extra_interest'])} 늘어남, 금융회사 확인 필요)")
        elif pol["policy"] == "lump_repayment":
            loan = next(i for i in family["finance"] if i["item_id"] == pol["item_id"])
            prepay.append({"loan_id": pol["item_id"], "month": pol["month"], "amount": pol["amount"]})
            changes.append(f"{pol['month']}개월째 예금 {won(pol['amount'])}으로 {loan['label']} 일시 상환")
        else:
            loan = next(i for i in family["finance"] if i["item_id"] == pol["item_id"])
            extra.append({"loan_id": pol["item_id"], "monthly": pol["amount"]})
            changes.append(f"{loan['label']} 한 달 {won(pol['amount'])} 추가 상환")
    nr = max(0.0, round(net_return(ret) + goal.get("return_delta", 0.0), 2))
    changes.insert(0, f"돈을 넣는 곳: {ret['label']}(수익률 " + (f"세후 연 {pct(nr)}, 세전 연 {pct(ret['expected_return'])}에서 이자소득세 15.4%를 뺌"
                                                              if ret.get("after_tax") else f"연 {pct(nr)}, 세금 전") + " 가정)")
    return {"option_id": spec["option_id"], "label": spec["label"], "description": spec["description"],
            "expected_return": nr, "volatility": ret["volatility"], "return_assumption_id": ret["id"],
            "cashflows": cashflows, "events": events, "lump_sums": lumps, "aux_changes": aux_changes,
            "extra_payments": extra, "loan_prepayments": prepay, "loan_payments": loan_payments, **({"floor": spec["floor"]} if spec.get("floor") is not None else {}),
            "meta": {"changes": changes, "return_label": ret["label"]}}


def life_cashflows(goal: dict) -> list[dict]:
    """가족이 입력한 앞으로의 일로 코드가 더하는 수입·지출(은퇴 후 생활비·연금, 간병비, 휴직 중 수입)."""
    life, out = goal.get("life") or {}, []
    if life.get("kind") == "retire":
        if life.get("monthly_need") and life["month"] > 1:
            out.append({"label": "은퇴 후 생활비", "amount": -life["monthly_need"], "category": "expense", "from_month": life["month"]})
        if life.get("pension"):
            out.append({"label": "은퇴 후 연금", "amount": life["pension"], "category": "income", "from_month": life["month"]})
    elif life.get("kind") == "care":
        out.append({"label": "부모님 간병비", "amount": -life["monthly_cost"], "category": "expense", "from_month": life["month"],
                    **({"to_month": life["to"]} if life.get("to") else {})})
    elif life.get("kind") == "baby" and life.get("income"):
        out.append({"label": "휴직 중 수입", "amount": life["income"], "category": "income", "from_month": life["from"], "to_month": life["to"]})
    we = life.get("work_end")
    if we and we.get("pension") and we["month"] > 1:  # 곧 은퇴하는 분이 받을 연금은 은퇴하는 달부터(2026-11-20)
        out.append({"label": "은퇴 후 연금", "amount": we["pension"], "category": "income", "from_month": we["month"]})
    return out


def life_lines(family: dict, goal: dict) -> list[str]:
    """'이렇게 가정했어요' 한 줄에 들어갈 말(가족이 입력한 값과 가정값만, 계산 결과 숫자는 없음)."""
    a = assumptions()
    out = []
    ig = goal.get("income_growth", 0)
    if any(m.get("work") in ("working", None) for m in family["members"]):
        out.append("월급은 해마다 물가만큼(연 2%) 올라요" if ig == a["income_growth"]["rate"] else f"월급은 해마다 연 {ig:g}% 올라요" if ig else "월급은 오르지 않는다고 봤어요")
    out.append(f"생활비는 물가만큼(연 {a['inflation']['rate']:g}%) 올라요")
    if goal.get("floor"):
        out.append(f"비상금 {won(goal['floor'])}은 늘 남겨 둬요(예금만으로, 주식은 빼고)")
    life = goal.get("life") or {}
    if life.get("kind") == "retire":
        who = member(family, life["base_member_id"])["name"]
        out.append(f"{who}님이 {life['age']:g}세에 은퇴하면 그때부터 가족의 월급이 없어요")
        out.append(f"은퇴 후 연금 월 {won(life['pension'])}" if life.get("pension") else "은퇴 후 연금은 입력하지 않아 연금 없이 계산했어요")
        if life.get("monthly_need") and life["month"] > 1:
            out.append(f"은퇴 후 한 달 {won(life['monthly_need'])}을 써요")
        elif life["month"] <= 1:
            out.append("이미 은퇴해서 지금 생활비로 계산했어요")
    elif life.get("kind") == "care":
        out.append(f"간병비 월 {won(life['monthly_cost'])}을 {'지금부터' if life['month'] == 1 else today_label(family, life['month'] - 1) + '부터'} "
                   + (f"{life['years']:g}년 동안" if life.get("years") else "기준이 되는 분이 100세가 될 때까지(기간을 입력하지 않음)")
                   + " 넣었어요(물가만큼 올라요)")
    elif life.get("kind") == "baby":
        who = member(family, life["member_id"])["name"]
        out.append(f"{today_label(family, life['from'] - 1)}부터 {life['to'] - life['from'] + 1}개월 {who}님 휴직 · 휴직 중 수입 "
                   + (f"월 {won(life['income'])}" if life.get("income") else "0원(입력하지 않음)"))
    we = life.get("work_end")
    if we:
        who = member(family, we["member_id"])["name"]
        out.append(f"{who}님이 {we['age']:g}세에 은퇴(퇴직)하면 그분의 월급은 그때부터 없어요" if we["month"] > 1 else f"{who}님은 이미 은퇴해서 월급 없이 계산했어요")
        out.append(f"은퇴 뒤 {who}님 연금 월 {won(we['pension'])}" if we.get("pension") else f"은퇴 뒤 {who}님 연금은 입력하지 않아 연금 없이 계산했어요")
    elif goal["type"] in ("debt_free", "runway") and (family.get("goal_input") or {}).get("category") != "retire" \
            and any(m.get("work") in ("working", None) for m in family["members"]):
        out.append("일하는 가족의 월급은 계산 기간 끝까지 이어진다고 봤어요(은퇴 시기를 입력하지 않음)")
    rd = goal.get("return_delta", 0.0)
    if rd:
        out.append(f"재점검에서 수익률을 {abs(rd):g}%포인트 {'낮췄어요' if rd < 0 else '높였어요'}(모든 방법에 적용)")
    if goal["type"] == "debt_free" and not goal.get("deficit"):  # 적자 상태에서는 예금을 대출에 쓰지 않는다(sweep 끔)
        out.append("예금이 비상금을 넘으면 금리가 높은 대출부터 더 갚아요")
    if goal.get("target_growth"):
        out.append(f"집값은 해마다 {goal['target_growth']:g}% 올라요")
    elif goal["type"] == "reach_target" and (family.get("goal_input") or {}).get("category") == "home":
        out.append("집값은 지금 그대로로 봤어요")
    return out


def build_request(family: dict, goal: dict, specs: list[dict]) -> dict:
    p = profile(family)
    loans = []
    for it in family["finance"]:
        if it["kind"] != "loan" or not it["amount"]:
            continue
        lease = it["loan_type"] == "lease"
        loans.append({"id": it["item_id"], "label": it["label"], "balance": it["amount"], "rate": it["rate"],
                      "kind": "interest_only" if lease else "amortizing", "payment": it.get("payment", 0),
                      "in_pool": lease and goal["pool_includes_lease"]})
    aux = []
    if p["home_total"]:
        aux.append({"id": "home", "kind": "asset", "value": p["home_total"], "label": "집(시세)"})
    if p["lease_deposit_total"] and not goal["pool_includes_lease"]:
        aux.append({"id": "lease", "kind": "asset", "value": p["lease_deposit_total"], "label": "전세 보증금"})
    if any(pol["policy"] == "reverse_mortgage" for s in specs for pol in s["policies"]):
        aux.append({"id": "rm_debt", "kind": "debt", "value": 0, "label": "주택연금으로 받은 돈(갚을 몫)"})
    if any(pol["policy"] == "sell_home" for s in specs for pol in s["policies"]) and not p["home_total"]:
        raise PlanError("집이 없어서 집 팔기를 고를 수 없어요")
    options = []
    for s in specs:
        o = engine_option(family, goal, s)
        o.pop("meta")
        for c in o["cashflows"]:
            c.pop("item_id", None)
        options.append(o)
    eg = {"type": goal["type"], "label": goal["label"], "target_amount": goal.get("target_amount", 0),
          "target_growth": goal.get("target_growth", 0.0)}
    if goal.get("within_months"):
        eg["within_months"] = goal["within_months"]
    return {"scenario_id": family.get("preset_id") or "custom", "horizon_months": goal["horizon_months"],
            "start": {"goal_pool": goal["start_pool"], "idle_pool": goal.get("idle_pool", 0.0), "pool_label": goal["pool_label"],
                      "aux_accounts": aux, "loans": loans, "floor": goal.get("floor", 0.0), "illiquid": goal.get("illiquid", 0.0)},
            "income_growth": goal.get("income_growth", 0.0),
            "sweep": goal["type"] == "debt_free" and goal.get("sweep", True) and not goal.get("deficit"),  # 적자 상태면 예금을 대출에 쓰지 않는다(버틸 돈이 먼저)
            "min_until": (goal.get("life") or {}).get("to", 0) if (goal.get("life") or {}).get("kind") == "baby" else 0,
            "goal": eg, "options": options, "inflation": assumptions()["inflation"]["rate"],
            "member_context": {"base_age": goal["base_age"]}, "range": {"paths": RANGE_PATHS, "seed": 1000}}


def design_context(family: dict, goal: dict, cut_max: float | None = None) -> dict:
    """역할 5에 주는 설계 재료(가족 금융 요약은 pipeline이 공개 범위대로 따로 넣는다)."""
    a = assumptions()
    b = _bounds(family)
    p = profile(family)
    return {
        "returns": [{"id": r["id"], "label": r["label"], "expected_return": r["expected_return"],
                     "used_in_calc": max(0.0, round(net_return(r) + goal.get("return_delta", 0.0), 2)),
                     "tax": "세후(이자소득세 15.4% 뺌)" if r.get("after_tax") else "세금 전", "source": r.get("source", "")}
                    for r in a["returns"]],  # source: 공시 통계로 정한 값인지 체험용 가정값인지(근거 문장에 쓸 수 있다)
        "inflation": f"생활비 같은 지출에 연 {pct(a['inflation']['rate'])} 물가 상승률을 엔진이 자동으로 붙여요",
        "policies": policy_menu(family, goal),
        "floor": goal.get("floor", 0.0),
        "deficit": ({"monthly_gap": goal["deficit"]["monthly_gap"], "note": ("은퇴(퇴직) 뒤에는 " if goal["deficit"].get("future_from_month") else "") + "생활비를 한도까지 줄여도 비상금을 못 지키는 적자 상태예요"}
                    if goal.get("deficit") else None),
        "monthly_spare": round(p["income_total"] - p["expense_total"] - p["loan_payment_total"], 1),  # 지금 한 달에 남는 돈(여유 지출을 늘릴 수 있는 한계의 참고)
        "auto_included": life_lines(family, goal),
        "expense_cut_max": cut_max if cut_max is not None else round(
            sum(i["amount"] for i in family["finance"] if i["kind"] in ("expense", "transfer_out")) * a["limits_realism"]["expense_cut_ratio"], 1),
        "limits": {"monthly_adjustment_abs_max": b["adjust"], "event_abs_max": b["event"],
                   "spending_lump_abs_max": b["lump"], "max_adjustments": b["max_adjustments"],
                   "max_events": b["max_events"], "max_lumps": b["max_lumps"], "horizon_months": goal["horizon_months"]},
        "today": today_label(family),
    }



# ---------- 적자 상태(2026-11-15 형님 결정 A, 시안12) ----------
def _spend_items(family: dict) -> list[dict]:
    return [i for i in family["finance"] if i["kind"] in ("expense", "transfer_out") and i["amount"]]


def deficit_info(family: dict, goal: dict, cut: float | None = None) -> dict | None:
    """생활비·용돈을 한도(지금의 20%)까지 줄이고 아무것도 더 안 써도 예금이 비상금 선을 못 지키면 '적자 상태'(코드 판정, AI 아님).
    모으기·대출 목표만(노후·간병은 예금이 줄어드는 게 결과 자체). {monthly_gap, cut_max, best_breach_month, income, outflow} 또는 None."""
    if goal["type"] not in ("reach_target", "debt_free"):
        return None
    from engine import simulate
    p = profile(family)
    flow = round(p["income_total"] - p["expense_total"] - p["loan_payment_total"], 1)
    we = (goal.get("life") or {}).get("work_end")  # 곧 은퇴(퇴직)하는 분이 있으면, 지금은 흑자여도 그 뒤의 적자까지 본다(2026-11-20)
    if flow >= 0 and not we:
        return None
    if cut is None:
        cut = round(sum(i["amount"] for i in _spend_items(family)) * assumptions()["limits_realism"]["expense_cut_ratio"], 1)
    g = {**goal, "deficit": None, "sweep": False}
    spec = check_option(family, g, {"option_id": "A", "label": "최선", "return_id": "safe",
                                    **({"adjustments": [{"label": "생활비·용돈 줄이기(한도까지)", "amount": cut, "reason": "적자 판정"}]} if cut else {})})
    req = build_request(family, g, [spec])
    req["range"] = {"paths": 0, "seed": 1}
    r = simulate(req, include_monthly=bool(we))["results"][0]
    start_cash = goal["start_pool"] - goal.get("idle_pool", 0.0) - goal.get("illiquid", 0.0)
    need = min(goal.get("floor", 0.0), max(start_cash, 0.0))
    if r["min_cash"] is None or r["min_cash"] >= need - 0.5:
        return None
    if flow >= 0:  # 지금은 흑자: 은퇴(퇴직) 뒤 첫 달 기준 적자를 보여 준다
        row = r["monthly"][min(len(r["monthly"]) - 1, we["month"] - 1)]
        return {"monthly_gap": round(max(-(row["inflow"] + row["outflow"]), 0.0), 1), "cut_max": cut, "best_breach_month": r.get("floor_breach_month"),
                "income": round(row["inflow"], 1), "outflow": round(-row["outflow"], 1), "future_from_month": we["month"]}
    return {"monthly_gap": -flow, "cut_max": cut, "best_breach_month": r.get("floor_breach_month"),
            "income": p["income_total"], "outflow": round(p["expense_total"] + p["loan_payment_total"], 1)}


def deficit_levers(family: dict, goal: dict) -> dict:
    """적자 메우기 표: 가족이 이미 가진 것(지출·대출·집)으로 할 수 있는 일마다 매달(또는 한 번에) 얼마를 메우는지와, 합쳐서 적자가 없어지는지(지금 기준, 엔진 계산).
    ✅ 형님 결정(2026-11-15): 부족한 돈을 새로 벌라는 방법(재취업·부업, '○님이 벌면')은 넣지 않는다. 안 되면 안 된다고 말한다."""
    from engine.policies import extend_term, sell_home
    a, p = assumptions(), profile(family)
    ratio = a["limits_realism"]["expense_cut_ratio"]
    gap = round(-(p["income_total"] - p["expense_total"] - p["loan_payment_total"]), 1)
    rows, cuts, ext_total = [], 0.0, 0.0
    for i in _spend_items(family):
        v = round(i["amount"] * ratio, 1)
        cuts += v
        rows.append({"label": f"{i['label']} {round(ratio * 100)}% 줄이기", "monthly": v, "note": ""})
    for lid in p["repaying_loans"]:
        loan = next(i for i in family["finance"] if i["item_id"] == lid)
        years = 40 if loan["loan_type"] == "mortgage" else 5
        ex = extend_term(loan["amount"], loan["rate"], loan.get("payment", 0), years)
        if ex["monthly_saving"] > 0:
            ext_total += ex["monthly_saving"]
            rows.append({"label": f"{loan['label']} 기간 늘리기(앞으로 {years}년)", "monthly": ex["monthly_saving"],
                         "note": f"대신 총 이자 약 {won(ex['extra_interest'])} 늘어요 · 금융회사 확인 필요"})
    after = round(gap - cuts - ext_total, 1)
    home_fix = 0.0
    if p["home_total"]:
        morts = [i for i in family["finance"] if i["kind"] == "loan" and i["loan_type"] == "mortgage" and i["amount"]]
        mort_bal = sum(i["amount"] for i in morts)
        ratios = sorted(a["sell_home"]["new_home_ratios"], reverse=True)  # 큰 집부터: 그 집 대출을 다 갚을 수 있는 가장 큰 새 집
        fit = next((r for r in ratios if morts and sell_home(p["home_total"], r)["net"] >= mort_bal), None)
        sh = sell_home(p["home_total"], fit or 0.7)
        if fit:  # 판 돈으로 그 집 대출을 다 갚으면 매달 상환액이 없어진다(2026-11-15 실제 AI 결과에서 발견)
            home_fix = round(sum(i.get("payment", 0) for i in morts), 1)
            note = f"판 돈 약 {won(sh['net'])}으로 주택담보대출을 다 갚으면 매달 상환 {won(home_fix)}이 없어지고 약 {won(sh['net'] - mort_bal)}이 남아요 · 큰 결정"
            rows.append({"label": f"집을 줄여 이사(시세의 {fit * 100:g}% 집으로)", "monthly": home_fix, "note": note})
        else:
            rows.append({"label": "집을 줄여 이사(시세의 70% 집으로)", "monthly": None, "once": sh["net"],
                         "note": f"한 번에 약 {won(sh['net'])}" + (f" · 지금 적자 약 {sh['net'] / gap / 12:.0f}년치" if gap > 0 else "") + " · 큰 결정"})
    rm = _reverse_mortgage_monthly(family, goal) if p["home_total"] else None
    if rm:
        rows.append({"label": "주택연금(지금 집에 살면서 매달 받기)", "monthly": rm[0], "note": rm[1]})
    combos = [f"지출 {round(ratio * 100)}% 줄이기 + 대출 기간 늘리기 → " + (f"매달 약 {won(-after)} 남아요" if after <= 0 else f"매달 약 {won(after)} 모자라요(아직 적자)")]
    solvable = after <= 0
    if after > 0 and rm and rm[0] >= after:
        combos.append(f"여기에 주택연금(월 {won(rm[0])})을 받으면 적자가 없어져요")
        solvable = True
    if not solvable and home_fix:
        left = round(gap - cuts - home_fix, 1)  # 집을 줄이면 대출 기간 늘리기는 필요 없다(대출이 없어지므로)
        combos.append(f"지출 {round(ratio * 100)}% 줄이기 + 집을 줄여 대출 갚기 → " + (f"매달 약 {won(-left)} 남아요(큰 결정이에요)" if left <= 0 else f"매달 약 {won(left)} 모자라요"))
        solvable = left <= 0
    if not solvable:
        combos.append("지금 가진 방법들로는 매달 적자를 메울 수 없어요")
    return {"gap": gap, "rows": rows, "combos": combos, "solvable": solvable}



# ---------- 생활비 줄이기 한도(2026-11-15 형님 결정: 가족이 말한 금액까지 허용) ----------
_CUT_WORDS = ("줄이", "줄일", "줄여", "아끼", "아낄", "아껴", "절약", "덜 쓰", "덜쓰")
_NOT_CUT = ("상환", "갚", "대출", "늘리", "늘릴", "모으", "모을", "저축", "벌", "수입")


def stated_cut(summaries: dict | None) -> float:
    """각자의 생각 요약('양보할 수 있는 것')에서 '이만큼 줄일 수 있다'는 금액을 찾는다(문장마다, 줄이기 말이 있고
    상환·저축·수입 말이 없을 때만). 여러 사람이 말하면 가장 큰 금액(같은 생활비를 말하는 경우가 많아 더하지 않는다)."""
    from verify import find_numbers
    best = 0.0
    for s in (summaries or {}).values():
        text = str((s or {}).get("flexible", ""))
        for sent in [x for x in text.replace("·", " ").replace("\n", ".").split(".") if x.strip()]:
            if not any(w in sent for w in _CUT_WORDS) or any(w in sent for w in _NOT_CUT):
                continue
            for h in find_numbers(sent):
                if h.kind == "money":
                    best = max(best, float(h.value))
    return round(best, 1)


def cut_limit(family: dict, summaries: dict | None = None) -> float:
    """방법이 생활비·용돈을 줄일 수 있는 한도(만원/월) = max(지금 지출의 20%, 가족이 말한 금액). 가족이 말해도 지금 지출의 절반을 넘지는 않는다."""
    total = sum(i["amount"] for i in family["finance"] if i["kind"] in ("expense", "transfer_out"))
    base = total * assumptions()["limits_realism"]["expense_cut_ratio"]
    return round(min(max(base, stated_cut(summaries)), total * 0.5), 1)
