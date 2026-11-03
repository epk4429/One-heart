"""제도·법 RAG: 원문 저장소(knowledge/sources/docs) → 조각(chunk) → 노드 태그 → 검색(docs/12 7절).

- 조각: 법령은 조문 단위(긴 조문은 항 단위로 나눔), 안내문은 제목 단위. 조각 글은 원문의 연속된 줄 그대로다(G3: 원문에 글자 그대로 있음).
  안내 페이지의 메뉴(짧은 줄이 길게 이어지는 덩어리)와 같은 기관 페이지에 모두 나오는 줄(머리말·꼬리말)은 뺀다.
- 노드 태그: 조각마다 온톨로지 노드(제도 PG_*, 상품 유형 P_*). 안내문은 그 문서를 출처로 쓰는 제도(ontology/programs.json),
  법령은 아래 LAW_TAGS. 태그가 없는 조각은 색인하지 않는다(엉뚱한 문서를 찾지 않게).
- 검색: BM25(글자 2-gram). 온톨로지로 먼저 고른 노드의 조각 안에서만 찾는다.
- 쓰는 곳: 화면의 제도 카드·상품 비교의 '더 알아보기'. 자격 판정·금리·한도에는 쓰지 않는다(그건 온톨로지 규칙).
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
SAVINGS = ["P_term_deposit", "P_installment_savings"]
HOUSING_FUND = ["PG_didimdol", "PG_newborn_didimdol", "PG_beotimmok", "PG_newborn_beotimmok", "PG_subscription"]
HOUSING_LOANS = ["PG_didimdol", "PG_newborn_didimdol", "PG_beotimmok", "PG_newborn_beotimmok"]
LAW_TAGS = {  # 법령 → 노드. "*" = 모든 조문, "match" = 조문(조각) 글에 그 말이 있을 때만, 그 밖의 키는 조문 번호
    "law_basic_pension": {"*": ["PG_basic_pension"]},
    "law_hf_corp": {"match": [(r"주택담보노후연금", ["PG_reverse_mortgage"]), (r"주택저당채권|주택저당증권|보금자리", ["PG_bogeumjari"])]},
    "law_hf_corp_decree": {"match": [(r"주택담보노후연금|노후연금", ["PG_reverse_mortgage"]), (r"주택저당채권|주택저당증권|보금자리", ["PG_bogeumjari"])]},
    "law_housing_fund": {"match": [(r"융자|대출|전세자금|구입자금", HOUSING_LOANS), (r"청약", ["PG_subscription"])]},
    "law_housing_supply_rule": {"*": ["PG_subscription"]},
    "law_depositor_protection": {"match": [(r"보험금|예금자등|보호되는", SAVINGS)]},
    "law_tax_special": {"제87조": ["PG_subscription"], "제88조의2": SAVINGS + ["PG_basic_pension"]},
}
MAX_CHARS = 900
TOPICS = {  # 화면의 주제 버튼(질문 → 검색어). 제도 카드용과 예금·적금용
    "program": [["누가 받을 수 있나요", "대상 요건 자격 연령 이상 범위"], ["얼마까지 되나요", "한도 금액 지급 기준연금액"],
                ["금리·비용", "금리 이율 보증료 수수료 비용"], ["중간에 갚거나 그만두면", "중도상환 수수료 해지 철회 상환"],
                ["주의할 점", "유의사항 제한 불가 제외 정지"], ["어디서 신청해요", "신청 상담 문의 취급 접수"]],
    "savings": [["예금자보호는 얼마까지", "예금자보호 보험금 한도 지급"], ["세금 없는 저축(비과세)", "비과세종합저축 과세특례 이자소득"]],
}
MIN_COVER = 0.5
TOPIC_COVER = 0.25  # 주제 버튼은 원문 용어를 여러 개 넣은 검색어라 그중 일부만 있어도 된다
_ART = re.compile(r"^(제\d+조(?:의\d+)?)(\(([^)]*)\))?")
_HEADING = re.compile(r"^[^\s.,:;()]{2,20}$|^[①-⑳\d]+\.\s*\S{2,20}$")


def _sources() -> list[dict]:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))["sources"]
    return [s for s in idx if s.get("doc_key")]


def _program_tags() -> dict[str, list[str]]:
    from ontology.programs import load
    out: dict[str, list[str]] = {}
    for pid, p in load().items():
        keys = {p.get("source")} | {v.get("source") for v in (p.get("terms") or {}).values() if isinstance(v, dict)}
        for k in keys - {None}:
            out.setdefault(k, []).append(pid)
    return out


def _body_lines(lines: list[str], common: set[str]) -> list[tuple[int, str]]:
    """메뉴·머리말·꼬리말을 뺀 본문 줄(원래 줄 번호와 함께). 짧은 줄(25자 미만)이 6줄 넘게 이어지면 메뉴로 본다."""
    keep, run = [], []
    for i, l in enumerate(lines):
        if len(l) < 25:
            run.append((i, l))
            continue
        if len(run) <= 6:
            keep += run
        run = []
        keep.append((i, l))
    if len(run) <= 6:
        keep += run
    return [(i, l) for i, l in keep if l not in common]


def _chunk_doc(lines: list[str], body: list[tuple[int, str]]) -> list[tuple[str, int, int]]:
    """안내문: 제목 줄에서 끊고(조각이 300자 넘었을 때), 900자를 넘으면 줄 경계에서 끊는다. 빠진 줄(메뉴)을 건너면 새 조각.
    → (제목, 시작 줄, 끝 줄 다음)."""
    out, start, prev, title, size = [], None, None, "", 0
    for i, l in body:
        new = start is None or i != prev + 1 or size + len(l) > MAX_CHARS or (_HEADING.match(l) and size >= 300)
        if new:
            carry = start is not None and i == prev + 1 and prev > start and _HEADING.match(lines[prev]) and not _HEADING.match(l)
            if carry:  # 앞 조각 끝 줄이 제목이면("중도상환수수료") 그 제목부터 새 조각
                out.append((title, start, prev))
                start, title, size = prev, lines[prev][:40], len(lines[prev]) + 1
            else:
                if start is not None:
                    out.append((title, start, prev + 1))
                start, title, size = i, l[:40], 0
        size += len(l) + 1
        prev = i
    if start is not None:
        out.append((title, start, prev + 1))
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


def _law_tags(key: str, art: str | None, text: str) -> list[str]:
    rule = LAW_TAGS[key]
    out = rule.get("*", []) + rule.get(art, [])
    for rx, nodes in rule.get("match", []):
        if re.search(rx, text):
            out += nodes
    return out


def build() -> list[dict]:
    srcs = _sources()
    prog = _program_tags()
    texts = {s["doc_key"]: (ROOT / s["file"]).read_text(encoding="utf-8") for s in srcs}
    by_pub: dict[str, list[str]] = {}
    for s in srcs:
        by_pub.setdefault(s["publisher"], []).append(s["doc_key"])
    chunks, seen = [], set()
    for s in srcs:
        key, text = s["doc_key"], texts[s["doc_key"]]
        lines = text.split("\n")
        if key in LAW_TAGS:
            arts = [i for i, l in enumerate(lines) if _ART.match(l)]
            first = next((i for i in arts if not lines[i].startswith("제1조")), None)  # 본문이 제2조 이상으로 들어선 뒤
            end = next((i for i in arts if first is not None and i > first and re.match(r"^제1조\s*\(", lines[i])), len(lines))  # 부칙의 제1조(시행일)부터는 지난 개정 경과 규정
            pieces = [(t, a, b, art) for t, a, b, art in _chunk_law(lines[:end])]
        else:
            peers = [set(texts[k].split("\n")) for k in by_pub[s["publisher"]] if k != key]
            common = set.intersection(*peers) & set(lines) if peers else set()
            pieces = [(t, a, b, None) for t, a, b in _chunk_doc(lines, _body_lines(lines, common))]
        for title, a, b, art in pieces:
            body = "\n".join(lines[a:b]).strip()
            if len(body) < 40:
                continue
            tags = _law_tags(key, art, title + "\n" + body) if key in LAW_TAGS else prog.get(key, [])
            h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
            if not tags or (key, h) in seen:
                continue
            seen.add((key, h))
            assert body in text  # G3
            n = sum(1 for c in chunks if c["doc_key"] == key)
            chunks.append({"chunk_id": f"C_{key}_{n:03d}", "source_id": s["source_id"], "doc_key": key, "title": title,
                           "article": art, "nodes": sorted(set(tags)), "text": body, "publisher": s["publisher"],
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
        return {"chunks": [], "tf": [], "df": Counter(), "avg": 1.0}
    chunks = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    tf = [Counter(_grams(c["text"])) + Counter(_grams(c["title"])) for c in chunks]  # 제목(조문 제목·소제목)은 한 번 더 센다
    df = Counter(g for t in tf for g in t)
    avg = sum(sum(t.values()) for t in tf) / len(tf) if tf else 1.0
    return {"chunks": chunks, "tf": tf, "df": df, "avg": avg}


def available() -> bool:
    return bool(load()["chunks"])


def search(query: str, nodes: list[str], k_doc: int = 3, k_law: int = 2, topic: bool = False, k1: float = 1.2, b: float = 0.75) -> list[dict]:
    """노드에 태그된 조각 안에서 BM25. 안내문 k_doc개 + 법령 k_law개(법령은 조문이 길고 많아 안내문을 밀어내지 않게 따로 센다).
    결과 조각은 원문 그대로(요약·생성 없음)."""
    ix = load()
    want = set(nodes)
    terms = _terms(query)
    q = Counter(g for t in terms for g in t)
    n = len(ix["chunks"])
    scored = []
    for c, tf in zip(ix["chunks"], ix["tf"]):
        if not want & set(c["nodes"]):
            continue
        dl = sum(tf.values())
        s = 0.0
        for g in q:
            f = tf.get(g, 0)
            if f:
                idf = math.log(1 + (n - ix["df"][g] + 0.5) / (ix["df"][g] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / ix["avg"]))
        hit = sum(1 for t in terms if any(tf.get(g) for g in t)) / len(terms) if terms else 0
        if s > 0 and hit >= (TOPIC_COVER if topic else MIN_COVER):  # 질문 낱말(비슷한 말 포함)의 절반도 없는 조각은 관련 없다고 보고 내놓지 않는다(못 찾으면 못 찾았다고)
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    docs = [x for x in scored if not x[1]["doc_key"].startswith("law_")][:k_doc]
    laws = [x for x in scored if x[1]["doc_key"].startswith("law_")][:k_law]
    out = []
    for s, c in docs + laws:
        lines = c["text"].split("\n")
        focus = max(range(len(lines)), key=lambda i: (sum(1 for g in set(_grams(lines[i])) if g in q) > 0, len(lines[i]) >= 15,
                                                      sum(1 for g in set(_grams(lines[i])) if g in q)))  # 제목 한 줄보다 내용 줄을 강조
        out.append({**{x: c[x] for x in ("chunk_id", "title", "article", "text", "publisher", "doc_title", "url", "fetched_at", "effective_date", "nodes")},
                    "kind": "법령" if c["doc_key"].startswith("law_") else "안내문", "score": round(s, 2), "focus": lines[focus]})
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
