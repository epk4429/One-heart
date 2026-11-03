"""재무 원리 카드(ontology/cards.py): 원문 인용·숫자·작성일 검사, 검사가 실제로 잡는지(돌연변이), 가족별 묶음."""

import copy
import json
from pathlib import Path

import pytest

from llm import family as F
from ontology import cards as C
from ontology.products import load_products

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = {p["provider"] for cat in ("deposit", "saving", "mortgage", "rent_loan", "credit_loan", "busi_loan") for p in load_products(cat)}


def test_cards_pass_all_checks():
    assert 20 <= len(C.load()) <= 40  # docs/12 6절 규모
    assert C.check(PROVIDERS) == []


@pytest.mark.parametrize("break_it, expect", [
    (lambda c: c["quotes"][0].__setitem__("quote", c["quotes"][0]["quote"] + "지어낸 말"), "인용이 원문에 없음"),
    (lambda c: c.__setitem__("text", c["text"] + " 3개월치면 충분해요."), "숫자 3"),
    (lambda c: c.__setitem__("published", "2020-01-01"), "작성일"),
    (lambda c: c.__setitem__("needs", ["N_없는필요"]), "없는 필요"),
    (lambda c: c.__setitem__("topics", ["lottery"]), "주제"),
    (lambda c: c.__setitem__("text", "하나요. 둘이요. 셋이요. 넷이요."), "4문장"),
    (lambda c: c.__setitem__("text", c["text"] + " 우리은행이 좋아요."), "금융회사 이름"),
])
def test_checker_catches_mutations(monkeypatch, break_it, expect):
    data = copy.deepcopy(C._data())
    break_it(data["cards"][0])
    monkeypatch.setattr(C, "_data", lambda: data)
    problems = C.check({"우리은행"})
    assert any(expect in p for p in problems), problems


def test_family_topics_follow_facts():
    newly, elder = F.preset("newly"), F.preset("elder")
    assert {"debt", "rent", "invest", "couple"} <= set(C.topics_for(newly))  # 전세대출·주식이 있는 부부
    assert "retirement" not in C.topics_for(newly)
    assert {"retirement", "senior", "insurance"} <= set(C.topics_for(elder))
    assert "debt" not in C.topics_for(elder)  # 대출이 없다
    for fam in (newly, elder):
        ids = {c["id"] for c in C.for_family(fam)}
        assert {"C_emergency_fund", "C_split_accounts"} <= ids  # 기본 주제는 누구에게나


def test_eval_families_all_get_cards():
    fams = json.loads((ROOT / "data/eval/kb_families.json").read_text(encoding="utf-8"))["families"]
    for f in fams:
        fam = F.validate(f["family"]) if "family" in f else F.validate(f)
        assert C.for_family(fam), f.get("id")
        has_loan = any(i["kind"] == "loan" for i in fam["finance"])
        assert has_loan == ("debt" in C.topics_for(fam)), f.get("id")  # 대출이 있을 때만 빚 카드
        has_senior = any(m["age"] >= C.SENIOR for m in fam["members"])
        assert has_senior == ("senior" in C.topics_for(fam)), f.get("id")


def test_needs_link_and_view():
    ids = {c["id"] for c in C.for_needs(["N_rent_deposit"])}
    assert {"C_jeonse_ratio", "C_deposit_guarantee"} <= ids
    v = C.view("C_loan_withdrawal")
    assert v["quotes"][0]["publisher"] == "금융감독원" and v["quotes"][0]["url"].startswith("https://www.fss.or.kr/")
    assert [b["card_id"] for b in C.brief(C.for_needs(["N_rent_deposit"]))] == [c["id"] for c in C.for_needs(["N_rent_deposit"])]


# ---------- 공동 목표 제안(역할 4a)의 카드 근거 ----------
from llm import pipeline as P  # noqa: E402
from llm.providers import get_provider  # noqa: E402
from llm.roles import ROLES  # noqa: E402


def _role4a_input(fam):
    return {"members": [{"member_id": m["member_id"], "name": m["name"]} for m in fam["members"]],
            "cards": C.brief(C.for_family(fam)), "facts": []}


