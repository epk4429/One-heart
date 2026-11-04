"""AI의 근거(llm/evidence.py, 금융꿀팁 RAG 조각): 가족별 조각 묶음, 근거 표시 검사(조각 ID·원문 인용·숫자·금융회사 이름), 역할 4a·5 연결."""

import json
import re
from pathlib import Path

import pytest

from llm import evidence as E
from llm import family as F
from llm import pipeline as P
from llm.providers import get_provider
from llm.roles import ROLES, design_note_errors
from rag import index as R

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not R.available(), reason="원문 저장소·RAG 색인이 없는 환경")


def _tags(fam, n=2):
    """그 가족에게 준 꿀팁 조각에서 (tip_id, 글에 그대로 있는 숫자 없는 한 줄)을 n개."""
    out = []
    for c in E.for_family(fam):
        q = next((l.strip(" □◦◈☞-*·") for l in c["text"].split("\n")
                  if 15 <= len(l.strip(" □◦◈☞-*·")) <= 80 and not re.search(r"[\d|\[\]]", l)), None)
        if q:
            out.append((c["chunk_id"], q))
        if len(out) == n:
            break
    assert len(out) == n
    return out


def _tag(tid, phrase, quote):
    return f"[[tip:{tid}|{phrase}|{quote}]]"


def test_family_topics_follow_facts():
    newly, elder = F.preset("newly"), F.preset("elder")
    assert {"debt", "rent", "invest", "couple"} <= set(E.topics_for(newly))  # 전세대출·주식이 있는 부부
    assert "retirement" not in E.topics_for(newly)
    assert {"retirement", "senior", "insurance"} <= set(E.topics_for(elder))
    assert "debt" not in E.topics_for(elder)  # 대출이 없다


def test_for_family_gives_only_tips_within_cap():
    for fam in (F.preset("newly"), F.preset("elder")):
        cs = E.for_family(fam)
        assert 1 <= len(cs) <= E.CAP and len({c["chunk_id"] for c in cs}) == len(cs)
        assert all(c["kind"] == "꿀팁" and c["doc_key"].startswith("fss_tip_") for c in cs)
        assert [b["tip_id"] for b in E.brief(cs)] == [c["chunk_id"] for c in cs]


def test_context_and_goal_type_change_the_tips():
    """가족이 확인한 말·목표 종류로 찾은 조각이 앞에 오고, 모든 가족에게 가던 고정 조각은 맨 뒤에 1~2개만 남는다."""
    fam = F.validate(F.preset("elder"))
    plain = [c["chunk_id"] for c in E.for_family(fam)]
    ctx = E.context_texts({"m0": {"keep": "이 집에서 계속 살기", "flexible": "여행", "worry": "병원비 연금 생활비"}})
    withctx = [c["chunk_id"] for c in E.for_family(fam, ctx)]
    withgoal = [c["chunk_id"] for c in E.for_family(fam, ctx, "debt_free")]
    assert withctx != plain and withgoal != withctx and len(withgoal) <= E.CAP
    base = {c["chunk_id"] for t in E.BASE_TOPICS for c in R.search(E.TOPIC_QUERY[t], kind="꿀팁", k=E.BASE_PER_TOPIC, topic=True)}
    assert len(base) <= len(E.BASE_TOPICS) * E.BASE_PER_TOPIC
    assert [c for c in withgoal if c in base] == withgoal[len(withgoal) - len([c for c in withgoal if c in base]):]  # 기본 조각은 맨 뒤


def test_families_do_not_all_share_the_same_tips():
    """가족이 달라지면 받는 조각이 달라진다(예전에는 4개가 모든 가족에게 똑같이 갔다)."""
    fams = [F.validate(f) for f in (F.preset("newly"), F.preset("elder"))]
    a, b = ({c["chunk_id"] for c in E.for_family(f)} for f in fams)
    assert len(a & b) < 4


def test_context_texts_uses_only_confirmed_summary_fields():
    out = E.context_texts({"m0": {"keep": "집", "flexible": "", "worry": "병원비", "raw_chat": "원문 대화"}, "m1": "x"}, ["기준 문장"])
    assert out == ["집", "병원비", "기준 문장"]


def test_brief_names_the_source_document():
    b = E.brief(E.for_family(F.preset("newly")))
    assert all(set(x) == {"tip_id", "from", "text"} and not x["from"].startswith("금융꿀팁 200선") for x in b)


