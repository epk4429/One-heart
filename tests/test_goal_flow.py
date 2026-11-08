"""2026-11-04 공동 목표 설정 개편: 목표 카테고리·필수값(llm/goals.py), 공개/비공개, 쟁점 카드 형식(역할 3),
제안 핑퐁(역할 4a·4c·4d), 확정 목표와 계산 가능 검사."""

import copy
import json
from pathlib import Path

import pytest

from llm import evidence as E
from llm import family as F
from llm import goals as G
from llm import pipeline as P
from llm.eval import load_family
from llm.plan import PlanError, normalize_goal
from llm.providers import get_provider
from llm.roles import ROLES
from server.app import dispatch

# 환경 격리(체험 코드·호출 제한)는 tests/conftest.py가 모든 테스트에 건다.

ROOT = Path(__file__).resolve().parents[1]
MIDS = {"m0", "m1"}
PROV = get_provider("replay")
SUMS = {"m0": {"keep": "우리 집에서 아이랑 사는 것", "flexible": "투자 비중", "worry": "집값"},
        "m1": {"keep": "마음 편한 육아휴직", "flexible": "집 마련 시기", "worry": "휴직 중 생활비"}}
SU = {"family_stage": "x", "living": "x", "shared_goal": "x", "differences": ["x"]}


def call(path, body):
    st, out = dispatch("POST", path, json.dumps(body).encode(), {}, "t")
    return st, out


# ---------- 목표 카테고리와 필수 입력값 ----------
def test_every_category_needs_its_fields():
    for cat, spec in G.CATEGORIES.items():
        if cat == "other":
            continue
        with pytest.raises(G.GoalInputError):
            G.validate_input({"category": cat, "fields": {}}, MIDS)
        assert spec["fields"], cat


def test_home_example_and_derived_goal():
    gi = G.validate_input({"category": "home", "fields": {"target_amount": 30000, "within_years": 5, "living": "전세"}}, MIDS)
    goal = G.derive_goal(gi, [{"member_id": "m0", "name": "민준"}])
    assert goal["type"] == "reach_target" and goal["target_amount"] == 30000 and goal["within_months"] == 60
    assert any("집 마련에 필요한 돈" in x for x in G.details_text(gi, [{"member_id": "m0", "name": "민준"}]))


@pytest.mark.parametrize("raw, msg", [
    ({"category": "nope", "fields": {}}, "목표 카테고리"),
    ({"category": "home", "fields": {"target_amount": 30000, "within_years": 5}}, "지금 사는 곳"),
    ({"category": "home", "fields": {"target_amount": "많이", "within_years": 5, "living": "전세"}}, "숫자"),
    ({"category": "home", "fields": {"target_amount": 30000, "within_years": 99, "living": "전세"}}, "사이"),
    ({"category": "home", "fields": {"target_amount": 30000, "within_years": 5, "living": "우주선"}}, "하나를 골라"),
    ({"category": "retire", "fields": {"base_member_id": "zz", "retire_age": 60, "monthly_need": 300}}, "가족을 골라"),
])
def test_bad_goal_inputs_are_rejected(raw, msg):
    with pytest.raises(G.GoalInputError) as e:
        G.validate_input(raw, MIDS)
    assert msg in str(e.value)


def test_other_category_asks_for_more_depending_on_the_calculation():
    base = {"purpose_text": "가족 여행", "engine_kind": "목표 금액 모으기"}
    gi = G.validate_input({"category": "other", "fields": base}, MIDS)  # 금액·기한은 비워 두면 2단계에서 정한다
    assert G.missing(gi) == ["target_amount", "within_years"]
    gi =G.validate_input({"category": "other", "fields": {**base, "target_amount": 500, "within_years": 2}}, MIDS)
    assert G.derive_goal(gi, [])["label"] == "가족 여행" and G.derive_goal(gi, [])["within_months"] == 24
    gi = G.validate_input({"category": "other", "fields": {"purpose_text": "예금 버티기", "engine_kind": "예금이 얼마나 버티는지", "base_member_id": "m1"}}, MIDS)
    assert G.derive_goal(gi, [])["type"] == "runway" and G.derive_goal(gi, [])["base_member_id"] == "m1"


def test_family_validate_keeps_goal_input_and_it_is_optional():
    fam = F.validate(F.preset("newly"))
    assert fam["goal_input"]["category"] == "home"
    raw = copy.deepcopy(F.preset("newly"))
    raw.pop("goal_input")
    assert F.validate(raw)["goal_input"] is None  # 예전 입력(목표 없음)도 받는다
    raw["goal_input"] = {"category": "home", "fields": {}}
    with pytest.raises(F.FamilyError):
        F.validate(raw)


