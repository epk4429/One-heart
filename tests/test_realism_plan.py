"""가족이 입력한 사실은 AI가 빠뜨려도 코드가 계산에 넣는다(할 일 1-9 B, 2026-11-15).

은퇴 나이·은퇴 후 필요한 돈·연금, 간병비와 시작 시기, 휴직 시기·기간·휴직하는 사람·휴직 중 수입, 월급 상승(일하는 사람만).
방법(spec)에 아무 이벤트가 없어도(= AI가 빠뜨린 경우) 엔진 입력에 들어가는지 본다.
"""

import copy

from engine import simulate
from llm import family as F
from llm.plan import build_request, check_option, life_lines, normalize_goal


def _fam(category, fields, extra_fin=(), members=None):
    raw = {"today": "2026-11", "room": {"name": "t", "reason": "", "host_member_id": "m0"},
           "members": members or [{"member_id": "m0", "name": "지훈", "role": "남편", "age": 35, "work": "working"},
                                  {"member_id": "m1", "name": "하윤", "role": "아내", "age": 33, "work": "working"}],
           "story": {"author_id": "m0", "text": "x"},
           "finance": [{"item_id": "f1", "owner_id": "m0", "kind": "income", "label": "지훈 월급", "amount": 390},
                       {"item_id": "f2", "owner_id": "m1", "kind": "income", "label": "하윤 월급", "amount": 330},
                       {"item_id": "f3", "owner_id": "joint", "kind": "expense", "label": "생활비", "amount": 370},
                       {"item_id": "f4", "owner_id": "joint", "kind": "deposit", "label": "예금", "amount": 5000},
                       *extra_fin],
           "goal_input": {"category": category, "fields": {"emergency_floor": 1000, **fields}}}
    return F.validate(raw)


def _req(fam, raw_goal):
    g = normalize_goal(fam, raw_goal)
    spec = check_option(fam, g, {"option_id": "A", "label": "아무것도 안 넣은 방법", "return_id": "safe"})
    req = build_request(fam, g, [spec])
    req["range"] = {"paths": 0, "seed": 1}
    return g, req, simulate(req, include_monthly=True)["results"][0]["monthly"]


def test_retire_stops_wages_and_uses_need_and_pension():
    fam = _fam("retire", {"base_member_id": "m0", "retire_age": 45, "monthly_need": 300, "pension_monthly": 100})
    g, req, mo = _req(fam, {"type": "runway", "base_member_id": "m0", "floor": 1000})
    rm = (45 - 35) * 12 + 1
    assert g["life"]["month"] == rm and g["horizon_months"] == (100 - 35) * 12  # 100세까지 계산
    assert abs(mo[rm - 2]["inflow"] - 720 * 1.02 ** ((rm - 2) / 12)) < 0.05      # 은퇴 전 달: 월급(2% 상승)
    assert abs(mo[rm - 1]["inflow"] - 100) < 0.01                                 # 은퇴한 달: 연금만
    assert abs(mo[rm - 1]["outflow"] + 300 * 1.02 ** ((rm - 1) / 12)) < 0.05      # 생활비 대신 은퇴 후 생활비(물가 반영)
    assert any("45세에 은퇴" in t for t in life_lines(fam, g)) and any("연금 월 100만원" in t for t in life_lines(fam, g))


def test_retire_without_pension_says_so():
    fam = _fam("retire", {"base_member_id": "m0", "retire_age": 60})
    g = normalize_goal(fam, {"type": "runway", "base_member_id": "m0"})
    assert any("연금 없이" in t for t in life_lines(fam, g))


def test_care_cost_starts_when_family_said():
    fam = _fam("care", {"base_member_id": "m0", "monthly_cost": 80, "start_years": 2})
    g, req, mo = _req(fam, {"type": "runway", "base_member_id": "m0"})
    assert abs(mo[23]["outflow"] + 370 * 1.02 ** (23 / 12)) < 0.05
    assert abs(mo[24]["outflow"] + (370 + 80) * 1.02 ** (24 / 12)) < 0.05   # 25달째(2년 뒤)부터 간병비


