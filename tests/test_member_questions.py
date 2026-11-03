"""각자의 생각 맞춤 질문(2026-11-03 형님 결정: 고정 3개 + 가족 이야기를 보고 그 사람에게 맞춘 1~2개)."""

import pytest

from llm import family as F
from llm import pipeline as P
from llm.providers import get_provider
from llm.roles import ROLES, member_question_errors

NEWLY = F.validate(F.preset("newly"))
INP = {"story": NEWLY["story"]["text"], "members": [{"member_id": m["member_id"], "name": m["name"], "role": m["role"], "age": m["age"]}
                                                     for m in NEWLY["members"]]}
OK = {"member_id": "m1", "text": "아이는 언제쯤 갖고 싶으세요?", "easy": "아이는 언제쯤이 좋으세요?", "from": "2년 안에 아이를 갖고 싶어요"}


@pytest.mark.parametrize("change, expect", [
    ({}, None),
    ({"member_id": "m9"}, "member_id"),
    ({"from": "내년에 육아휴직을 해요"}, "글자 그대로"),  # 이야기에 없는 구절
    ({"text": "아이는 언제쯤 갖고 싶으세요."}, "?로 끝남"),
    ({"easy": "아이는 언제쯤 낳고 싶은지 편하게 이야기해 주실 수 있으세요?"}, "1~30자"),
    ({"text": "우리은행 적금으로 아이 자금을 모을까요?"}, "금융회사 이름"),
])
def test_member_question_checks(change, expect):
    errs = member_question_errors([{**OK, **change}], INP)
    assert errs == [] if expect is None else any(expect in e for e in errs), errs


def test_at_most_two_per_member_and_whitespace_tolerant_from():
    three = [OK, {**OK, "from": "전세 만기가 내년 4월이에요"}, {**OK, "from": "5년 안에는"}]
    assert any("2개까지" in e for e in member_question_errors(three, INP))
    assert member_question_errors([{**OK, "from": "2년 안에  아이를 갖고"}], INP) == []  # 띄어쓰기 차이는 봐준다
    assert member_question_errors([], INP) == []  # 필요 없으면 비워도 된다


def test_role1a_checks_questions_and_1b_checks_details():
    base = {"family_stage": "결혼 1년 차", "living": "전세", "shared_goal": "집", "differences": ["순서"]}
    assert ROLES["1a"].check({**base, "member_questions": [OK]}, INP) == []
    assert ROLES["1a"].check({**base, "member_questions": [{**OK, "from": "지어낸 말"}]}, INP)
    s1b = {"keep": "a", "flexible": "b", "worry": "c", "ambiguous": []}
    assert ROLES["1b"].check({**s1b, "details": ["휴직은 1년쯤"]}, {"qa": []}) == []
    assert ROLES["1b"].check({**s1b, "details": ["a", "b", "c"]}, {"qa": []})


def test_flow_with_mock_questions_details_and_sharing():
    prov = get_provider("replay")
    story = P.story_understand(NEWLY, prov)
    qs = story["result"]["member_questions"]
    assert set(qs) == {"m0", "m1"} and all(1 <= len(v) <= 2 for v in qs.values())
    assert all(q["from"] in NEWLY["story"]["text"] for v in qs.values() for q in v)
    fixed = [q["text"] for q in F.QUESTIONS]
    qa = [[t, "답"] for t in fixed] + [[qs["m1"][0]["text"], "내년 봄쯤이요"]]
    rv = P.interview_review(NEWLY, "m1", qa, prov)["result"]
    assert rv["details"] == ["내년 봄쯤이요"]
    shared = P.shared_summaries({"m1": rv, "m0": {"keep": "a", "flexible": "b", "worry": "c"}}, NEWLY)
    assert shared["m1"]["details"] == ["내년 봄쯤이요"] and "details" not in shared["m0"]
    assert set(shared["m1"]) == {"keep", "flexible", "worry", "details"}  # 질문 원문·말뜻 같은 다른 칸은 공유되지 않는다
