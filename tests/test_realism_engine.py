"""미래 계산 현실성 바로잡기(할 일 1-9, 2026-11-15)의 엔진 규칙을 독립 계산과 대조한다.

비상금 선(floor)·주식 등 비상금으로 안 세는 몫(illiquid)·남는 돈으로 대출 더 갚기(sweep)·월급 상승(income_growth, grows)·
기간이 있는 수입·지출(from_month~to_month)·집값 상승(target_growth). 새 값을 안 쓰면 예전과 똑같이 계산된다(골든 테스트가 지킴).
"""

from engine import simulate


def _req(goal, cash, *, pool=2500, loans=(), horizon=360, **extra):
    req = {"scenario_id": "t", "horizon_months": horizon,
           "start": {"goal_pool": pool, "pool_label": "x", "aux_accounts": [], "loans": list(loans)},
           "goal": goal, "options": [{"option_id": "A", "label": "A", "expected_return": 3.3, "volatility": 0,
                                      "return_assumption_id": "", "cashflows": list(cash), "events": [], "lump_sums": [],
                                      "aux_changes": [], "extra_payments": [], "loan_prepayments": []}],
           "inflation": 0, "member_context": {"base_age": 35}, "range": {"paths": 0, "seed": 1}}
    for k, v in extra.items():
        if k in ("floor", "illiquid"):
            req["start"][k] = v
        else:
            req[k] = v
    return req


def _r(req):
    out = simulate(req, include_monthly=True)
    assert "error" not in out, out
    return out["results"][0]


MORT = {"id": "M", "label": "주택담보대출", "balance": 24000, "rate": 4.2, "kind": "amortizing", "payment": 118}
CRED = {"id": "C", "label": "신용대출", "balance": 3000, "rate": 6.0, "kind": "amortizing", "payment": 60}
PAY = [{"label": "월급", "amount": 720, "category": "income"}, {"label": "생활비", "amount": -400, "category": "expense"}]


def test_sweep_pays_loans_with_money_above_floor():
    """남는 돈 규칙: 예금이 비상금 선(1,000만원)을 넘는 만큼을 금리 높은 대출(신용 6%)부터 갚는다."""
    r = _r(_req({"type": "debt_free", "label": "d"}, PAY, loans=[MORT, CRED], floor=1000, sweep=True))
    # 독립 계산
    pool, bal, m, cash_min = 2500.0, {"M": 24000.0, "C": 3000.0}, 0, None
    rate, pay = {"M": 4.2, "C": 6.0}, {"M": 118, "C": 60}
    while bal["M"] + bal["C"] > 0.005:
        m += 1
        interest = max(pool, 0) * 0.033 / 12
        paid = 0.0
        for k in ("M", "C"):
            b = bal[k]
            if b <= 0:
                continue
            i = b * rate[k] / 1200
            p = pay[k]
            pr = p - i
            if pr >= b:
                pr, p = b, b + i
            bal[k] -= pr
            paid += p
        pool += interest + 720 - 400 - paid
        ex = pool - 1000
        for k in ("C", "M"):
            if ex > 0.005 and bal[k] > 0:
                x = min(bal[k], ex)
                bal[k] -= x
                pool -= x
                ex -= x
        cash_min = pool if cash_min is None else min(cash_min, pool)
    assert r["debt_free_month"] == m == r["goal_hit_month"]
    assert abs(r["min_cash"] - round(cash_min, 1)) < 0.2 and r["min_cash"] >= 1000 - 0.1
    assert r["monthly_flow"] == 142.0  # 첫 달 남는 돈으로 더 갚은 돈은 '매달 모이는 돈'에서 뺀다
    no_sweep = _r(_req({"type": "debt_free", "label": "d"}, PAY, loans=[MORT, CRED], floor=1000))
    assert r["debt_free_month"] < no_sweep["debt_free_month"] / 2  # 쌓아 두기만 하던 예전 그림보다 훨씬 빨리 갚는다


def test_floor_makes_reach_target_later_and_illiquid_is_not_cash():
    """내 집 마련: '예금 − 비상금'이 목표에 닿을 때 달성. 주식은 비상금으로 세지 않는다(min_cash에서 빠짐)."""
    goal = {"type": "reach_target", "label": "t", "target_amount": 8000}
    cash = [{"label": "월급", "amount": 300, "category": "income"}, {"label": "생활비", "amount": -200, "category": "expense"}]
    base = _r(_req(goal, cash, pool=1000))
    fl = _r(_req(goal, cash, pool=1000, floor=1000, illiquid=300))
    pool, m = 1000.0, 0
    while pool - 1000 < 8000:
        m += 1
        pool += pool * 0.033 / 12 + 100
    assert fl["goal_hit_month"] == m > base["goal_hit_month"]
    assert fl["min_cash"] == round(1000 - 300 + 1000 * 0.033 / 12 + 100, 1)  # 첫 달 끝 예금 − 주식


def test_runway_with_floor_counts_until_only_floor_is_left():
    goal = {"type": "runway", "label": "r"}
    cash = [{"label": "생활비", "amount": -150, "category": "expense"}]
    a = _r(_req(goal, cash, pool=20000))
    b = _r(_req(goal, cash, pool=20000, floor=3000))
    pool, m = 20000.0, 0
    while pool >= 3000:
        m += 1
        pool += pool * 0.033 / 12 - 150
    assert b["goal_hit_month"] == m < a["goal_hit_month"]


def test_wage_growth_and_windows():
    """월급(grows)에만 상승률, 기간이 있는 항목은 그 기간에만. 연금(grows 아님)은 그대로."""
    cash = [{"label": "월급", "amount": 400, "category": "income", "grows": True, "to_month": 120},
            {"label": "연금", "amount": 100, "category": "income", "from_month": 121},
            {"label": "생활비", "amount": -300, "category": "expense"}]
    r = _r(_req({"type": "runway", "label": "r"}, cash, pool=5000, horizon=240, income_growth=2.0, inflation=2.0))
    mo = r["monthly"]
    assert abs(mo[0]["inflow"] - 400) < 0.01
    assert abs(mo[12]["inflow"] - 400 * 1.02) < 0.01            # 13달째 = 1년 뒤 2% 오름
    assert abs(mo[119]["inflow"] - 400 * 1.02 ** (119 / 12)) < 0.01
    assert abs(mo[120]["inflow"] - 100) < 0.01                   # 121달째부터 월급 끝, 연금만(오르지 않음)
    assert abs(mo[120]["outflow"] + 300 * 1.02 ** (120 / 12)) < 0.01


def test_target_growth_moves_goal():
    goal = {"type": "reach_target", "label": "집", "target_amount": 8000}
    cash = [{"label": "월급", "amount": 200, "category": "income"}]
    flat = _r(_req(goal, cash, pool=1000))
    up = _r(_req({**goal, "target_growth": 2.0}, cash, pool=1000))
    pool, m = 1000.0, 0
    while True:
        m += 1
        pool += pool * 0.033 / 12 + 200
        if pool >= 8000 * 1.02 ** ((m - 1) / 12):
            break
    assert up["goal_hit_month"] == m > flat["goal_hit_month"]


def test_defaults_keep_old_results():
    """새 값을 하나도 안 쓰면 예전 규칙과 같다(비상금 0, 월급 상승 0, sweep 없음)."""
    r = _r(_req({"type": "debt_free", "label": "d"}, PAY, loans=[MORT]))
    b, m = 24000.0, 0
    while b > 0.005:
        m += 1
        i = b * 4.2 / 1200
        pr = min(118 - i, b)
        b -= pr
    assert r["debt_free_month"] == m == 357