@pytest.mark.parametrize("key", ["newly", "elder", "single_parent", "mortgage_couple", "pre_retire", "grandma_grandchild"])
def test_every_example_family_has_a_calculable_goal(key):
    fam = F.validate(load_family(key))
    goal = normalize_goal(fam, G.derive_goal(fam["goal_input"], fam["members"]))
    assert goal["type"] in ("reach_target", "runway", "debt_free")


def test_disclosure_is_share_or_hide_only():
    raw = copy.deepcopy(F.preset("newly"))
    item = raw["finance"][0]["item_id"]
    raw["disclosure"] = {item: "summary_only"}  # 예전 값은 비공개로 읽는다
    assert F.validate(raw)["disclosure"] == {item: "hide"}
    assert F.DISCLOSURE == ("share", "hide")
    fin = F.shared_finance(F.validate(raw))
    assert item not in [x["item_id"] for x in fin] and not any(x["item_id"] is None for x in fin)


# ---------- 생각이 갈리는 부분(역할 3) ----------
def _issue(**kw):
    base = {"title": "집을 먼저 살까, 아이를 먼저 가질까", "kind": "order",
            "stances": {"m0": "집부터 사고 싶어요", "m1": "아이부터 갖고 싶어요"}, "shared": "우리 집에서 아이와 함께 사는 것"}
    return {**base, **kw}


def _check3(issues):
    return ROLES["3"].check({"headline": "h", "agreed_points": ["a"], "issues": issues},
                            {"members": [{"member_id": m} for m in MIDS]})


def test_issue_cards_have_no_positions_and_need_everyone():
    assert _check3([_issue()]) == []
    assert any("stances" in e for e in _check3([_issue(stances={"m0": "집부터"})]))
    assert any("kind" in e for e in _check3([_issue(kind="left")]))
    assert any("shared" in e for e in _check3([_issue(shared="")]))
    assert any("60자" in e for e in _check3([_issue(stances={"m0": "가" * 70, "m1": "나"})]))


def test_goal_analyze_gives_cards_covers_and_reasons():
    fam = F.validate(F.preset("newly"))
    out = P.goal_analyze(fam, SUMS, SU, PROV)
    r = out["result"]
    assert not out["proposal_run"]["errors"]
    for it in r["issues"]:
        assert set(it["stances"]) == MIDS and it["kind"] in ("order", "method", "amount", "value") and "positions" not in it
    p = r["proposal"]
    assert p["text"].endswith("어떨까요?") and 1 <= len(p["reasons"]) <= 3 and set(p["covers"]) == MIDS and p["to"]


# ---------- 제안 핑퐁 ----------
def _round(prop, replies):
    return {"proposal": prop["text"], "reasons": prop["reasons"], "replies": replies}


def _first():
    fam = F.validate(F.preset("newly"))
    a = P.goal_analyze(fam, SUMS, SU, PROV)["result"]
    return fam, a, a["proposal"]


def test_revise_collects_opinions_into_a_new_proposal():
    fam, a, p = _first()
    rounds = [_round(p, {"m0": {"v": "good", "text": ""}, "m1": {"v": "cond", "text": "괜찮아요, 단 휴직 중 생활비는 따로 지켜 주세요"}})]
    out = P.goal_revise(fam, SUMS, a, rounds, PROV)
    p2 = out["result"]["proposal"]
    assert not out["proposal_run"]["errors"] and set(p2["covers"]) == MIDS
    assert set(p2["heard"]) == {"m1"} and p2["changed"] and "휴직 중 생활비" in p2["heard"]["m1"]


@pytest.mark.parametrize("replies, msg", [
    ({"m0": {"v": "good", "text": ""}, "m1": {"v": "good", "text": ""}}, "수정 제안이 필요 없어요"),
    ({"m0": {"v": "good", "text": ""}, "m1": {"v": "cond", "text": ""}}, "내용을 적어"),
])
def test_revise_refuses_when_not_needed_or_without_text(replies, msg):
    fam, a, p = _first()
    with pytest.raises(ValueError) as e:
        P.goal_revise(fam, SUMS, a, [_round(p, replies)], PROV)
    assert msg in str(e.value)


def test_role4c_requires_a_heard_line_for_each_objector():
    fam, a, p = _first()
    inp = {"members": [{"member_id": m} for m in MIDS], "tips": [], "facts": [],
           "rounds": [{"replies": {"m0": {"v": "good", "text": ""}, "m1": {"v": "other", "text": "다른 생각이에요"}}}]}
    ok = {"reasons": [E.strip(r) for r in p["reasons"]], "covers": p["covers"], "to": p["to"], "proposal": p["text"], "changed": "조건을 더했어요 정말로",
          "heard": {"m1": "다른 생각을 이번 제안에 담았어요"}}
    assert ROLES["4c"].check(ok, inp) == []
    assert any("heard" in e for e in ROLES["4c"].check({**ok, "heard": {}}, inp))


