"""계산은 계산엔진만(CLAUDE.md 5절, 2026-11-10~11): 온톨로지·AI 쪽에서 옮겨 온 계산 규칙의 테스트.
- 우대금리 합산(engine/rates.py), 주택연금·집 팔기·통계 기준(engine/policies.py)
- 온톨로지·통계 기준 코드에는 계산 규칙이 남아 있지 않다."""

import inspect

from engine import policies as EP
from engine import rates as R
from llm import world_size as W
from ontology import conditions as C
from ontology import fit


def _it(pp, **kw):
    return {"add_pp": pp, "tag": kw.pop("tag", "salary"), **kw}


def test_rates_group_tier_alt_rules():
    # 묶음(합): 머리 줄 1.0이 아래 0.6+0.6의 상한
    g = [_it(1.0, role="group", group="g1", group_rule="sum"), _it(0.6, group="g1"), _it(0.6, group="g1")]
    assert R.reachable(g) == 1.0
    # 묶음(택일): 아래 중 큰 것
    o = [_it(0.5, role="group", group="g1", group_rule="one_of"), _it(0.3, group="g1"), _it(0.5, group="g1")]
    assert R.reachable(o) == 0.5
    # 단계형: 그중 큰 것
    assert R.reachable([_it(0.2, group="t1"), _it(0.4, group="t1"), _it(0.1)]) == 0.5
    # 고객 구분 택일: 큰 쪽
    assert R.reachable([_it(0.3, alt="신규"), _it(0.5, alt="기존"), _it(0.1)]) == 0.6
    # 고른 종류만
    assert R.applicable([_it(0.3, tag="salary"), _it(0.2, tag="card")], {"card"}) == 0.2


def test_my_rate_caps_by_disclosed_gap_and_text_cap():
    items = [_it(0.8), _it(0.7)]
    r = R.my_rate(3.0, 4.0, items, {"salary"}, None)  # 원하는 1.5, 공시 최고 우대폭 1.0
    assert r == {"rate": 4.0, "bonus": 1.0, "held": 0.5, "want": 1.5}
    assert R.my_rate(3.0, 4.0, items, {"salary"}, 0.6)["rate"] == 3.6  # 원문 상한 0.6
    assert R.my_rate(3.0, None, items, {"salary"}, None)["rate"] == 3.0  # 공시 최고금리 없음 → 우대 0


def test_home_purchase_rules_from_engine_data():
    assert EP.own_money_with_ltv(50000) == 15000  # LTV 70% → 30%
    assert EP.acquisition_tax(50000) == {"amount": 500.0, "rate": 1.0}
    assert EP.acquisition_tax(100000) == {"amount": 3000.0, "rate": 3.0}
    assert EP.acquisition_tax(70000)["amount"] is None  # 6~9억은 법령 계산식을 확보하지 못해 금액을 내지 않음
    assert W.check_quotes() == []  # 엔진 데이터의 인용이 원문에 그대로 있다


def test_sell_home_from_engine_data():
    assert EP.sell_home(50000, 0.6) == {"net": 18000, "new_home": 30000}  # 50000×0.4 − 50000×0.04


def test_no_calculation_rules_left_outside_engine():
    """온톨로지·통계 기준 코드에 계산식이 남아 있지 않다(엔진 함수를 부르기만)."""
    assert C.reachable is R.reachable and C.applicable is R.applicable
    assert "def _sum" not in inspect.getsource(C)
    src = inspect.getsource(fit)
    assert "base_rate\"] + bonus" not in src and "my_rate(" in src
    ws = inspect.getsource(W)
    assert "* (100 - LTV" not in ws and "/ 100)}(집값" not in ws
