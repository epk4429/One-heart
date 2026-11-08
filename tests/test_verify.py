"""검증 구조 테스트(docs/05_AI역할과_검증.md 3.5절)."""

import json
from pathlib import Path

from engine import simulate
from verify import VerificationRecord, check_agreement, scan_numbers, verify_texts
from verify.core import find_numbers

ROOT = Path(__file__).resolve().parents[1]
CASES = {c["case_id"]: c for c in json.loads((ROOT / "data/golden/engine_cases.json").read_text(encoding="utf-8"))["cases"]}


def _facts(case_id):
    out = simulate(CASES[case_id]["request"])
    return out, {f["fact_id"]: f for r in out["results"] for f in r["facts"]}


def test_find_numbers_handles_composite_money():
    hits = find_numbers("지금 1억 4,855만원이고 한 달 235만원, 연 3.8%, 약 4.9년, 87세")
    kinds = [(h.kind, h.value) for h in hits]
    assert ("money", 14855) in kinds
    assert ("money", 235) in kinds
    assert ("pct", 3.8) in kinds
    assert ("year", 4.9) in kinds
    assert ("age", 87) in kinds


def test_placeholders_render_and_pass():
    out, facts = _facts("newly_options")
    texts = {"easy": "B를 고르면 {{fact:B.goal_hit_years}}에 {{fact:goal.target_amount}}이 모여요."}
    rendered, rec = verify_texts(texts, facts, role="6", run_id=out["run_id"])
    assert rendered["easy"] == "B를 고르면 약 4.9년에 3억원이 모여요."
    assert rec.status == "pass"
    assert rec.to_dict()["facts_used"] == ["B.goal_hit_years", "goal.target_amount"]


def test_wrong_raw_number_is_error():
    _, facts = _facts("newly_options")
    rec = VerificationRecord(run_id=None, role="6")
    v = scan_numbers("B를 고르면 약 4.5년 뒤에 모여요", facts, record=rec)
    assert v[0]["type"] == "raw_number_mismatch"
    assert rec.status == "fail"


def test_correct_raw_number_is_warning_with_fact():
    _, facts = _facts("newly_options")
    v = scan_numbers("B를 고르면 약 4.9년 뒤에 모여요", facts)
    assert v[0]["type"] == "raw_number_matching_fact"
    assert v[0]["fact_id"].startswith("B.goal_hit")


def test_unknown_fact_is_error():
    _, facts = _facts("newly_options")
    _, rec = verify_texts({"t": "{{fact:Z.goal_hit_years}}"}, facts, role="6")
    assert rec.violations[0]["type"] == "unknown_fact"
    assert rec.status == "fail"


def test_quotes_and_allowlist():
    _, facts = _facts("newly_options")
    quotes = {"q1": "집은 1~2년 늦어도 돼"}
    v = scan_numbers("서연님은 {{quote:q1}}라고 했고, 5년 뒤 모습을 물었어요", facts, quotes, allow=["5년 뒤"])
    assert v == []


def test_agreement_arithmetic_and_conditions():
    out, _ = _facts("newly_agreed")
    res = out["results"][0]
    goal = out["goal"]
    good = {
        "contribution": [{"label": "함께 모으는 돈", "amount": 175}, {"label": "휴직 준비 적금", "amount": 60}],
        "target_amount": {"value": 30000},
        "commitments": [{"text": "휴직 준비금은 투자하지 않기", "source": {"type": "condition", "member_id": "m1"}},
                        {"text": "6개월 점검 때 시기 다시", "source": {"type": "condition", "member_id": "m0"}}],
    }
    conds = [{"member_id": "m0", "text": "집값이 많이 오르면…"}, {"member_id": "m1", "text": "휴직 준비금…"}]
    rec = VerificationRecord(run_id=out["run_id"], role="7")
    check_agreement(good, res["monthly_flow"], goal, conds, rec)
    assert rec.status == "pass"

    bad = dict(good, contribution=[{"amount": 175, "part_of": "agree.monthly_saving"},
                                   {"amount": 70, "part_of": "agree.monthly_saving"}], commitments=good["commitments"][:1])
    rec2 = VerificationRecord(run_id=out["run_id"], role="7")
    check_agreement(bad, res["monthly_flow"], goal, conds, rec2)
    types = {v["type"] for v in rec2.violations}
    assert types == {"contribution_sum_mismatch", "condition_not_reflected"}


def test_fix_particles_after_rendered_numbers():
    from verify.core import fix_particles as f
    assert f("매달 35만원가 남아요") == "매달 35만원이 남아요"
    assert f("약 17.0년가 걸려요") == "약 17.0년이 걸려요"
    assert f("잔액이 0만원라서") == "잔액이 0만원이라서"
    assert f("월 180만원로 정해요") == "월 180만원으로 정해요"
    assert f("대출 더 갚기를 월 월 210만원으로") == "대출 더 갚기를 월 210만원으로"
    assert f("1,200만원가량") == "1,200만원가량" and f("3월 월요일") == "3월 월요일"