def test_eval_families_all_get_tips():
    fams = json.loads((ROOT / "data/eval/kb_families.json").read_text(encoding="utf-8"))["families"]
    for f in fams:
        fam = F.validate(f["family"]) if "family" in f else F.validate(f)
        assert E.for_family(fam), f.get("id")
        has_loan = any(i["kind"] == "loan" for i in fam["finance"])
        assert has_loan == ("debt" in E.topics_for(fam)), f.get("id")  # 대출이 있을 때만 빚 주제
        has_senior = any(m["age"] >= E.SENIOR for m in fam["members"])
        assert has_senior == ("senior" in E.topics_for(fam)), f.get("id")


def test_view_gives_original_and_source():
    tid, q = _tags(F.preset("newly"), 1)[0]
    v = E.view(tid, q)
    assert v["publisher"] == "금융감독원" and v["url"].startswith("https://www.fss.or.kr/") and q in v["text"] and v["quote"] == q
    assert E.view("C_none_000", "x") is None


def test_tags_parse_strip_and_ids():
    (t1, q1), (t2, q2) = _tags(F.preset("newly"), 2)
    text = f"{_tag(t1, '첫째 이유라서', q1)} 그리고 {_tag(t2, '둘째 이유라서', q2)} 해요. {_tag(t1, '첫째 이유라서', q1)}"
    assert E.used(text) == [(t1, q1), (t2, q2)] and E.used_ids(text) == [t1, t2]
    assert E.strip(text) == "첫째 이유라서 그리고 둘째 이유라서 해요. 첫째 이유라서" and "[[" not in E.strip(text)


# ---------- 공동 목표 제안(역할 4a)의 꿀팁 근거: 제안 → 이유(근거 표시는 이유에만) → 모두를 챙겼는지 ----------
def _role4a_input(fam):
    return {"members": [{"member_id": m["member_id"], "name": m["name"]} for m in fam["members"]],
            "tips": E.brief(E.for_family(fam)), "facts": []}


def _out4a(fam, proposal="조건을 먼저 정하면 어떨까요? 모두의 마음을 담아요.", reasons=None, covers=None):
    mids = [m["member_id"] for m in fam["members"]]
    return {"proposal": proposal, "reasons": reasons if reasons is not None else ["서로 지키고 싶은 것이 달라서 조건으로 정해요"],
            "covers": covers if covers is not None else {m: "이 제안에서 지켜져요" for m in mids}, "to": mids}


def _check4a(fam, **kw):
    return ROLES["4a"].check(_out4a(fam, **kw), _role4a_input(fam))


def test_role4a_accepts_a_real_quote_in_a_reason():
    fam = F.preset("newly")
    tid, q = _tags(fam, 1)[0]
    assert _check4a(fam, reasons=[_tag(tid, "여유가 있을 때 하는 게 기본이라서", q) + " 조건으로 정해요"]) == []


def test_role4a_does_not_force_a_tip():
    """맞는 조각이 없으면 근거 없이 써도 된다(억지 인용을 시키지 않는다, 2026-11-04)."""
    assert _check4a(F.preset("newly")) == []


@pytest.mark.parametrize("make, expect", [
    (lambda tid, q, other: dict(reasons=[_tag("C_fss_tip_999_000", "지어낸 원리라서", q) + " 정해요"]), "주지 않은 조각"),
    (lambda tid, q, other: dict(reasons=[_tag(tid, "원리라서", "원문에 없는 문장을 그럴듯하게 지어낸 것입니다 정말로") + " 정해요"]), "원문 인용"),
    (lambda tid, q, other: dict(reasons=[_tag(tid, "원리라서", other) + " 정해요"]), "원문 인용"),  # 다른 조각의 글을 인용
    (lambda tid, q, other: dict(reasons=[_tag(tid, "5천만원까지 보호되는 원리라서", q) + " 정해요"]), "숫자"),
    (lambda tid, q, other: dict(proposal="우리은행 적금으로 모으면 어떨까요? 같이 정해요."), "금융회사 이름"),
    (lambda tid, q, other: dict(reasons=[f"[[tip:{tid} 원리라서]] 조건으로 정해요 정말"]), "모양"),
    (lambda tid, q, other: dict(proposal=_tag(tid, "원리라서", q) + " 조건을 정하면 어떨까요?"), "reasons에만"),  # 근거 표시는 이유에만
])
def test_role4a_checks_tip_reasons(make, expect):
    fam = F.preset("newly")
    (tid, q), (_, other) = _tags(fam, 2)
    errs = _check4a(fam, **make(tid, q, other))
    assert any(expect in e for e in errs), errs


