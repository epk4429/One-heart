"""AI의 근거 자료(금융꿀팁 RAG 조각): 가족 상황에 맞는 조각 고르기, AI 출력 속 근거 표시 검사, 화면에 보여 줄 원문.

2026-11-04 형님 결정: 재무 원리 카드(ontology/cards)를 없애고, 근거는 금감원 금융꿀팁 원문 조각(RAG, kind "꿀팁")으로 댄다.
- 이 파일은 RAG(rag/index.py)만 부른다. 온톨로지와 무관하다.
- 가족 정보(금융정보 종류·나이)로 주제를 고르고, 주제마다 검색어로 꿀팁 조각을 찾아 역할(공동 목표 제안·방법 설계)에 묶음째 넣는다.
- AI는 받은 조각 안에서만 근거를 대고, 근거마다 원문 인용(조각에 글자 그대로 있는 말)을 단다. 서버가 조각 ID와 인용을 검사한다(G11).
"""

from __future__ import annotations

import re

from rag import index as rag

TOPICS = ("saving", "emergency", "invest", "debt", "credit", "rent", "insurance", "retirement", "senior", "couple")
BASE_TOPICS = ("saving", "emergency")  # 어느 가족에게나
ADULT, CHILD_MAX, RETIRE_NEAR, SENIOR = 19, 18, 50, 60
TOPIC_QUERY = {  # 주제 → 꿀팁 검색어(원문에 흔한 말)
    "saving": "예금 적금 목돈 만기 이자 저축",
    "emergency": "비상금 긴급자금 생활비 지출관리 여유자금",
    "invest": "펀드 투자 위험 원금손실 여유자금 분산",
    "debt": "대출 상환 금리 이자 부담 연체",
    "credit": "신용 신용등급 신용관리 연체 신용점수",
    "rent": "전세 보증금 전세자금대출 임차인 반환",
    "insurance": "보험 가입 보장 실손 병원비 보험료",
    "retirement": "연금 노후 퇴직연금 연금저축 은퇴",
    "senior": "고령 노후 연금 금융사기 어르신",
    "couple": "부부 결혼 신혼 공동 가계 목돈",
}
GOAL_QUERY = {  # 계산할 목표 종류 → 꿀팁 검색어(방법 설계에서만 쓴다)
    "reach_target": "목돈 종잣돈 모으기 적금 저축 만기 이자",
    "runway": "생활비 노후 연금 은퇴 자금 수령 인출",
    "debt_free": "대출 상환 중도상환 이자 부담 갚",
}
PER_TOPIC, BASE_PER_TOPIC, CAP = 2, 1, 10  # 가족 주제는 2조각, 기본 주제(저축·비상금)는 1조각씩, 한 번에 최대 10개
CONTEXT_K, GOAL_K, CONTEXT_COVER = 3, 2, 0.1  # 가족 말 검색 3조각, 목표 종류 검색 2조각, 검색어 낱말의 10%만 있어도 후보(말이 길어서)


def context_texts(summaries: dict | None, extra: list[str] | None = None) -> list[str]:
    """가족이 확인한 요약(지키고 싶은 것·양보·걱정)과 덧붙일 말(목표 문장 등)을 검색에 쓸 글로 모은다. 원문 대화는 쓰지 않는다."""
    out = [str(v.get(k, "")) for v in (summaries or {}).values() if isinstance(v, dict) for k in ("keep", "flexible", "worry")]
    return [t.strip() for t in out + list(extra or []) if t and t.strip()]


def topics_for(family: dict) -> list[str]:
    """가족 정보로 확실히 아는 것만으로 주제를 고른다(짐작하지 않음). 순서는 TOPICS 순서."""
    kinds = {i["kind"] for i in family.get("finance", [])}
    loan_types = {i.get("loan_type") for i in family.get("finance", []) if i["kind"] == "loan"}
    ages = [m["age"] for m in family["members"]]
    on = set(BASE_TOPICS)
    if "loan" in kinds:
        on |= {"debt", "credit"}
    if "lease_deposit" in kinds or "lease" in loan_types:
        on.add("rent")
    if "investment" in kinds:
        on.add("invest")
    if any(a <= CHILD_MAX for a in ages) or any(a >= SENIOR for a in ages):
        on.add("insurance")  # 아이가 아프거나 다칠 때, 병원비·간병
    if any(a >= RETIRE_NEAR for a in ages):
        on.add("retirement")
    if any(a >= SENIOR for a in ages):
        on.add("senior")
    if sum(a >= ADULT for a in ages) >= 2:
        on.add("couple")
    return [t for t in TOPICS if t in on]


