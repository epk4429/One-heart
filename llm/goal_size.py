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
from engine.schema import MAX_CASHFLOW, MAX_HORIZON

from . import family as F
from . import goals
from . import world_size
from .plan import PlanError, build_request, check_option, normalize_goal

BASE_RETURN = "safe"          # 예금·적금만(가정값 표, 공시 금리 중앙값)
YEARS = (3, 5, 10)            # '지금처럼 모으면' 보여 주는 해
DEBT_YEARS = (5, 10, 15, 20)  # 대출 갚기: '이 기간 안에 갚으려면' 후보(2026-11-15)
RETIRE_RATIOS = (0.6, 0.8, 1.0, 1.2)  # 노후 준비: 은퇴 뒤 한 달 쓰는 돈 후보 = 지금 생활비 × 이 비율(2026-11-15)


def _years_label(months: int | None) -> str:
    if not months:
        return ""
    y, m = divmod(int(months), 12)
    return f"{y}년" + (f" {m}개월" if m else "") if y else f"{m}개월"


def _run(fam: dict, goal: dict, extra_monthly: float = 0.0, extra_repay: tuple[str, float] | None = None) -> dict:
    """'지금처럼' 한 가지 조건으로 계산. extra_monthly: 지금보다 더 모으는 돈, extra_repay: (대출 id, 매달 더 갚는 돈)."""
    spec = check_option(fam, goal, {"option_id": "A", "label": "지금처럼", "return_id": BASE_RETURN})
    req = build_request(fam, goal, [spec])
    req["range"] = {"paths": 0, "seed": 1}
    if extra_monthly:
        req["options"][0]["cashflows"].append({"label": "지금보다 더 모으는 돈", "amount": round(extra_monthly, 1),
                                               "category": "adjustment"})
    if extra_repay and extra_repay[1]:
        req["options"][0]["extra_payments"].append({"loan_id": extra_repay[0], "monthly": round(extra_repay[1], 1)})
    sim = simulate(req, include_monthly=False)
    if "error" in sim:
        raise PlanError(str(sim["error"]))
    return sim["results"][0]


def _rate_note() -> str:
    r = next(x for x in F.assumptions()["returns"] if x["id"] == BASE_RETURN)
    from .plan import net_return
    return f"지금의 매달 수입·지출·대출 상환 그대로, 모은 돈은 {r['label']}(세후 연 {net_return(r):g}%)으로 불린다고 가정했어요. 생활비는 물가만큼 올라요."


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


def _debt_row(fam: dict, base: dict, months: int, cut_max: float) -> dict:
    """한 기한의 결과 줄: 남는 돈 규칙 위에서, 그 기한 안에 갚으려면 매달 얼마가 더 있어야 하나(생활비 줄이기·수입 증가)."""
    need = _need_monthly(fam, base, months)
    if need == 0:
        disp, note, warn = "지금 속도로도 닿아요", "", False
    elif need is None:
        disp, note, warn = "매달 더 모아도 어려워요", "", True
    else:
        warn = need > cut_max
        disp = f"매달 {won(need)} 더 있어야 해요"
        note = f"생활비를 줄여 마련하기엔 커요(지금 지출의 20%는 {won(cut_max)})" if warn else ""
    return {"label": f"{_years_label(months)} 안에 갚으려면", "display": disp, "note": note, "warn": warn}


def _debt_options(fam: dict, raw: dict, base: dict, p: dict) -> dict:
    """'언제까지 다 갚고 싶나요'를 정할 때 보는 것(엔진 계산, 시안10·11): entered = 가족이 적은 기한의 결과 한 줄, rows = 참고 목록(5·10·15·20년).
    남는 돈과 비상금 선을 넘는 예금은 이미 금리 높은 대출부터 갚는다고 보고, 그보다 빨리 갚으려면 매달 얼마가 더 있어야 하는지 낸다."""
    cut_max = round(p["expense_total"] * F.assumptions()["limits_realism"]["expense_cut_ratio"], 1)
    wm = raw.get("within_months")
    return {"key": "within_years", "other_title": "다른 기간이라면",
            "entered": _debt_row(fam, base, int(wm), cut_max) if wm else None,
            "rows": [_debt_row(fam, base, y * 12, cut_max) for y in DEBT_YEARS],
            "note": "남는 돈과 비상금을 넘는 예금은 금리가 높은 대출부터 더 갚는다고 계산했어요. '더 있어야 해요'는 생활비를 줄이거나 수입이 늘어 매달 더 생겨야 하는 돈이에요.",
            "footer": "이 차이를 어떻게 메울지는 다음 단계(미래 계산)에서 함께 봐요"}