def test_baby_leave_replaces_that_members_wage():
    fam = _fam("lump", {"purpose": "출산·육아", "within_years": 1, "leave_months": 6, "leave_member_id": "m1", "leave_income": 150, "target_amount": 3000})
    g, req, mo = _req(fam, {"type": "reach_target", "target_amount": 30000, "floor": 1000})
    w = lambda m: 1.02 ** ((m - 1) / 12)
    assert abs(mo[11]["inflow"] - 720 * w(12)) < 0.05                    # 12달째: 둘 다 월급
    assert abs(mo[12]["inflow"] - (390 * w(13) + 150)) < 0.05             # 13~18달째: 하윤 월급 대신 휴직 중 수입
    assert abs(mo[17]["inflow"] - (390 * w(18) + 150)) < 0.05
    assert abs(mo[18]["inflow"] - 720 * w(19)) < 0.05                    # 19달째부터 다시 월급


def test_wage_growth_only_for_working_members():
    members = [{"member_id": "m0", "name": "아버님", "role": "아버지", "age": 70, "work": "retired"},
               {"member_id": "m1", "name": "딸", "role": "딸", "age": 40, "work": "working"}]
    fam = _fam("care", {"base_member_id": "m0", "monthly_cost": 50, "start_years": 0}, members=members)
    g, req, mo = _req(fam, {"type": "runway", "base_member_id": "m0"})
    cfs = {c["label"]: c for c in req["options"][0]["cashflows"]}
    assert cfs["하윤 월급"]["grows"] and not cfs["지훈 월급"]["grows"]  # m0(은퇴)의 수입은 오르지 않는다


def test_debt_request_turns_on_sweep_and_floor():
    fam = _fam("debt", {"priority": "빨리 끝내기"}, extra_fin=[{"item_id": "f9", "owner_id": "joint", "kind": "loan", "loan_type": "credit",
                                                         "label": "신용대출", "amount": 3000, "rate": 6, "payment": 60},
                                                        {"item_id": "f8", "owner_id": "m0", "kind": "investment", "label": "주식", "amount": 700}])
    g, req, mo = _req(fam, {"type": "debt_free", "floor": 1000})
    assert req["sweep"] and req["start"]["floor"] == 1000 and req["start"]["illiquid"] == 700 and req["income_growth"] == 2.0


def test_old_saved_goal_without_floor_still_works():
    fam = _fam("lump", {"purpose": "차량", "target_amount": 3000, "within_years": 2})
    g = normalize_goal(fam, {"type": "reach_target", "target_amount": 8000})  # 예전에 저장한 목표(floor 없음)
    assert g["floor"] == 0.0


def test_family_below_floor_gets_fill_month_not_breach():
    """처음부터 예금이 비상금보다 적은 가족은 '비상금 아래로 1개월'이 아니라 '비상금을 채우는 때'(2026-11-15)."""
    from llm import pipeline as P
    from tools.realism_check import goal_raw, load
    sc = load("home_child_credit")[0]
    fam = F.validate(sc["family"])
    goal = normalize_goal(fam, goal_raw(fam))
    spec = check_option(fam, goal, {"option_id": "A", "label": "x", "return_id": "safe"})
    r = P.simulate_specs(fam, goal, [spec], include_monthly=False)["results"][0]
    assert r["floor_fill_month"] and r["floor_fill_month"] > 1 and r["floor_breach_month"] is None


def test_label_saying_now_but_changed_is_renamed():
    from llm.plan import mark_baseline
    fam = _fam("lump", {"purpose": "차량", "target_amount": 3000, "within_years": 2})
    g = normalize_goal(fam, {"type": "reach_target", "target_amount": 8000, "floor": 1000})
    c = check_option(fam, g, {"option_id": "C", "label": "지금처럼(비교용)", "return_id": "safe", "floor": 1500})
    b = check_option(fam, g, {"option_id": "B", "label": "지금처럼 쓰고 외식 줄이기", "return_id": "safe",
                              "adjustments": [{"label": "외식", "amount": 20, "reason": "r"}]})
    out = mark_baseline([b, c])
    assert out[1]["label"] == "지금처럼 쓰고 비상금 넉넉히" and "지금처럼" not in out[0]["label"]