def test_role4a_requires_everyones_keep_to_be_covered():
    """공평성: 구성원 한 사람이라도 '지키고 싶은 것이 어떻게 지켜지는지'가 빠지면 다시 쓰게 한다."""
    fam = F.preset("newly")
    assert any("빠뜨리면" in e for e in _check4a(fam, covers={"m0": "이 제안에서 지켜져요"}))
    assert any("covers.m1" in e for e in _check4a(fam, covers={"m0": "이 제안에서 지켜져요", "m1": ""}))
    assert any("reasons" in e for e in _check4a(fam, reasons=[]))


def test_goal_analyze_puts_tip_view_and_criterion_strips_it(monkeypatch):
    prov = get_provider("replay")
    fam = F.validate(F.preset("elder"))
    sums = {m["member_id"]: {"keep": "이 집에서 살기", "worry": "생활비", "flexible": "시기", "confirmed": True} for m in fam["members"]}
    su = {"family_stage": "x", "living": "x", "shared_goal": "x", "differences": ["x"]}
    out = P.goal_analyze(fam, sums, su, prov)
    p = out["result"]["proposal"]
    assert p["tips"] and E.used_ids(" ".join(p["reasons"])) == [t["tip_id"] for t in p["tips"]] and "[[" not in p["text"]
    assert p["tips"][0]["publisher"] == "금융감독원" and p["tips"][0]["quote"] in p["tips"][0]["text"]
    assert set(p["covers"]) == {m["member_id"] for m in fam["members"]}  # 모두를 챙겼는지
    assert not [v for v in out["verification"]["violations"] if v.get("severity") == "error"]
    assert "[[" not in E.strip(" ".join(p["reasons"]))
    seen = {}
    real = P.run_role
    monkeypatch.setattr(P, "run_role", lambda key, inp, *a, **k: (seen.setdefault(key, inp), real(key, inp, *a, **k))[1])
    P.goal_criterion(fam, p["text"], {m["member_id"]: "좋아요" for m in fam["members"]}, sums, prov, su, p["reasons"])
    assert seen["4b"]["proposal"] == E.strip(p["text"])  # 다음 역할에는 표시를 뗀 문장만
    assert all("[[" not in r for r in seen["4b"]["reasons"])


# ---------- 방법 설계(역할 5)의 근거 ----------
def _notes(fam, **why):
    (t1, q1), (t2, q2) = _tags(fam, 2)
    base = {"A": _tag(t1, "지출을 먼저 챙기는 게 기본이라서", q1) + " 여유 지출을 줄여요.",
            "B": _tag(t2, "안전하게 두는 게 원칙이라서", q2) + " 예금 위주로 모아요.",
            "C": "지금 생활의 여유를 먼저 지켜요."} | why
    return {"options": [{"option_id": o, "label": o, "description": ""} for o in "ABC"],
            "design_notes": [{"option_id": o, "intent": "x", "why": w} for o, w in base.items()]}


@pytest.mark.parametrize("why, expect", [
    ({}, None),
    ({"C": ""}, "근거(why)가 없어요"),
    ({"B": _tag("C_fss_tip_999_000", "원리라서", "어디에도 없는 조각이에요 그냥 그렇습니다") + " 예금 위주로 모아요."}, "주지 않은 조각"),
    ({"B": "예금 위주로 모아요."}, None),  # 근거를 꼭 달지 않아도 된다
    ({"A": "우리은행에 모아요."}, "금융회사 이름"),
])
def test_role5_reason_checks(why, expect):
    fam = F.preset("newly")
    if expect == "금융회사 이름":  # 근거 표시가 둘 이상 남도록 C에 하나 더
        why = why | {"A": _notes(fam)["design_notes"][0]["why"] + " 우리은행에 모아요."}
    errs = design_note_errors(_notes(fam, **why), {"tips": E.brief(E.for_family(fam))})
    assert errs == [] if expect is None else any(expect in e for e in errs), errs


def test_role5_label_company_name_and_flow_with_mock():
    fam = F.validate(F.preset("newly"))
    o = _notes(fam)
    o["options"][0]["label"] = "우리은행 적금으로"
    assert any("이름·설명" in e for e in design_note_errors(o, {"tips": E.brief(E.for_family(fam))}))
    out = P.options_design(fam, {"type": "reach_target", "target_amount": 30000, "within_months": 60}, "기준",
                           {m["member_id"]: {"keep": "a", "flexible": "b", "worry": "c"} for m in fam["members"]},
                           get_provider("replay"), use_tools=False)
    notes = {n["option_id"]: n for n in out["design_notes"]}
    assert notes["A"]["tips"] and notes["B"]["tips"] and not notes["C"]["tips"]
    assert notes["A"]["tips"][0]["publisher"] == "금융감독원"
    assert not [v for v in out["verification"]["violations"] if v.get("severity") == "error"]