def test_stuck_guidance_lists_what_to_talk_about_without_deciding():
    fam, a, p = _first()
    rounds = [_round(p, {"m0": {"v": "other", "text": "집이 먼저예요"}, "m1": {"v": "cond", "text": "괜찮아요, 단 휴직이 먼저예요"}})]
    out = P.goal_stuck(fam, SUMS, rounds, PROV)["result"]
    assert "이야기" in out["message"] and out["topics"] and set(out["topics"][0]["stances"]) == MIDS


def test_discussion_note_reaches_the_revise_role(monkeypatch):
    fam, a, p = _first()
    seen = {}
    real = P.run_role
    monkeypatch.setattr(P, "run_role", lambda key, inp, *x, **k: (seen.setdefault(key, inp), real(key, inp, *x, **k))[1])
    rounds = [_round(p, {"m0": {"v": "other", "text": "집이 먼저예요"}, "m1": {"v": "good", "text": ""}})]
    P.goal_revise(fam, SUMS, a, rounds, PROV, None, "집은 지키되 휴직 중 생활비는 따로 두기로 했어요")
    assert "휴직 중 생활비" in seen["4c"]["discussion"] and seen["4c"]["rounds"][0]["replies"]["m0"]["v"] == "other"


# ---------- 합의안 작성(역할 7): 분담 금액의 합 검사가 값(value)이 없어도 멈추지 않는다 ----------
def test_role7_split_contribution_sum_is_checked_without_crashing():
    i = {"members": [{"member_id": "m0"}], "facts": [], "contribution_values": {"agree.monthly_saving": 300.0},
         "contribution_facts": [{"fact_id": "agree.monthly_saving", "display": "월 300만원"}]}  # AI에 주는 모양: value 없음

    def errs(parts):
        o = {"goal": "g", "target_amount_label": "t", "timing": "x", "review": {}, "change_conditions": [], "commitments": [], "report": {},
             "contribution": [{"label": l, "part_of": "agree.monthly_saving", "amount": a} for l, a in parts]}
        return [e for e in ROLES["7"].check(o, i) if "나눈 금액" in e]

    assert errs([("a", 100), ("b", 200)]) == []
    assert errs([("a", 100), ("b", 150)])  # 합이 달라서 다시 쓰게 한다


# ---------- 2단계: 확정된 목표 ----------
def test_criterion_uses_the_goal_the_family_entered_and_checks_it_is_calculable():
    fam, a, p = _first()
    body = {"family": F.preset("newly"), "proposal": p["text"], "reasons": p["reasons"], "summaries": SUMS, "story_understanding": SU,
            "replies": {"m0": {"v": "good", "text": ""}, "m1": {"v": "good", "text": ""}}}
    st, out = call("/api/goal/criterion", body)
    assert st == 200 and out["result"]["goal"]["target_amount"] == 30000 and out["result"]["goal"]["within_months"] == 60
    assert out["goal_check"]["ok"] and out["goal_check"]["goal"]["start_pool"] == 14000
    bad = copy.deepcopy(body)
    bad["family"]["goal_input"]["fields"]["target_amount"] = 5000  # 이미 모은 돈(1억 4,000만원)보다 작다
    st, out = call("/api/goal/criterion", bad)
    assert st == 200 and not out["goal_check"]["ok"] and "커야" in out["goal_check"]["message"]


# ---------- 2단계: 목표 숫자를 함께 정하기(2026-11-08) ----------
def _blank_newly():
    raw = copy.deepcopy(F.preset("newly"))
    raw["goal_input"]["fields"].pop("target_amount")
    raw["goal_input"]["fields"].pop("within_years")
    return raw


def test_numbers_can_be_left_for_step_two():
    fam = F.validate(_blank_newly())  # 숫자를 비워도 '우리 가족 이야기'를 통과한다
    assert G.missing(fam["goal_input"]) == ["target_amount", "within_years"]
    assert any("아직 정하지 않았어요" in x for x in G.details_text(fam["goal_input"], fam["members"]))


def test_size_gives_family_anchors_and_goal_only_when_complete():
    body = {"family": _blank_newly()}
    st, out = call("/api/goal/size", body)
    labels = [l["label"] for l in out["anchors"]["lines"]]
    assert st == 200 and out["goal"] is None and out["missing"] == ["target_amount", "within_years"]
    assert "지금 한 달에 모이는 돈" in labels and "지금처럼 모으면 5년 뒤" in labels
    assert "facts" not in out["anchors"] and "예금·적금" in out["anchors"]["note"]
    st, out = call("/api/goal/size", {**body, "values": {"target_amount": 30000, "within_years": 3}})
    assert st == 200 and out["goal"]["target_amount"] == 30000 and out["goal"]["within_months"] == 36
    need = next(l for l in out["anchors"]["lines"] if l["label"].startswith("3년 안에"))
    assert "더" in need["display"]  # 지금 속도로는 3년 안에 못 모아서 한 달에 더 필요한 돈을 보여 준다
    st, out = call("/api/goal/size", {**body, "values": {"target_amount": "많이"}})
    assert st == 400