def for_family(family: dict, context: list[str] | None = None, goal_type: str | None = None) -> list[dict]:
    """이 가족에게 넣을 꿀팁 조각 묶음. 앞쪽일수록 이 가족 상황에 가까운 조각이다(겹치면 한 번만, 최대 CAP개).
    ① 가족이 확인한 말(context)로 찾은 조각 ② 계산할 목표 종류(goal_type)로 찾은 조각
    ③ 가족 상황 주제(대출·전세·투자·나이 등)별 조각 ④ 모든 가족에게 해당하는 기본 주제(저축·비상금)는 1조각씩만(맨 뒤)."""
    out, seen = [], set()

    def add(chunks):
        for c in chunks:
            if c["chunk_id"] not in seen and len(out) < CAP:
                seen.add(c["chunk_id"])
                out.append(c)

    if context:
        add(rag.search(" ".join(context)[:400], kind="꿀팁", k=CONTEXT_K, topic=True, cover=CONTEXT_COVER))
    if goal_type in GOAL_QUERY:
        add(rag.search(GOAL_QUERY[goal_type], kind="꿀팁", k=GOAL_K, topic=True))
    topics = topics_for(family)
    for t in topics:
        if t not in BASE_TOPICS:
            add(rag.search(TOPIC_QUERY[t], kind="꿀팁", k=PER_TOPIC, topic=True))
    for t in topics:
        if t in BASE_TOPICS:
            add(rag.search(TOPIC_QUERY[t], kind="꿀팁", k=BASE_PER_TOPIC, topic=True))
    return out


def brief(chunks: list[dict]) -> list[dict]:
    """AI에게 넣는 모양: 조각 ID·어느 문서에서 나왔는지(제목)·글(출처 주소는 서버가 화면 표시에 쓴다)."""
    return [{"tip_id": c["chunk_id"], "from": re.sub(r"^금융꿀팁 200선\s*", "", c["doc_title"]), "text": c["text"]} for c in chunks]


def view(tip_id: str, quote: str) -> dict | None:
    """화면에서 근거 문구를 누르면 보이는 원문: 조각 글 + 인용 + 출처 이름·주소·수집일."""
    c = rag.get(tip_id)
    if not c:
        return None
    return {"tip_id": c["chunk_id"], "text": c["text"], "quote": quote, "publisher": c["publisher"],
            "source_title": c["doc_title"], "url": c["url"], "fetched_at": c["fetched_at"]}


# ---------- AI 출력 속 근거: 제안 문장 안에 [[tip:조각ID|근거 문구|원문 인용]]으로 녹인다 ----------
TAG = re.compile(r"\[\[\s*tip\s*:\s*([A-Za-z0-9_]+)\s*\|([^\]|]+)\|([^\]|]+)\]\]")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def used(text: str) -> list[tuple[str, str]]:
    """쓴 근거 (조각 ID, 원문 인용) 목록(같은 조각·인용은 한 번)."""
    return list(dict.fromkeys((m.group(1), m.group(3).strip()) for m in TAG.finditer(text or "")))


def used_ids(text: str) -> list[str]:
    return list(dict.fromkeys(i for i, _ in used(text)))


def strip(text: str) -> str:
    """표시 꼬리표를 떼고 근거 문구만 남긴다(다음 역할에 넘기거나 글로만 보여 줄 때)."""
    return TAG.sub(lambda m: m.group(2).strip(), text or "")


def check_output(text: str, allowed: set[str], providers: set[str] | frozenset = frozenset()) -> list[str]:
    """G11: 쓴 조각이 이 호출에 준 조각인지, 원문 인용이 그 조각에 글자 그대로 있는지, 근거 문구의 숫자가 인용에 있는지.
    G12: 앞 단계 글에 금융회사 이름이 없는지. 고칠 말을 돌려준다."""
    errs = []
    for m in TAG.finditer(text or ""):
        tid, phrase, quote = m.group(1), m.group(2).strip(), m.group(3).strip()
        if tid not in allowed:
            errs.append(f"주지 않은 조각을 썼어요: {tid}. tips에 있는 tip_id만 쓰세요.")
        elif not rag.check_citation(tid, quote):
            errs.append(f"원문 인용이 {tid}의 글에 그대로 없어요: '{quote[:30]}'. 조각 글에서 그대로 복사하세요.")
        elif {n.replace(",", "") for n in _NUM.findall(phrase)} - {n.replace(",", "") for n in _NUM.findall(quote)}:
            errs.append(f"근거 문구의 숫자는 원문 인용에 있는 숫자만 쓸 수 있어요: '{phrase[:30]}'")
    if "[[" in TAG.sub("", text or ""):
        errs.append("근거 표시는 [[tip:tip_id|근거 문구|원문 인용]] 모양이어야 해요.")
    names = sorted(n for n in providers if n and n in strip(text))
    if names:
        errs.append(f"금융회사 이름을 쓰면 안 돼요: {', '.join(names)}. 상품·회사 이야기는 조건 비교 단계에서만 해요.")
    return errs
