"""금지 표현 검사(파일럿 1-4, 임의결정 67): 금융상품을 권하거나 광고하는 말을 모든 AI 출력에서 막는다.
① 예문(잡아야 할 말 / 잡으면 안 되는 말) ② 모든 역할에 붙었는지 ③ 돌연변이: 실제 흐름의 역할 출력에 금지 표현을 넣으면 그 역할 검사가 잡는다."""

import json
import os

import pytest

os.environ["LLM_PROVIDER"] = "replay"

from llm import pipeline as P  # noqa: E402
from llm.roles import ROLES, forbidden_errors, forbidden_expressions  # noqa: E402
from tests.test_api import _iso  # noqa: E402,F401  환경 격리(재생 공급자·체험 코드 없음)를 이 파일에도 건다

MUST_CATCH = [
    "이 적금을 추천해요.",
    "지금 바로 가입하세요.",
    "청약통장에 가입해 보세요.",
    "이 방법이 더 유리해요.",
    "고정금리가 유리합니다.",
    "수익 보장이 되는 상품이에요.",
    "이자가 보장돼요.",
    "확정 수익을 얻을 수 있어요.",
    "무조건 오르니까 걱정 마세요.",
    "손해 볼 일이 없어요.",
    "손실은 없어요.",
    "최고의 상품이에요.",
    "가장 좋은 투자예요.",
    "주식에 투자하세요.",
    "지금 매수하세요.",
    # 투자 비중 권유(1-4)
    "주식 비중을 늘리세요.",
    "투자를 줄이는 게 좋아요.",
    "여윳돈의 30%는 주식에 넣으세요.",
    "펀드에 투자하는 것이 바람직합니다.",
    "주식 비중은 20%로 하는 게 좋아요.",
    "지금은 주식을 더 섞는 편이 나아요.",
    "투자 비중을 높이셔야 해요.",
]

MUST_PASS = [
    "부모님 두 분은 대전 서구 아파트에 사세요",  # '살다'의 높임
    "어디서 사세요?",
    "예금은 원금 보장이 돼요.",  # 사실 설명
    "원금 보장이 아니라서 조금 불안할 수 있어요.",
    "예적금은 확정수익형 상품이에요.",
    "무조건 집은 지키고 싶어요.",  # 가족이 흔히 쓰는 말
    "추천이 아니라 우리 목표에 맞는 순서예요.",
    "가입 여부는 가족이 직접 정해요.",
    "투자 비중은 가족이 정한 값을 적었어요.",
    "손해를 줄이려면 비상금을 먼저 모아 두면 좋아요.",
    # 투자 비중을 설명하거나 가족에게 결정을 맡기는 말(실제 Claude 출력에서 가져옴)
    "투자 비중을 줄여도 된다고 하셔서 주식은 여윳돈의 20%까지만 섞어요.",
    "투자 비중을 줄였어요.",
    "그동안 투자는 조금 줄이고, 양가 용돈은 지금처럼 똑같이 드리면 어떨까요?",
    "이 방법은 여윳돈의 주식 20%까지로 계산했어요.",
    "투자 비중은 줄일 수 있어요.",
    "주식 비중도 낮춰서 휴직 중 마음 부담이 비교적 적어요.",
    "투자 비중은 가족이 직접 정하셔야 해요.",
    "생활비를 조금 아끼고 투자 비중을 유지해 집 마련을 가장 빨리 노려요.",
]


@pytest.mark.parametrize("text", MUST_CATCH)
def test_catches_promotional_words(text):
    assert forbidden_expressions(text), text


@pytest.mark.parametrize("text", MUST_PASS)
def test_does_not_catch_plain_words(text):
    assert not forbidden_expressions(text), (text, forbidden_expressions(text))


def test_tip_quotes_are_not_checked():
    """금융꿀팁 원문 인용은 글자 그대로여야 하므로(G11) 원문 속 '가입하세요'는 막지 않는다."""
    o = {"text": "[[tip:C_x|적금과 예금|목돈을 운용할 때는 거치식 상품인 정기예금에 가입하세요.]]이니까 예금으로 모아요."}
    assert not forbidden_errors(o)
    assert forbidden_errors({"text": o["text"] + " 꼭 가입하세요."})


def test_every_role_has_the_check():
    """모든 역할의 검사에 금지 표현 검사가 붙어 있다(실제 입력으로 잡는지는 아래 돌연변이 테스트가 본다)."""
    for key, role in ROLES.items():
        assert getattr(role.check, "__wrapped__", None), key


def test_mutation_every_role_output_in_full_flow(monkeypatch):
    """예시 가족 두 곳을 끝까지(재생 공급자): 원래 출력은 금지 표현 검사를 통과하고, 금지 표현을 넣으면 그 역할 검사가 잡는다."""
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
    assert len(seen) >= 10, sorted(seen)
    for key, (inp, out) in seen.items():
        assert not [e for e in ROLES[key].check(out, inp) if "권하거나 광고" in e], key  # 원래 출력은 통과
        for word in ("이 적금을 추천해요", "지금 가입하세요", "수익 보장", "주식 비중을 30%로 늘리는 게 좋아요"):
            errs = ROLES[key].check(_inject(out, word), inp)
            assert any("권하거나 광고" in e for e in errs), (key, word, errs)
    json.dumps(sorted(seen))


def _screen_lines(path):
    """화면에 고정된 글(주석 줄과 줄 끝 주석은 뺌)."""
    import re as _re
    from pathlib import Path
    out = []
    for n, line in enumerate((Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8").splitlines(), 1):
        t = line.strip()
        if t.startswith(("//", "/*", "*", "<!--")):
            continue
        t = _re.sub(r"\s//\s[^`\"']*$", "", t)
        if _re.search(r"[가-힣]", t):
            out.append((n, t))
    return out


@pytest.mark.parametrize("path", ["web/index.html", "web/js/app.js"])
def test_fixed_screen_text_has_no_promotional_words(path):
    """화면 문구 다듬기(1-5, 2026-11-10): 고정된 화면 문구도 AI 출력과 같은 금지 표현 목록으로 검사한다(docs/07 부록 C).
    화면 이름 '상품 추천'(형님이 정한 7단계 이름)은 예외."""
    bad = []
    for n, t in _screen_lines(path):
        found = forbidden_expressions(t.replace("상품 추천", ""))
        if found:
            bad.append((n, found, t[:80]))
    assert not bad, bad