def test_tidy_removes_minus_before_shortfall():
    from llm.pipeline import _tidy
    assert _tidy("매달 -30만원씩 모자라서") == "매달 30만원씩 모자라서" and _tidy("연 연 4.2%") == "연 4.2%"


def test_care_years_limits_care_cost_and_is_optional():
    """간병 기간(선택 입력, 2026-11-15 형님 결정): 넣으면 그 기간만, 비우면 100세까지 계속."""
    fam = _fam("care", {"base_member_id": "m0", "monthly_cost": 80, "start_years": 1, "care_years": 3})
    g, req, mo = _req(fam, {"type": "runway", "base_member_id": "m0"})
    infl = lambda m: 1.02 ** ((m - 1) / 12)
    assert abs(mo[12]["outflow"] + (370 + 80) * infl(13)) < 0.05      # 13달째부터 간병비
    assert abs(mo[47]["outflow"] + (370 + 80) * infl(48)) < 0.05      # 48달째(3년째 마지막)까지
    assert abs(mo[48]["outflow"] + 370 * infl(49)) < 0.05             # 49달째부터 간병비 없음
    assert any("3년 동안" in t for t in life_lines(fam, g))
    fam2 = _fam("care", {"base_member_id": "m0", "monthly_cost": 80, "start_years": 1})
    g2 = normalize_goal(fam2, {"type": "runway", "base_member_id": "m0"})
    assert g2["life"]["to"] == 0 and any("100세가 될 때까지" in t for t in life_lines(fam2, g2))


def test_cut_limit_uses_family_words():
    """생활비 줄이기 한도 = max(지금 지출의 20%, 가족이 '이만큼 줄일 수 있다'고 말한 금액), 상환·저축 얘기는 세지 않음(2026-11-15 형님 결정)."""
    from llm.plan import PlanError, cut_limit, stated_cut
    fam = _fam("lump", {"purpose": "차량", "target_amount": 3000, "within_years": 2})  # 지출: 생활비 370
    assert stated_cut({"m0": {"flexible": "외식·여가로 100만원은 줄일 수 있어요"}}) == 100
    assert stated_cut({"m0": {"flexible": "월 상환을 80만원까지 늘릴 수 있음"}}) == 0      # 상환 얘기는 감액이 아님
    assert stated_cut({"m0": {"flexible": "저축을 50만원 더 할 수 있어요"}}) == 0
    assert cut_limit(fam, {}) == 74.0                                                    # 370 × 20%
    assert cut_limit(fam, {"m1": {"flexible": "생활비를 120만원까지 줄일 수 있어요"}}) == 120.0
    assert cut_limit(fam, {"m1": {"flexible": "생활비를 300만원 줄일 수 있어요"}}) == 185.0   # 절반(185)을 넘지는 않음
    g = normalize_goal(fam, {"type": "reach_target", "target_amount": 8000, "floor": 1000})
    spec = {"option_id": "A", "label": "x", "return_id": "safe", "adjustments": [{"label": "외식 줄이기", "amount": 100, "reason": "가족 말"}]}
    try:
        check_option(fam, g, spec, cut_limit=74.0)
        raise AssertionError("20% 한도면 막혀야 해요")
    except PlanError:
        pass
    assert check_option(fam, g, spec, cut_limit=120.0)  # 가족이 120만원이라고 했으면 통과
    assert check_option(fam, g, spec)                   # 방법을 짜는 단계가 아니면(가족 홈 다시 계산 등) 검사하지 않음


