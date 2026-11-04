"""법령 RAG(rag/index.py): 조각이 원문 그대로인지, 법령만 있고 온톨로지와 독립인지, 정답 질문에 맞는 원문이 나오는지, 인용 검사(G11)."""

import hashlib
import json
from pathlib import Path

import pytest

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


def test_only_laws_and_tips_and_independent_of_ontology():
    """법령(kind 법령)과 금융꿀팁(kind 꿀팁)만 색인하고, 조각에 온톨로지 ID(nodes)가 없다. RAG 코드는 온톨로지를 불러오지 않는다."""
    cs = R.load()["chunks"]
    laws = [c for c in cs if c["kind"] == "법령"]
    tips = [c for c in cs if c["kind"] == "꿀팁"]
    assert laws and tips and len(laws) + len(tips) == len(cs)
    assert all(c["doc_key"] in R.LAW_SCOPE for c in laws) and all(c["doc_key"].startswith("fss_tip_") for c in tips)
    assert all("nodes" not in c for c in cs)
    assert len({c["chunk_id"] for c in cs}) == len(cs)
    assert {c["doc_key"] for c in laws} == set(R.LAW_SCOPE)
    assert len({c["doc_key"] for c in tips}) == 18  # 금융꿀팁 18편 모두
    src = (ROOT / "rag/index.py").read_text(encoding="utf-8")
    assert "import ontology" not in src and "from ontology" not in src


def test_tip_chunks_skip_press_release_header_and_keep_size():
    tips = [c for c in R.load()["chunks"] if c["kind"] == "꿀팁"]
    assert all(80 <= len(c["text"]) <= R.MAX_CHARS for c in tips)
    assert not any("담당부서" in c["text"] and "책임자" in c["text"] for c in tips)  # 보도자료 맨 위 연락처 표


def test_search_keeps_kinds_apart():
    assert {r["kind"] for r in R.search("예금자보호 보험금 한도")} == {"법령"}
    res = R.search("펀드 투자 위험 원금손실 여유자금", kind="꿀팁", topic=True)
    assert res and {r["kind"] for r in res} == {"꿀팁"}
    assert not any(r["doc_key"].startswith("law_") for r in res)
    assert all(x["doc_key"].startswith("law_") for x in R.laws() and R.search("비과세종합저축"))


def test_law_addenda_are_left_out():
    """부칙(지난 개정의 경과 규정: 다른 법 고치기, 시행일)은 조각으로 만들지 않는다."""
    law = [c for c in R.load()["chunks"] if c["doc_key"] == "law_depositor_protection"]
    assert not any("시행일" in (c["title"] or "") for c in law)


def test_huge_law_is_limited_to_scoped_articles():
    """조세특례제한법(원문 1.8MB)은 정한 조문(제87조·제88조의2)만 색인한다."""
    arts = {c["article"] for c in R.load()["chunks"] if c["doc_key"] == "law_tax_special"}
    assert arts == {"제87조", "제88조의2"}


@pytest.mark.parametrize("q, doc_key, article", [
    ("비과세종합저축", "law_tax_special", "제88조의2"),
    ("예금자보호 보험금 한도", "law_depositor_protection", None),
    ("기초연금 소득인정액", "law_basic_pension", None),
    ("주택담보노후연금 보증", "law_hf_corp", None),
    ("청약 국민주택", "law_housing_supply_rule", None),
])
def test_gold_questions_find_the_right_law(q, doc_key, article):
    res = R.search(q)
    assert res and all(r["kind"] == "법령" for r in res)
    assert any(r["doc_key"] == doc_key and (article is None or r["article"] == article) for r in res[:3])


def test_topic_buttons_find_their_law():
    want = {"예금자보호는 얼마까지": "law_depositor_protection", "세금 없는 저축(비과세)": "law_tax_special",
            "기초연금 받는 사람": "law_basic_pension", "주택연금(주택담보노후연금)": "law_hf_corp",
            "청약·국민주택": "law_housing_supply_rule", "주택도시기금 대출": "law_housing_fund"}
    assert {l for l, _ in R.TOPICS["law"]} == set(want)
    for label, q in R.TOPICS["law"]:
        assert any(r["doc_key"] == want[label] for r in R.search(q, topic=True)[:3]), label


def test_law_filter():
    res = R.search("한도", ["law_depositor_protection"])
    assert res and {r["doc_key"] for r in res} == {"law_depositor_protection"}


def test_unrelated_question_finds_nothing():
    assert R.search("고양이 사료 추천") == []


def test_check_citation():
    c = next(c for c in R.load()["chunks"] if c["article"] == "제88조의2")
    assert R.check_citation(c["chunk_id"], "65세 이상인 거주자로서")
    assert not R.check_citation(c["chunk_id"], "60세 이상인 거주자로서")
    assert not R.check_citation("C_none_000", "65세")


def test_api_rag_search():
    st, out = dispatch("POST", "/api/rag/search", json.dumps({"query": "비과세종합저축"}).encode(), {}, "t")
    assert st == 200 and out["results"] and "원문" in out["note"] and "nodes" not in out
    st, out = dispatch("POST", "/api/rag/search", json.dumps({"query": "한도", "laws": ["law_depositor_protection", "NOT_A_LAW"]}).encode(), {}, "t")
    assert st == 200 and {r["doc_key"] for r in out["results"]} == {"law_depositor_protection"}
    st, _ = dispatch("POST", "/api/rag/search", json.dumps({"query": ""}).encode(), {}, "t")
    assert st == 400
    cfg = dispatch("POST", "/api/config", b"{}", {}, "t")[1]
    assert cfg["rag"]["available"] is True and cfg["rag"]["topics"]["law"]