def _retire_row(fam: dict, raw: dict, age: float, base_id: str, pool: float, n: float, end_age: int, pension: float = 0.0) -> dict:
    """한 금액의 결과 줄: 은퇴 뒤 한 달에 n만원 쓰면(연금을 입력했으면 연금을 받으며) 예금이 비상금 선까지 몇 세에 내려가나."""
    fin = [{"item_id": "f1", "owner_id": "joint", "kind": "deposit", "label": "은퇴할 때 예금", "amount": round(pool, 1)},
           {"item_id": "f2", "owner_id": "joint", "kind": "expense", "label": "은퇴 후 생활비", "amount": n}]
    if pension:
        fin.append({"item_id": "f3", "owner_id": "joint", "kind": "transfer_in", "label": "은퇴 후 연금", "amount": pension})
    fam2 = {**fam, "members": [{**m, "age": age} if m["member_id"] == base_id else m for m in fam["members"]],
            "disclosure": {}, "goal_input": None, "finance": fin}  # 은퇴한 뒤만 계산(월급 없음, 앞으로의 일은 이미 반영)
    g2 = normalize_goal(fam2, {"type": "runway", "label": raw.get("label", ""), "base_member_id": base_id, "floor": raw.get("floor")})
    hit = _run(fam2, g2)["goal_hit_month"]
    if hit:
        disp, warn = f"예금이 약 {int(age + hit // 12)}세까지 가요", True
    else:
        disp, warn = f"예금이 {end_age}세 넘게 남아요", False
    return {"label": f"한 달에 {won(n)} 쓰면", "display": disp, "note": "", "warn": warn}