def test_selling_home_repays_its_mortgage_first():
    """집 팔기: 판 달에 그 집의 주택담보대출부터 갚고 남는 돈만 예금에(2026-11-15 형님 결정)."""
    from llm import pipeline as P
    fam = _fam("retire", {"base_member_id": "m0", "retire_age": 60, "monthly_need": 300},
               extra_fin=[{"item_id": "f8", "owner_id": "joint", "kind": "home", "label": "집", "amount": 60000},
                          {"item_id": "f9", "owner_id": "joint", "kind": "loan", "loan_type": "mortgage", "label": "주택담보대출",
                           "amount": 10000, "rate": 4.2, "payment": 80}],
               members=[{"member_id": "m0", "name": "지훈", "role": "남편", "age": 58, "work": "working"},
                        {"member_id": "m1", "name": "하윤", "role": "아내", "age": 56, "work": "working"}])
    g = normalize_goal(fam, {"type": "runway", "base_member_id": "m0"})
    s = check_option(fam, g, {"option_id": "A", "label": "x", "return_id": "safe", "policies": [{"policy": "sell_home", "month": 12, "new_home_ratio": 0.6}]})
    req = build_request(fam, g, [s])
    assert req["options"][0]["loan_prepayments"] == [{"loan_id": "f9", "month": 12, "amount": 10000}]
    req["range"] = {"paths": 0, "seed": 1}
    mo = simulate(req, include_monthly=True)["results"][0]["monthly"]
    assert mo[11]["debt"] == 0 and mo[10]["debt"] > 0 and mo[12]["loan_payment"] == 0  # 12달째에 다 갚고 그 뒤 상환 없음


def test_review_return_change_is_carried_into_new_plan():
    """재점검의 수익률 변화(−1%p)는 합의안을 다시 정할 때도 모든 방법에 들어가고, 가정 한 줄에 밝힌다(2026-11-15 형님 결정)."""
    from llm.plan import design_context, engine_option, net_return
    fam = _fam("lump", {"purpose": "차량", "target_amount": 3000, "within_years": 2})
    g0 = normalize_goal(fam, {"type": "reach_target", "target_amount": 8000, "floor": 1000})
    g1 = normalize_goal(fam, {"type": "reach_target", "target_amount": 8000, "floor": 1000, "return_delta": -1})
    spec = check_option(fam, g1, {"option_id": "A", "label": "x", "return_id": "safe"})
    safe = next(r for r in F.assumptions()["returns"] if r["id"] == "safe")
    assert engine_option(fam, g0, spec)["expected_return"] == net_return(safe)
    assert engine_option(fam, g1, spec)["expected_return"] == round(net_return(safe) - 1, 2)
    assert any("1%포인트 낮췄어요" in t for t in life_lines(fam, g1))
    assert next(r for r in design_context(fam, g1)["returns"] if r["id"] == "safe")["used_in_calc"] == round(net_return(safe) - 1, 2)


def test_already_retired_keeps_current_spending():
    """이미 은퇴한 가족은 지금 생활비가 곧 은퇴 후 생활비: 방법의 생활비 줄이기가 반영돼야 한다(2026-11-15 실제 AI에서 발견)."""
    members = [{"member_id": "m0", "name": "상철", "role": "남편", "age": 67, "work": "retired"},
               {"member_id": "m1", "name": "순자", "role": "아내", "age": 64, "work": "retired"}]
    fam = _fam("retire", {"base_member_id": "m0", "retire_age": 65, "monthly_need": 260}, members=members)
    g = normalize_goal(fam, {"type": "runway", "base_member_id": "m0"})
    a = check_option(fam, g, {"option_id": "A", "label": "x", "return_id": "safe", "monthly_changes": [{"item_id": "f3", "amount": 300, "reason": "r"}]})
    b = check_option(fam, g, {"option_id": "B", "label": "y", "return_id": "safe"})
    from llm import pipeline as P
    rs = {r["option_id"]: r for r in P.simulate_specs(fam, g, [a, b], include_monthly=False)["results"]}
    assert rs["A"]["monthly_flow"] == rs["B"]["monthly_flow"] + 70  # 370 → 300 줄인 만큼 그대로
    assert any("이미 은퇴해서 지금 생활비로" in t for t in life_lines(fam, g))
