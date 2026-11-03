"""재무 원리 카드(ontology/cards.json, docs/12 6절): 불러오기, 가족 상황에 맞는 묶음 고르기, 정확성 검사.

카드는 상품·제도가 아닌 일반 원리다. 수가 적어 검색하지 않고, 코드가 가족 상황(금융정보 종류·나이)으로 주제를 골라
역할(공동 목표 제안·방법 설계)에 묶음째 넣는다. AI는 받은 카드 안에서만 근거를 대고, 쓴 카드 ID는 서버가 검사한다(G11).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .programs import source_text

HERE = Path(__file__).resolve().parent
TOPICS = ("saving", "emergency", "invest", "debt", "credit", "rent", "insurance", "retirement", "senior", "couple")
BASE_TOPICS = ("saving", "emergency")  # 어느 가족에게나
ADULT, CHILD_MAX, RETIRE_NEAR, SENIOR = 19, 18, 50, 60


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads((HERE / "cards.json").read_text(encoding="utf-8"))


def load() -> dict[str, dict]:
    return {c["id"]: c for c in _data()["cards"]}


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


def for_family(family: dict) -> list[dict]:
    """이 가족에게 넣을 카드 묶음(주제가 하나라도 겹치는 카드, cards.json 순서)."""
    on = set(topics_for(family))
    return [c for c in load().values() if on & set(c["topics"])]


def for_needs(need_ids: list[str]) -> list[dict]:
    """합의안의 필요(ontology/vocab.json)와 이어진 카드."""
    want = set(need_ids)
    return [c for c in load().values() if want & set(c["needs"])]


def brief(cards: list[dict]) -> list[dict]:
    """AI에게 넣는 모양: ID·제목·설명만(인용 원문은 서버가 검사·화면 표시에 쓴다)."""
    return [{"card_id": c["id"], "title": c["title"], "text": c["text"]} for c in cards]


def view(card_id: str) -> dict:
    """화면에서 근거 문구를 누르면 보이는 원문: 인용 + 출처 이름·주소·작성일."""
    c = load()[card_id]
    idx = {s["doc_key"]: s for s in json.loads((HERE.parent / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]
           if s.get("doc_key")}
    return {"card_id": c["id"], "title": c["title"], "text": c["text"], "published": c["published"],
            "quotes": [{"quote": q["quote"], "publisher": idx.get(q["doc_key"], {}).get("publisher", ""),
                        "source_title": idx.get(q["doc_key"], {}).get("title", ""), "url": idx.get(q["doc_key"], {}).get("url", "")}
                       for q in c["quotes"]]}


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _date_in(text: str, iso: str) -> bool:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{y}.{m}.{d}." in re.sub(r"\s+", "", text)


def check(providers: set[str] | None = None) -> list[str]:
    """정확성 검사. 문제 목록을 돌려준다.
    G3 인용이 원문에 글자 그대로 / G4 설명의 숫자가 인용 안에 / 작성일이 원문에 / 필요·주제가 어휘에 있음 /
    설명은 2~3문장 / G12 설명에 금융회사 이름이 없음(providers: 공시 금융회사 이름)."""
    vocab = {n["id"] for n in json.loads((HERE / "vocab.json").read_text(encoding="utf-8"))["needs"]}
    problems, seen = [], set()
    for c in _data()["cards"]:
        cid = c["id"]
        if cid in seen:
            problems.append(f"{cid}: ID 겹침")
        seen.add(cid)
        texts = {}
        for q in c["quotes"]:
            if q["doc_key"] not in texts:
                try:
                    texts[q["doc_key"]] = source_text(q["doc_key"])[1]
                except (IndexError, FileNotFoundError):
                    problems.append(f"{cid}: 원문 없음 {q['doc_key']}")
                    continue
            if q["quote"] not in texts[q["doc_key"]]:
                problems.append(f"{cid}: 인용이 원문에 없음 {q['quote'][:30]}")
        quoted = {n.replace(",", "") for q in c["quotes"] for n in _NUM.findall(q["quote"])}
        for n in _NUM.findall(c["text"] + c["title"]):
            if n.replace(",", "") not in quoted:
                problems.append(f"{cid}: 숫자 {n}가 인용에 없음")
        if texts and not any(_date_in(t, c["published"]) for t in texts.values()):
            problems.append(f"{cid}: 작성일 {c['published']}이 원문에 없음")
        if set(c["needs"]) - vocab:
            problems.append(f"{cid}: 없는 필요 {sorted(set(c['needs']) - vocab)}")
        if not c["topics"] or set(c["topics"]) - set(TOPICS):
            problems.append(f"{cid}: 주제 {c['topics']}")
        n_sent = len(re.findall(r"[요다]\.", c["text"]))
        if not 1 <= n_sent <= 3:
            problems.append(f"{cid}: 설명 {n_sent}문장")
        for name in providers or ():
            if name in c["text"] or name in c["title"]:
                problems.append(f"{cid}: 금융회사 이름 {name}")
    return problems


# ---------- AI 출력 속 카드 근거: 제안 문장 안에 [[card:ID|근거 문구]]로 녹인다(2026-11-03 형님 결정) ----------
CARD_TAG = re.compile(r"\[\[\s*card\s*:\s*([A-Za-z0-9_]+)\s*\|([^\]|]+)\]\]")


def used_ids(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in CARD_TAG.finditer(text or "")))


def strip(text: str) -> str:
    """표시 꼬리표를 떼고 근거 문구만 남긴다(다음 역할에 넘기거나 글로만 보여 줄 때)."""
    return CARD_TAG.sub(lambda m: m.group(2).strip(), text or "")


def check_output(text: str, allowed: set[str], providers: set[str] | frozenset = frozenset()) -> list[str]:
    """G11: 쓴 카드가 이 호출에 준 카드인지. G12: 앞 단계 글에 금융회사 이름이 없는지. 고칠 말을 돌려준다."""
    errs = []
    bad = [i for i in used_ids(text) if i not in allowed]
    if bad:
        errs.append(f"주지 않은 카드를 썼어요: {', '.join(bad)}. cards에 있는 card_id만 쓰세요.")
    if "[[" in CARD_TAG.sub("", text or ""):
        errs.append("카드 근거 표시는 [[card:카드ID|근거 문구]] 모양이어야 해요.")
    names = sorted(n for n in providers if n and n in strip(text))
    if names:
        errs.append(f"금융회사 이름을 쓰면 안 돼요: {', '.join(names)}. 상품·회사 이야기는 조건 비교 단계에서만 해요.")
    return errs