def _retire_calc(fam: dict, raw: dict, v: dict, p: dict) -> tuple[float | None, dict | None]:
    """노후·은퇴 준비: (은퇴할 때 예금, 결과·참고 목록). 은퇴할 때 예금은 '지금처럼' 모아 갔을 때의 엔진 값.
    은퇴 뒤에는 수입 없이 예금에서만 쓴다고 보고, 그때 남은 대출은 넣지 않는다."""
    age, base_id = v.get("retire_age"), v.get("base_member_id")
    if not age or not base_id:
        return None, None
    g = normalize_goal(fam, {**raw, "within_months": None})
    k = int(round(age - g["base_age"]))
    if k <= 0:
        pool = g["start_pool"]
    else:
        ys = _run(fam, g)["yearly"]
        if k > len(ys):
            return None, None
        pool = ys[k - 1]["end"]
    if pool <= 0:
        return pool, None
    # 엔진은 최대 30년(MAX_HORIZON)까지만 계산하므로, 그 안에 안 바닥나면 '그 나이까지 확인했다'고만 말한다(100세로 단정하지 않음)
    end_age = min(F.assumptions()["horizon_months"]["runway_until_age"], int(age) + MAX_HORIZON // 12)
    base = max(p["expense_total"], 50)
    needs = sorted({max(50, int(round(base * r / 10)) * 10) for r in RETIRE_RATIOS})
    entered, pen = v.get("monthly_need"), v.get("pension_monthly") or 0.0
    return pool, {"key": "monthly_need", "other_title": "다른 금액이라면",
                  "entered": _retire_row(fam, raw, age, base_id, pool, entered, end_age, pen) if entered else None,
                  "rows": [_retire_row(fam, raw, age, base_id, pool, n, end_age, pen) for n in needs],
                  "note": ("은퇴한 뒤에는 월급 없이 " + (f"연금 월 {won(pen)}과 예금으로" if pen else "예금으로만(연금은 입력하지 않음)")
                           + " 산다고 계산했어요. 비상금 선까지 내려가는 때를 봤어요. 은퇴할 때 남은 대출은 넣지 않았어요. 생활비는 물가만큼 올라요."),
                  "footer": f"예금이 바닥나면(주황색) 부족한 부분을 어떻게 메울지는 다음 단계(미래 계산)에서 함께 봐요"}


def _leave_gap(fam: dict, raw: dict) -> tuple[float, dict] | None:
    """육아: 휴직 동안 줄어드는 수입(휴직하는 분의 월급 − 휴직 중 수입, 월급 상승 반영, 엔진 계산, 2026-11-15)."""
    g = normalize_goal(fam, {**raw, "target_amount": 1_000_000, "within_months": None})
    life = g.get("life") or {}
    if life.get("kind") != "baby":
        return None

    def inflows(goal):
        spec = check_option(fam, goal, {"option_id": "A", "label": "지금처럼", "return_id": BASE_RETURN})
        req = build_request(fam, goal, [spec])
        req["range"] = {"paths": 0, "seed": 1}
        return [m["inflow"] for m in simulate(req, include_monthly=True)["results"][0]["monthly"]]
    a, b = inflows({**g, "life": {}}), inflows(g)
    gap = sum(a[m - 1] - b[m - 1] for m in range(life["from"], life["to"] + 1) if m <= len(a))
    return round(gap, -1), life


def anchors(fam: dict, gi: dict, with_options: bool = False) -> dict:
    """우리 가족 기준. {"lines": [{"label","display","note"}], "facts": {fact_id: fact}, "note": 가정 설명}.
    facts는 가족이 정하는 값과 상관없는 기준점만 담는다(AI 설명 문장이 숫자를 고쳐도 낡지 않게).
    with_options: 대출 갚기·노후 준비에서 숫자를 정할 때 보는 후보표("options")도 계산한다(화면용, 시뮬레이션이 여러 번 돌아 AI 입력에는 쓰지 않는다)."""
    v = gi["fields"]
    raw = goals.derive_goal(gi, fam["members"])
    p = F.profile(fam)
    lines, facts = [], []
    options = None

    def add(fid: str, value, unit: str, display: str, label: str, note: str = "", fixed: bool = True, key: bool | None = None):
        # key: 가족이 정한 목표와 직접 이어지는 줄(화면이 맨 위에 한 줄로 먼저 보여 주고, 나머지는 '자세히 보기'에 접는다)
        lines.append({"label": label, "display": display, "note": note, "key": (not fixed) if key is None else key})
        if fixed:
            facts.append(F._fact(fid, value, unit, display, label))

    if raw["type"] == "reach_target":
        base = normalize_goal(fam, {**raw, "target_amount": 1_000_000, "within_months": None})
        r = _run(fam, base)
        add("size.pool", base["start_pool"], "만원", won(base["start_pool"]), "보유 자산", base["pool_label"])
        add("size.flow", r["monthly_flow"], "만원/월", "월 " + won(r["monthly_flow"]), "이번 달 모이는 돈",
            "월 수입 − 월 지출 − 대출 상환")
        yrs = sorted(set(YEARS) | ({round(raw["within_months"] / 12)} if raw.get("within_months") else set()))
        for y in yrs:
            if y <= len(r["yearly"]):
                end = r["yearly"][y - 1]["end"]
                add(f"size.after_{y}y", end, "만원", won(end), f"지금처럼 모으면 {y}년 뒤", "", fixed=y in YEARS)
        if gi["category"] == "baby":  # 육아 준비금의 기준: 휴직 동안 줄어드는 수입(2026-11-15 형님 결정, 목표 뜻 = 휴직이 끝날 때까지 비상금을 지키며 준비금 모으기)
            lg = _leave_gap(fam, raw)
            if lg:
                gap, life = lg
                who = F.member(fam, life["member_id"])["name"]
                add("size.leave_gap", gap, "만원", won(gap), "휴직 동안 줄어드는 수입",
                    f"{life['to'] - life['from'] + 1}개월 동안 {who}님 월급 − 휴직 중 수입", key=True)
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
        plain = _run(fam, {**base, "sweep": False})  # 지금 상환액대로만(남는 돈은 예금에 쌓임)
        r = _run(fam, base)  # 남는 돈 규칙: 예금이 비상금 선을 넘는 만큼 대출을 더 갚음(2026-11-15)
        add("size.loan", r["start_debt"], "만원", won(r["start_debt"]), "갚아 나가는 대출 잔액", key=False)
        dm = plain["debt_free_month"]
        add("size.payoff", dm, "month", f"약 {_years_label(dm)} 뒤" if dm else f"{base['horizon_months'] // 12}년 넘게",
            "지금 상환액대로만 갚으면 다 갚는 때", key=False)
        ds = r["debt_free_month"]
        add("size.payoff_sweep", ds, "month", f"약 {_years_label(ds)} 뒤" if ds else f"{base['horizon_months'] // 12}년 넘게",
            "남는 돈을 대출에 쓰면 다 갚는 때", f"비상금 {won(base['floor'])}을 남기고 남는 돈과 그 위의 예금으로 금리 높은 대출부터 더 갚을 때"
            if base["floor"] else "비상금을 정하면 그만큼은 남기고 계산해요", key=True)
        add("size.flow", r["monthly_flow"], "만원/월", "월 " + won(r["monthly_flow"]), "한 달에 남는 돈",
            "월 수입 − 월 지출 − 대출 상환", key=True)
        if with_options:
            options = _debt_options(fam, raw, base, p)
    if gi["category"] == "retire":
        add("size.expense", p["expense_total"], "만원/월", "월 " + won(p["expense_total"]), "지금 한 달 생활비",
            "대출 상환은 빼고, 생활비·용돈 등 나가는 돈", key=True)
        if with_options:
            pool, options = _retire_calc(fam, raw, v, p)
            if pool is not None:
                age = v["retire_age"]
                add("", None, "", "약 " + won(max(pool, 0)) if pool > 0 else "은퇴 전에 바닥나요",
                    f"{int(age)}세에 은퇴할 때 예금·투자", "지금처럼 모아 갔을 때", fixed=False)
    out = {"lines": lines, "facts": {f["fact_id"]: f for f in facts}, "note": _rate_note() if facts else ""}
    if options:
        out["options"] = options
    return out


def size(fam: dict, values: dict | None = None, world: dict | None = None) -> dict | None:
    """2단계 화면에 줄 것: 정할 숫자 칸, 우리 가족 기준, 통계 기준(있는 카테고리만), (다 정했으면) 계산할 목표.
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
    p = F.profile(fam)
    month_out = round(p["expense_total"] + p["loan_payment_total"], 1)
    floor_ref = {"monthly_out": month_out, "m3": round(month_out * 3, -1), "m6": round(month_out * 6, -1),
                 "deposits": round(sum(i["amount"] for i in fam["finance"] if i["kind"] == "deposit"), 1)}  # 비상금 참고(2026-11-15)
    out = {"fields": fields, "missing": goals.missing(merged), "goal_raw": None, "goal": None, "message": "", "floor_ref": floor_ref,
           "details": goals.details_text(merged, fam["members"]), "world": world_size.world(fam, merged, world)}
    try:  # 적자 상태(2026-11-15 시안12): 숫자 정하기에서 미리 알려 준다(목표 금액이 아직 없으면 큰 값으로 판정만)
        rg = goals.derive_goal(merged, fam["members"])
        if rg["type"] == "reach_target" and not rg.get("target_amount"):
            rg["target_amount"] = 1_000_000
        out["deficit"] = normalize_goal(fam, rg).get("deficit")
    except PlanError:
        out["deficit"] = None
    try:
        out["anchors"] = anchors(fam, merged, with_options=True)
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
