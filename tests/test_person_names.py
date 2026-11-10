"""사람 이름 대조 검사(1-5, G14, 임의결정 70): AI 글 속 'OO님'은 이 가족 구성원(이름·성 뺀 이름·관계)이거나 가족을 부르는 말이어야 하고,
구성원 id(m0)를 이름 대신 쓰면 안 된다. ① 예문 ② 실제 흐름(예시 가족 두 곳)의 역할 출력에 없는 이름·id를 넣으면 잡는지."""

import pytest

from llm import pipeline as P
from llm.roles import ROLES, person_name_errors
from tests.test_api import _iso  # noqa: F401  환경 격리

ELDER = [{"member_id": "m0", "name": "김영호", "role": "아버지"}, {"member_id": "m1", "name": "박순자", "role": "어머니"},
         {"member_id": "m2", "name": "김태윤", "role": "장남"}, {"member_id": "m3", "name": "김지은", "role": "장녀"}]
I = {"members": ELDER}

PASS = [
    "김영호님은 이 집에서 계속 사시고 싶어 해요.",
    "영호님과 순자님의 생각이 달라요.",  # 성을 뺀 이름
    "지은 님이 부모님을 돌보는 시간을 걱정해요.",  # 띄어 쓴 님, 부모님
    "아버님은 집을, 어머님은 병원비를 걱정하세요.",
    "어머님과 아드님은 활용해도 괜찮다고 보세요.",
    "장남님이 더 보태기로 했어요.",  # 관계
    "양가 부모님께 드리는 용돈은 그대로예요.",
]
CATCH_UNKNOWN = [
    "지훈님은 집을 먼저 사고 싶어 해요.",
    "김민수님이 생활비를 더 내요.",
]
CATCH_ID = [
    "투자 비중을 줄여도 된다고 하신 m0님 말씀을 살렸어요.",  # 실제 Claude 출력(2026-11-08 신혼부부 돌아오기)
    "m2가 매달 보태는 돈은 그대로예요.",
]


@pytest.mark.parametrize("text", PASS)
def test_real_names_and_family_words_pass(text):
    assert not person_name_errors({"t": text}, I), text


@pytest.mark.parametrize("text", CATCH_UNKNOWN)
def test_unknown_name_is_caught(text):
    errs = person_name_errors({"t": text}, I)
    assert errs and "없는 사람 이름" in errs[0], text


@pytest.mark.parametrize("text", CATCH_ID)
def test_member_id_in_sentence_is_caught(text):
    assert any("구성원 id" in e for e in person_name_errors({"t": text}, I)), text


def test_structured_ids_are_fine():
    """to·member_id 같은 구조 값의 id, 숫자 자리표시({{fact:…}}), 꿀팁 인용은 문제가 아니다."""
    o = {"to": ["m0", "m1"], "covers": {"m0": "영호님의 집"}, "text": "남는 돈은 {{fact:m0.income}}이에요."}
    assert not person_name_errors(o, I)


def test_one_person_roles_check_only_ids():
    """한 사람만 보는 역할(각자 대화 정리·말뜻 되묻기)은 다른 가족 이름을 몰라 이름 대조는 하지 않고 id만 본다."""
    one = {"member": ELDER[0]}
    assert not person_name_errors({"t": "태윤이가 보태 준다고 했어요. 지훈님"}, one)
    assert person_name_errors({"t": "m1님이 보태 준다고 했어요."}, one)


def test_mutation_every_role_output_in_full_flow(monkeypatch):
    """예시 가족 두 곳을 끝까지(재생 공급자): 원래 출력은 통과하고, 이름을 받는 역할에 없는 이름을 넣으면, 모든 역할에 id를 넣으면 잡는다."""
    from tests.test_api import _inject, call, run_flow
    seen = {}
    real = P.run_role

    def spy(key, inp, *a, **k):
        run = real(key, inp, *a, **k)
        if run.ok:
            seen.setdefault(key, (inp, run.output))
        return run
    monkeypatch.setattr(P, "run_role", spy)
    for pid in ("newly", "elder"):
        p = call("/api/preset", {"preset_id": pid})
        run_flow(p, p["scripts"]["answers"], p["scripts"]["replies"])
    name_roles = []
    for key, (inp, out) in seen.items():
        assert not person_name_errors(out, inp), (key, person_name_errors(out, inp))  # 원래 출력은 통과
        assert any("구성원 id" in e for e in ROLES[key].check(_inject(out, "m1님 말씀"), inp)), key
        if [m for m in (inp.get("members") or inp.get("keeps") or []) if isinstance(m, dict) and m.get("name")]:
            name_roles.append(key)
            errs = ROLES[key].check(_inject(out, "지훈님 말씀"), inp)
            assert any("없는 사람 이름" in e for e in errs), (key, errs)
    assert len(name_roles) >= 6, name_roles