def test_step_two_needs_more_with_shorter_deadline():
    from llm import goal_size as GS
    fam = F.validate(_blank_newly())
    from llm.plan import normalize_goal as ng
    g = ng(fam, {"type": "reach_target", "target_amount": 40000})
    assert GS._need_monthly(fam, g, 36) > GS._need_monthly(fam, g, 60) >= 0


def test_criterion_with_blank_numbers_leaves_numbers_to_the_family():
    fam, a, p = _first()
    body = {"family": _blank_newly(), "proposal": p["text"], "reasons": p["reasons"], "summaries": SUMS, "story_understanding": SU,
            "replies": {"m0": {"v": "good", "text": ""}, "m1": {"v": "good", "text": ""}}}
    st, out = call("/api/goal/criterion", body)
    assert st == 200 and not out["goal_check"]["ok"] and out["size"]["missing"]
    assert "{{" not in out["result"]["size_note"] and "만원" in out["result"]["size_note"]  # 엔진 숫자가 들어간 생각해 볼 점
    # 기준 문장·생각해 볼 점에 목표 숫자(fact:goal.*)를 쓰면 다시 쓰게 한다
    inp = {"fixed_goal": {"type": "reach_target"}, "facts": [{"fact_id": "size.after_5y"}], "members": []}
    assert any("goal 숫자" in e for e in ROLES["4b"].check({"criterion": "목표 {{fact:goal.target_amount}}을 모아요", "size_note": ""}, inp))


def test_revise_after_coming_back_from_agreement():
    """모두 '좋아요'였어도 합의안 단계에서 이유를 적고 돌아오면 다시 제안한다(2026-11-08)."""
    fam, a, p = _first()
    rounds = [_round(p, {"m0": {"v": "good", "text": ""}, "m1": {"v": "good", "text": ""}})]
    body = {"family": F.preset("newly"), "summaries": SUMS, "analysis": a, "rounds": rounds}
    st, _ = call("/api/goal/revise", body)
    assert st == 400  # 이유 없이 돌아오면 안 된다
    st, out = call("/api/goal/revise", {**body, "discussion": "서연님이 합의안 단계에서 돌아왔어요: 기한을 다시 정하고 싶어요"})
    assert st == 200 and out["result"]["proposal"]["text"]


def test_api_revise_stuck_and_config():
    fam, a, p = _first()
    rounds = [_round(p, {"m0": {"v": "good", "text": ""}, "m1": {"v": "cond", "text": "괜찮아요, 단 휴직이 먼저예요"}})]
    st, out = call("/api/goal/revise", {"family": F.preset("newly"), "summaries": SUMS, "analysis": a, "rounds": rounds})
    assert st == 200 and out["result"]["proposal"]["heard"]
    st, _ = call("/api/goal/revise", {"family": F.preset("newly"), "summaries": SUMS, "analysis": a,
                                       "rounds": [_round(p, {"m0": {"v": "good", "text": ""}, "m1": {"v": "good", "text": ""}})]})
    assert st == 400
    st, out = call("/api/goal/stuck", {"family": F.preset("newly"), "summaries": SUMS, "rounds": rounds})
    assert st == 200 and out["result"]["topics"]
    st, cfg = call("/api/config", {})
    assert st == 200 and set(cfg["goal_input"]["categories"]) == set(G.CATEGORIES)


# ---------- G12: 수정 제안(4c)·이야기 필요 안내(4d)에도 금융회사·상품 이름 검사 ----------
def test_revise_and_stuck_roles_reject_company_and_product_names(monkeypatch):
    from ontology.products import product_brand_names
    from tests.test_api import _inject
    fam, a, p = _first()
    seen = {}
    real = P.run_role
    monkeypatch.setattr(P, "run_role", lambda key, inp, *x, **k: (lambda r: (seen.setdefault(key, (inp, r.output)), r)[1])(real(key, inp, *x, **k)))
    rounds = [_round(p, {"m0": {"v": "other", "text": "집이 먼저예요"}, "m1": {"v": "cond", "text": "괜찮아요, 단 휴직이 먼저예요"}})]
    P.goal_revise(fam, SUMS, a, rounds, PROV)
    P.goal_stuck(fam, SUMS, rounds, PROV)
    product = sorted(n for n in product_brand_names() if n.startswith("KB"))[0]
    for key in ("4c", "4d"):
        inp, out = seen[key]
        assert not [e for e in ROLES[key].check(out, inp) if "상품 이름" in e], key
        for word in ("우리은행", product):
            assert any(word in e for e in ROLES[key].check(_inject(out, word), inp)), (key, word)
