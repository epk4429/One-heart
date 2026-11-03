"""제도·법 RAG(rag/index.py): 조각이 원문 그대로인지, 노드 안에서만 찾는지, 정답 질문에 맞는 원문이 나오는지, 인용 검사(G11)."""

import hashlib
import json
from pathlib import Path

import pytest

from ontology.programs import load as load_programs
from ontology.search import load as load_ontology
from rag import index as R
from server.app import dispatch

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not R.available(), reason="원문 저장소·RAG 색인이 없는 환경")


def test_chunks_are_verbatim_and_sources_unchanged():
    """G3: 조각 글이 원문에 글자 그대로 있고, 원문 파일은 수집 때의 sha256 그대로다."""
    idx = {s["source_id"]: s for s in json.loads((ROOT / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]}
    texts = {}
    for c in R.load()["chunks"]:
        s = idx[c["source_id"]]
        if c["source_id"] not in texts:
            t = (ROOT / s["file"]).read_text(encoding="utf-8")
            assert hashlib.sha256(t.encode("utf-8")).hexdigest() == s["sha256"]
            texts[c["source_id"]] = t
        assert c["text"] in texts[c["source_id"]]


def test_every_chunk_is_tagged_with_known_nodes():
    known = set(load_ontology()["types"]) | set(load_programs())
    cs = R.load()["chunks"]
    assert cs and all(c["nodes"] and set(c["nodes"]) <= known for c in cs)
    assert len({c["chunk_id"] for c in cs}) == len(cs)
    assert {c["doc_key"] for c in cs} >= {"law_basic_pension", "law_tax_special", "law_depositor_protection", "hf_reverse_mortgage", "nhuf_didimdol"}


def test_law_addenda_are_left_out():
    """부칙(지난 개정의 경과 규정: 다른 법 고치기, 시행일)은 조각으로 만들지 않는다."""
    law = [c for c in R.load()["chunks"] if c["doc_key"] == "law_depositor_protection"]
    assert not any("시행일" in (c["title"] or "") for c in law)


@pytest.mark.parametrize("nodes, q, must", [
    (["PG_reverse_mortgage"], "가입 나이 조건", "55세"),
    (["PG_didimdol"], "대출 한도", "2억원"),
    (["PG_beotimmok"], "중도상환수수료", "중도상환수수료"),
    (["PG_basic_pension"], "소득인정액", "소득인정액"),
    (["PG_subscription"], "무주택 소득공제", "소득공제"),
    (["P_term_deposit"], "비과세종합저축", "기초연금 수급자"),  # 조세특례제한법 제88조의2
])
def test_gold_questions_find_the_right_text(nodes, q, must):
    res = R.search(q, nodes)
    assert res and any(must in r["text"] for r in res[:3] + [x for x in res if x["kind"] == "법령"])
    assert all(set(nodes) & set(r["nodes"]) for r in res)  # 고른 노드 안에서만


def test_tax_free_savings_article_is_found_for_savings():
    res = R.search("비과세종합저축", ["P_installment_savings"])
    assert any(r["article"] == "제88조의2" for r in res)


def test_unrelated_question_finds_nothing():
    assert R.search("주식 투자 수익률", ["PG_basic_pension"]) == []


def test_check_citation():
    c = next(c for c in R.load()["chunks"] if c["article"] == "제88조의2")
    assert R.check_citation(c["chunk_id"], "65세 이상인 거주자로서")
    assert not R.check_citation(c["chunk_id"], "60세 이상인 거주자로서")
    assert not R.check_citation("C_none_000", "65세")


def test_api_rag_search():
    st, out = dispatch("POST", "/api/rag/search", json.dumps({"nodes": ["PG_reverse_mortgage"], "query": "가입 나이 조건"}).encode(), {}, "t")
    assert st == 200 and out["results"] and "원문" in out["note"]
    st, _ = dispatch("POST", "/api/rag/search", json.dumps({"nodes": ["NOT_A_NODE"], "query": "x"}).encode(), {}, "t")
    assert st == 400
    cfg = dispatch("POST", "/api/config", b"{}", {}, "t")[1]
    assert cfg["rag"]["available"] is True and cfg["rag"]["topics"]["program"]
