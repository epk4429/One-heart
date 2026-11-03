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

GOAL_TYPES = {"reach_target": "목표 금액 모으기", "runway": "예금이 버티는 기간", "debt_free": "대출 다 갚기"}
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
    if t == "reach_target":
        pool = p["liquid_total"] + p["lease_deposit_total"] - p["lease_loan_total"]
        parts = [f"예금·투자 {won(p['liquid_total'])}"]
        if p["lease_deposit_total"]:
            parts.append(f"전세 보증금 {won(p['lease_deposit_total'])}")
        if p["lease_loan_total"]:
            parts.append(f"전세대출 −{won(p['lease_loan_total'])}")
        goal["pool_includes_lease"] = True
    else:
        pool = p["liquid_total"]
        parts = [f"예금·투자 {won(p['liquid_total'])}"]
        goal["pool_includes_lease"] = False
    goal["start_pool"] = round(pool, 1)
    if t == "reach_target" and goal["target_amount"] <= goal["start_pool"]:
        raise PlanError(f"목표 금액은 지금 모여 있는 돈({won(goal['start_pool'])}, {' + '.join(parts)})보다 커야 해요")
    goal["pool_label"] = " + ".join(parts).replace("+ 전세대출 −", "− 전세대출 ")
    return goal


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
    """주택연금 월 수령액: 한국주택금융공사 월지급금 예시표(ontology/programs.json, 원문 인용)에서 부부 중 젊은 사람 나이·집 시세로.
    2026-11-03 전에는 가상 비율(집값 × 나이별 %, 임의결정 25)이었다."""
    from ontology.programs import judge, reverse_mortgage_age, reverse_mortgage_monthly
    home = profile(family)["home_total"]
    if not home or judge("PG_reverse_mortgage", family)["status"] == "not_eligible":
        return None  # 집 주인 부부가 55세 미만 등 공식 조건에 확실히 안 맞으면 미래 계산에도 내놓지 않는다
    m = reverse_mortgage_monthly(reverse_mortgage_age(family), home)
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
    for lid in p["repaying_loans"]:
        loan = next(i for i in family["finance"] if i["item_id"] == lid)
        out.append({"policy": "extra_repayment", "label": f"{loan['label']} 더 갚기", "params": {"item_id": lid,
                    "amount": f"한 달에 더 갚을 돈(만원, {_bounds(family)['adjust']} 이하)"},
                    "effect": "모이는 돈은 줄고, 대출을 더 빨리 갚아요"})
        out.append({"policy": "lump_repayment", "label": f"{loan['label']} 예금으로 한 번에 갚기", "params": {
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


def check_option(family: dict, goal: dict, spec: dict, *, allowed_ids=OPTION_IDS) -> dict:
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
    hidden = {k for k, v in family["disclosure"].items() if v in ("hide", "summary_only")}
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
        if name not in menu and name not in ("extra_repayment", "lump_repayment"):
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
        elif name == "lump_repayment":
            lid = pol.get("item_id")
            if lid not in profile(family)["repaying_loans"]:
                raise PlanError(f"{pw}.item_id는 갚아 나가는 대출 id여야 해요")
            liquid = profile(family)["liquid_total"]
            out["policies"].append({"policy": name, "item_id": lid, "month": _num(pol, "month", pw, 1, H, True),
                                    "amount": _num(pol, "amount", pw, 1, max(1, liquid))})
        else:
            lid = pol.get("item_id")
            if lid not in profile(family)["repaying_loans"]:
                raise PlanError(f"{pw}.item_id는 갚아 나가는 대출 id여야 해요")
            out["policies"].append({"policy": name, "item_id": lid, "amount": _num(pol, "amount", pw, 1, b["adjust"])})
        used.add(name)
    if {"reverse_mortgage", "sell_home"} <= used:
        raise PlanError(f"{w}: 주택연금과 집 팔기는 함께 고를 수 없어요")
    return out


def _cat(kind: str) -> str:
    return {"income": "income", "transfer_in": "transfer", "expense": "expense", "transfer_out": "transfer"}[kind]


def engine_option(family: dict, goal: dict, spec: dict) -> dict:
    """정리된 spec → 엔진 Option. meta에는 화면·해석용 설명을 담는다."""
    rets = {r["id"]: r for r in assumptions()["returns"]}
    ret = rets[spec["return_id"]]
    over = {c["item_id"]: c for c in spec["monthly_changes"]}
    cashflows, changes = [], []
    for it in family["finance"]:
        if KINDS[it["kind"]][0] != "monthly":
            continue
        amt = over[it["item_id"]]["amount"] if it["item_id"] in over else it["amount"]
        if it["item_id"] in over and amt != it["amount"]:
            changes.append(f"{it['label']} 월 {won(it['amount'])} → {won(amt)} ({over[it['item_id']]['reason']})")
        if amt:
            cashflows.append({"label": it["label"], "amount": KINDS[it["kind"]][1] * amt, "category": _cat(it["kind"]),
                              "item_id": it["item_id"]})
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
    aux_changes, extra, prepay = [], [], []
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
            sh = assumptions()["sell_home"]
            home = profile(family)["home_total"]
            net = round(home * (1 - pol["new_home_ratio"]) - home * sh["cost_ratio"])
            lumps.append({"month": pol["month"], "amount": net, "label": "집 팔고 남는 돈"})
            aux_changes.append({"type": "set", "account_id": "home", "month": pol["month"],
                                "value": round(home * pol["new_home_ratio"])})
            changes.append(f"{pol['month']}개월째 집을 팔고 시세 {pol['new_home_ratio'] * 100:g}% 집으로 옮겨요. 남는 돈 {won(net)}")
        elif pol["policy"] == "lump_repayment":
            loan = next(i for i in family["finance"] if i["item_id"] == pol["item_id"])
            prepay.append({"loan_id": pol["item_id"], "month": pol["month"], "amount": pol["amount"]})
            changes.append(f"{pol['month']}개월째 예금 {won(pol['amount'])}으로 {loan['label']} 한 번에 갚기")
        else:
            loan = next(i for i in family["finance"] if i["item_id"] == pol["item_id"])
            extra.append({"loan_id": pol["item_id"], "monthly": pol["amount"]})
            changes.append(f"{loan['label']} 한 달 {won(pol['amount'])} 더 갚기")
    changes.insert(0, f"돈을 불리는 방식: {ret['label']}(연 {pct(ret['expected_return'])} 가정)")
    return {"option_id": spec["option_id"], "label": spec["label"], "description": spec["description"],
            "expected_return": ret["expected_return"], "volatility": ret["volatility"], "return_assumption_id": ret["id"],
            "cashflows": cashflows, "events": events, "lump_sums": lumps, "aux_changes": aux_changes,
            "extra_payments": extra, "loan_prepayments": prepay,
            "meta": {"changes": changes, "return_label": ret["label"]}}


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
    eg = {"type": goal["type"], "label": goal["label"], "target_amount": goal.get("target_amount", 0)}
    if goal.get("within_months"):
        eg["within_months"] = goal["within_months"]
    return {"scenario_id": family.get("preset_id") or "custom", "horizon_months": goal["horizon_months"],
            "start": {"goal_pool": goal["start_pool"], "pool_label": goal["pool_label"], "aux_accounts": aux, "loans": loans},
            "goal": eg, "options": options, "inflation": assumptions()["inflation"]["rate"],
            "member_context": {"base_age": goal["base_age"]}, "range": {"paths": RANGE_PATHS, "seed": 1000}}


def design_context(family: dict, goal: dict) -> dict:
    """역할 5에 주는 설계 재료(가족 금융 요약은 pipeline이 공개 범위대로 따로 넣는다)."""
    a = assumptions()
    b = _bounds(family)
    return {
        "returns": [{"id": r["id"], "label": r["label"], "expected_return": r["expected_return"]} for r in a["returns"]],
        "inflation": f"생활비 같은 지출에 연 {pct(a['inflation']['rate'])} 물가 오름을 엔진이 자동으로 붙여요",
        "policies": policy_menu(family, goal),
        "limits": {"monthly_adjustment_abs_max": b["adjust"], "event_abs_max": b["event"],
                   "spending_lump_abs_max": b["lump"], "max_adjustments": b["max_adjustments"],
                   "max_events": b["max_events"], "max_lumps": b["max_lumps"], "horizon_months": goal["horizon_months"]},
        "today": today_label(family),
    }
