"""법령·금융꿀팁 RAG: 원문 저장소(knowledge/sources/docs의 법령, 금감원 꿀팁) → 조각 → 검색.

- 색인 대상은 법령(kind "법령")과 금융꿀팁(kind "꿀팁")이다(2026-11-04 결정). 제도 안내문은 온톨로지의 자격 규칙 출처로만 쓰고 여기서 찾지 않는다.
- 온톨로지와 독립이다. 조각에 온톨로지 ID를 붙이지 않고, 온톨로지 코드를 부르지 않으며, 온톨로지도 이 검색 결과를 쓰지 않는다.
  범위는 아래 LAW_SCOPE(법령마다 색인할 조문)로 RAG가 스스로 정한다.
- 조각: 법령은 조문 단위(긴 조문은 항 단위로 나눔), 꿀팁은 □ 절 단위. 조각 글은 원문의 연속된 줄 그대로다(G3: 원문에 글자 그대로 있음).
- 검색: BM25(글자 2-gram). 결과는 원문 그대로(요약·생성 없음).
- 쓰는 곳: 화면의 '관련 법령 찾아보기'(법령만), AI의 근거(공동 목표 제안·방법 설계: llm/evidence.py가 꿀팁 조각을 찾아 준다). 자격 판정·금리·한도에는 쓰지 않는다(그건 온톨로지 규칙).
- G11: AI가 RAG로 답할 때는 chunk_id + 인용을 달고, check_citation이 인용이 그 조각에 글자 그대로 있는지 본다.

만들기: python -m rag.index → knowledge/rag/chunks.jsonl
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "knowledge/sources/index.json"
OUT = ROOT / "knowledge/rag/chunks.jsonl"
LAW_SCOPE = {  # 법령 → 색인할 조문. "*" = 모든 조문, "match" = 조문 글에 그 말이 있을 때만, "articles" = 그 조문 번호만(조세특례제한법처럼 매우 큰 법)
    "law_basic_pension": {"*": True},
    "law_hf_corp": {"match": r"주택담보노후연금|주택저당채권|주택저당증권|보금자리"},
    "law_hf_corp_decree": {"match": r"주택담보노후연금|노후연금|주택저당채권|주택저당증권|보금자리"},
    "law_housing_fund": {"match": r"융자|대출|전세자금|구입자금|청약"},
    "law_housing_supply_rule": {"*": True},
    "law_depositor_protection": {"match": r"보험금|예금자등|보호되는"},
    "law_tax_special": {"articles": ["제87조", "제88조의2"]},
}
TIP_PREFIX = "fss_tip_"  # 금융꿀팁 문서의 doc_key 머리
KINDS = ("법령", "꿀팁")
MAX_CHARS = 900
TOPICS = {  # 화면의 주제 버튼(질문 → 검색어)
    "law": [["예금자보호는 얼마까지", "예금자보호 보험금 한도 지급"], ["세금 없는 저축(비과세)", "비과세종합저축 과세특례 이자소득"],
            ["기초연금 받는 사람", "기초연금 수급권자 지급 대상 소득인정액"], ["주택연금(주택담보노후연금)", "주택담보노후연금 보증 연금 지급 담보"],
            ["청약·국민주택", "청약 국민주택 공급 입주자 저축"], ["주택도시기금 대출", "주택도시기금 융자 대출 전세자금"]],
}
MIN_COVER = 0.5
TOPIC_COVER = 0.25  # 주제 버튼은 원문 용어를 여러 개 넣은 검색어라 그중 일부만 있어도 된다
_ART = re.compile(r"^(제\d+조(?:의\d+)?)(\(([^)]*)\))?")


def _sources() -> list[dict]:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))["sources"]
    return [s for s in idx if s.get("doc_key") in LAW_SCOPE or str(s.get("doc_key", "")).startswith(TIP_PREFIX)]


def kind_of(doc_key: str) -> str:
    return "꿀팁" if doc_key.startswith(TIP_PREFIX) else "법령"


_TIP_START = re.compile(r"^[□◈]")
_TIP_HEADER = re.compile(r"^(담당부서|책임자|담당자)$|\d{2,4}-\d{3,4}|^제\s*목\s*:")


def _chunk_tip(lines: list[str]) -> list[tuple[str, int, int]]:
    """꿀팁(보도자료 본문): 맨 위 담당부서·연락처 표(담당부서·책임자·담당자 줄, 전화번호 줄, '제 목' 줄)를 건너뛰고,
    □ 절에서 끊고(300자 넘었을 때), 900자를 넘으면 줄 경계에서 끊는다. 표 조각(짧은 줄투성이)은 뺀다. → (제목, 시작 줄, 끝 줄 다음)."""
    head = [i for i, l in enumerate(lines[:40]) if _TIP_HEADER.search(l)]
    begin = (max(head) + 1) if head else 0
    out, start, size = [], None, 0

    def flush(a: int, end: int):
        body = [l for l in lines[a:end] if l.strip()]
        short = sum(1 for l in body if len(l) < 8)
        if sum(len(l) for l in body) >= 80 and short * 2 <= len(body):
            out.append((lines[a][:40], a, end))

    for i in range(begin, len(lines)):
        l = lines[i]
        if start is not None and (size + len(l) > MAX_CHARS or (size >= 300 and _TIP_START.match(l))):
            flush(start, i)
            start, size = None, 0
        if start is None:
            start = i
        size += len(l) + 1
    if start is not None:
        flush(start, len(lines))
    return out


def _chunk_law(lines: list[str]) -> list[tuple[str, int, int, str]]:
    """법령: 조문 줄('제3조(…)')에서 끊고, 긴 조문은 항(①②…) 줄에서 다시 끊는다. → (제목, 시작, 끝, 조문 번호)."""
    out, start, art, title, size = [], None, None, "", 0
    for i, l in enumerate(lines):
        m = _ART.match(l)
        cut = m or (start is not None and size + len(l) > MAX_CHARS and re.match(r"^[①-⑳]", l))
        if cut:
            if start is not None:
                out.append((title, start, i, art))
            if m:
                art = m.group(1)
                title = f"{m.group(1)}({m.group(3)})" if m.group(3) else m.group(1)
            else:
                title = title.split(" ·")[0] + f" · {l[:1]}"
            start, size = i, 0
        if start is not None:
            size += len(l) + 1
    if start is not None:
        out.append((title, start, len(lines), art))
    return out


def _in_scope(key: str, art: str | None, text: str) -> bool:
    rule = LAW_SCOPE[key]
    return bool(rule.get("*") or (art in rule.get("articles", [])) or (rule.get("match") and re.search(rule["match"], text)))


def build() -> list[dict]:
    chunks, seen = [], set()
    for s in _sources():
        key = s["doc_key"]
        text = (ROOT / s["file"]).read_text(encoding="utf-8")
        lines = text.split("\n")
        kind = kind_of(key)
        if kind == "꿀팁":
            pieces = [(t, a, b, None) for t, a, b in _chunk_tip(lines)]
        else:
            arts = [i for i, l in enumerate(lines) if _ART.match(l)]
            first = next((i for i in arts if not lines[i].startswith("제1조")), None)  # 본문이 제2조 이상으로 들어선 뒤
            end = next((i for i in arts if first is not None and i > first and re.match(r"^제1조\s*\(", lines[i])), len(lines))  # 부칙의 제1조(시행일)부터는 지난 개정 경과 규정
            pieces = _chunk_law(lines[:end])
        for title, a, b, art in pieces:
            body = "\n".join(lines[a:b]).strip()
            if len(body) < 40 or (kind == "법령" and not _in_scope(key, art, title + "\n" + body)):
                continue
            h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
            if (key, h) in seen:
                continue
            seen.add((key, h))
            assert body in text  # G3
            n = sum(1 for c in chunks if c["doc_key"] == key)
            chunks.append({"chunk_id": f"C_{key}_{n:03d}", "source_id": s["source_id"], "doc_key": key, "kind": kind, "title": title,
                           "article": art, "text": body, "publisher": s["publisher"],
                           "doc_title": s["title"], "url": s["url"], "fetched_at": s["fetched_at"][:10],
                           "effective_date": s.get("effective_date")})
    return chunks


def write() -> list[dict]:
    chunks = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    load.cache_clear()
    return chunks


# ---------- 검색 ----------
_ASK = re.compile(r"어떻게|어떤|돼요|되나요|되요|얼마나|얼마|뭐예요|무엇|인가요|해요|있어요|있나요|알려\s*줘요?|궁금해요|나요|까요|예요|이에요|싶어요|할\s*수")
_JOSA = re.compile(r"(하면|하는|하고|에서|으로|에게|까지|부터|은|는|이|가|을|를|에|의|도|로|와|과|면|요)$")
SYNONYMS = {  # 질문에 흔한 말 → 원문에 흔한 말(글자 검색 보강). 원문 용어를 바꾸지는 않는다
    "나이": ["연령", "세"], "해지": ["중도상환", "철회", "해약"], "그만두": ["해지", "중도상환"], "갚": ["상환"], "서류": ["구비서류", "제출"],
    "받는": ["수급", "대상"], "사람": ["대상", "자격"], "누가": ["대상", "자격", "요건"], "조건": ["요건", "자격", "대상"], "돈": ["금액"],
    "이자": ["금리", "이율"], "금리": ["이율"], "신청": ["접수", "취급", "상담"], "어디": ["취급", "영업점", "상담"], "세금": ["과세", "비과세", "소득공제"],
    "보호": ["보험금", "예금자"], "얼마까지": ["한도"], "주의": ["유의사항", "제한"],
}


def _grams(t: str) -> list[str]:
    """낱말 안의 글자 2-gram(낱말 경계를 넘지 않음). 한 글자 낱말은 그 글자."""
    out = []
    for w in re.findall(r"[0-9A-Za-z가-힣]+", t.lower()):
        out += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
    return out


def _terms(query: str) -> list[list[str]]:
    """질문 → 낱말별 글자쌍 묶음(비슷한 말 포함). 말끝·조사는 뗀다."""
    out = []
    for w in re.findall(r"[0-9A-Za-z가-힣]+", _ASK.sub(" ", query)):
        w = _JOSA.sub("", w) if len(w) > 2 else w
        if len(w) < 2:
            continue
        alts = [w] + next((v for k, v in SYNONYMS.items() if w.startswith(k)), [])
        out.append(sorted({g for a in alts for g in _grams(a)}))
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    """조각 + BM25 통계. 원문 저장소가 없는 배포 묶음에서는 빈 색인."""
    if not OUT.exists():
        return {"chunks": [], "tf": [], "stats": {}}
    chunks = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    tf = [Counter(_grams(c["text"])) + Counter(_grams(c["title"])) for c in chunks]  # 제목(조문 제목·소제목)은 한 번 더 센다
    stats = {}  # BM25 통계는 종류별로 따로 낸다(법령과 꿀팁은 글의 성격이 달라 점수를 섞으면 어긋난다)
    for kind in KINDS:
        tfs = [t for c, t in zip(chunks, tf) if c["kind"] == kind]
        stats[kind] = {"n": len(tfs), "df": Counter(g for t in tfs for g in t),
                       "avg": sum(sum(t.values()) for t in tfs) / len(tfs) if tfs else 1.0}
    return {"chunks": chunks, "tf": tf, "stats": stats}


def available() -> bool:
    return bool(load()["chunks"])


def laws() -> list[dict]:
    """색인된 법령 목록(화면의 법령 선택용)."""
    seen = {}
    for c in load()["chunks"]:
        if c["kind"] == "법령":
            seen.setdefault(c["doc_key"], {"doc_key": c["doc_key"], "doc_title": c["doc_title"]})
    return list(seen.values())


def get(chunk_id: str) -> dict | None:
    return next((c for c in load()["chunks"] if c["chunk_id"] == chunk_id), None)


def search(query: str, laws: list[str] | None = None, kind: str = "법령", k: int = 5, topic: bool = False,
           cover: float | None = None, k1: float = 1.2, b: float = 0.75) -> list[dict]:
    """kind("법령"|"꿀팁") 조각 안에서 BM25. laws를 주면 그 문서(doc_key)만. 결과 조각은 원문 그대로(요약·생성 없음).
    cover: 검색어 낱말 중 조각에 있어야 하는 비율을 직접 정한다(없으면 질문 MIN_COVER, 주제 버튼 TOPIC_COVER)."""
    ix = load()
    want = set(laws or [])
    terms = _terms(query)
    q = Counter(g for t in terms for g in t)
    st = ix["stats"].get(kind) or {"n": 0, "df": Counter(), "avg": 1.0}
    n, df, avg = st["n"], st["df"], st["avg"]
    scored = []
    for c, tf in zip(ix["chunks"], ix["tf"]):
        if c["kind"] != kind or (want and c["doc_key"] not in want):
            continue
        dl = sum(tf.values())
        s = 0.0
        for g in q:
            f = tf.get(g, 0)
            if f:
                idf = math.log(1 + (n - df[g] + 0.5) / (df[g] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avg))
        hit = sum(1 for t in terms if any(tf.get(g) for g in t)) / len(terms) if terms else 0
        if s > 0 and hit >= (cover if cover is not None else TOPIC_COVER if topic else MIN_COVER):  # 질문 낱말(비슷한 말 포함)의 절반도 없는 조각은 관련 없다고 보고 내놓지 않는다(못 찾으면 못 찾았다고)
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, c in scored[:k]:
        lines = c["text"].split("\n")
        focus = max(range(len(lines)), key=lambda i: (sum(1 for g in set(_grams(lines[i])) if g in q) > 0, len(lines[i]) >= 15,
                                                      sum(1 for g in set(_grams(lines[i])) if g in q)))  # 제목 한 줄보다 내용 줄을 강조
        out.append({**{x: c[x] for x in ("chunk_id", "doc_key", "title", "article", "text", "publisher", "doc_title", "url", "fetched_at", "effective_date")},
                    "kind": c["kind"], "score": round(s, 2), "focus": lines[focus]})
    return out


def check_citation(chunk_id: str, quote: str) -> bool:
    """G11: AI 답의 인용이 그 조각에 글자 그대로 있는가(공백 차이는 무시)."""
    c = next((c for c in load()["chunks"] if c["chunk_id"] == chunk_id), None)
    norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
    return bool(c and quote.strip() and norm(quote) in norm(c["text"]))


if __name__ == "__main__":
    cs = write()
    print(f"{OUT.relative_to(ROOT)}  조각 {len(cs)}개")
    for k, v in Counter(c["doc_key"] for c in cs).most_common():
        print(f"  {k}: {v}")