@pytest.mark.parametrize("proposal, expect", [
    ("[[card:C_emergency_fund|비상금은 따로 두는 게 기본이라서]] 조건을 먼저 정하면 어떨까요?", None),
    ("[[card:C_pension_early_exit|연금은 깨지 않는 게 좋아서]] 조건을 먼저 정하면 어떨까요?", "주지 않은 카드"),  # 신혼부부에게 안 준 노후 카드
    ("[[card:C_made_up|지어낸 원리라서]] 조건을 먼저 정하면 어떨까요?", "주지 않은 카드"),
    ("[[card:C_emergency_fund|비상금은 따로 두는 게 기본이라서]] 우리은행 적금으로 모으면 어떨까요?", "금융회사 이름"),
    ("조건을 먼저 정하고 함께 계산해 보면 어떨까요?", "근거를"),
    ("[[C_emergency_fund 비상금이라서]] 조건을 먼저 정하면 어떨까요?", "모양"),
])
def test_role4a_checks_card_reasons(proposal, expect):
    fam = F.preset("newly")
    inp = _role4a_input(fam)
    errs = ROLES["4a"].check({"proposal": proposal, "to": ["m0", "m1"], "bridges": []}, inp)
    if expect is None:
        assert errs == []
    else:
        assert any(expect in e for e in errs), errs


def test_goal_analyze_puts_card_view_and_criterion_strips_it(monkeypatch):
    prov = get_provider("replay")
    fam = F.validate(F.preset("elder"))
    sums = {m["member_id"]: {"keep": "이 집에서 살기", "worry": "생활비", "flexible": "시기", "confirmed": True} for m in fam["members"]}
    su = {"family_stage": "x", "living": "x", "shared_goal": "x", "differences": ["x"]}
    out = P.goal_analyze(fam, sums, su, prov)
    p = out["result"]["proposal"]
    assert C.used_ids(p["text"]) == [c["card_id"] for c in p["cards"]] and p["cards"]
    assert p["cards"][0]["quotes"][0]["publisher"] == "금융감독원"
    assert not [v for v in out["verification"]["violations"] if v.get("severity") == "error"]
    assert C.strip(p["text"]).startswith("집이 있으면") and "[[" not in C.strip(p["text"])
    seen = {}
    real = P.run_role
    monkeypatch.setattr(P, "run_role", lambda key, inp, *a, **k: (seen.setdefault(key, inp), real(key, inp, *a, **k))[1])
    P.goal_criterion(fam, p["text"], {m["member_id"]: "좋아요" for m in fam["members"]}, sums, prov, su)
    assert seen["4b"]["proposal"] == C.strip(p["text"])  # 다음 역할에는 표시를 뗀 문장만


# ---------- 방법 설계(역할 5)의 근거 ----------
from llm.roles import design_note_errors  # noqa: E402


def _notes(**why):
    base = {"A": "[[card:C_essentials_first|꼭 써야 하는 지출을 먼저 빼는 게 기본이라서]] 여유 지출을 줄여요.",
            "B": "[[card:C_emergency_fund|비상금은 따로 두는 게 기본이라서]] 예금 위주로 모아요.",
            "C": "지금 생활의 여유를 먼저 지켜요."} | why
    return {"options": [{"option_id": o, "label": o, "description": ""} for o in "ABC"],
            "design_notes": [{"option_id": o, "intent": "x", "why": w} for o, w in base.items()]}


@pytest.mark.parametrize("why, expect", [
    ({}, None),
    ({"C": ""}, "근거(why)가 없어요"),
    ({"B": "[[card:C_pension_early_exit|연금은 깨지 않아서]] 예금 위주로 모아요."}, "주지 않은 카드"),
    ({"B": "예금 위주로 모아요."}, "적어도 둘"),
    ({"A": "[[card:C_essentials_first|지출을 먼저 빼는 게 기본이라서]] 우리은행에 모아요."}, "금융회사 이름"),
])
def test_role5_reason_checks(why, expect):
    inp = {"cards": C.brief(C.for_family(F.preset("newly")))}
    errs = design_note_errors(_notes(**why), inp)
    assert errs == [] if expect is None else any(expect in e for e in errs), errs


def test_role5_label_company_name_and_flow_with_mock():
    o = _notes()
    o["options"][0]["label"] = "우리은행 적금으로"
    assert any("이름·설명" in e for e in design_note_errors(o, {"cards": C.brief(C.for_family(F.preset("newly")))}))
    fam = F.validate(F.preset("newly"))
    out = P.options_design(fam, {"type": "reach_target", "target_amount": 30000, "within_months": 60}, "기준",
                           {m["member_id"]: {"keep": "a", "flexible": "b", "worry": "c"} for m in fam["members"]},
                           get_provider("replay"), use_tools=False)
    notes = {n["option_id"]: n for n in out["design_notes"]}
    assert notes["B"]["cards"][0]["card_id"] == "C_short_money_no_risk" and "1~2년" in notes["B"]["why"]
    assert not [v for v in out["verification"]["violations"] if v.get("severity") == "error"]  # 카드 설명의 숫자는 허용
