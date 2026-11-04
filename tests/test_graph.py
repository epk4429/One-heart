"""온톨로지 그래프(ontology/graph.py): 공유 노드가 상품·제도를 실제로 잇는지, 원래 데이터와 수가 맞는지, API."""

import json
from collections import Counter

from ontology import graph as G
from ontology.products import load_products
from ontology.search import load as load_core
from server.app import dispatch

GR = G.build()
N, E = GR["nodes"], GR["edges"]


def _out(nid, rel):
    return {e["t"] for e in E if e["s"] == nid and e["rel"] == rel}


def _in(nid, rel):
    return {e["s"] for e in E if e["t"] == nid and e["rel"] == rel}


def test_counts_match_source_data():
    c = Counter(n["type"] for n in N.values())
    core = load_core()
    total = sum(len(load_products(cat)) for cat in ("deposit", "saving", "mortgage", "rent_loan", "credit_loan", "busi_loan"))
    assert c["product"] == total == 2070
    assert (c["need"], c["constraint"], c["ptype"], c["program"]) == (len(core["needs"]), len(core["constraints"]), len(core["types"]), 8)
    assert c["card"] == 0  # 재무 원리 카드는 없앴다(근거는 금융꿀팁 RAG)
    assert not [e for e in E if e["s"] not in N or e["t"] not in N]  # 끊어진 관계 없음


def test_every_product_has_its_branches():
    for nid, n in N.items():
        if n["type"] == "product":
            assert len(_out(nid, "inCategory")) == 1 and len(_out(nid, "offeredBy")) == 1, nid
            assert _out(nid, "source"), nid  # 모든 상품은 공시 원문에 이어진다


def test_shared_nodes_join_products_and_programs():
    homeless = "person:home:0"
    assert {"program:PG_beotimmok", "program:PG_didimdol"} <= _in(homeless, "eligibleIf")
    assert any(s.startswith("product:") for s in _in(homeless, "eligibleIf"))  # 무주택 전용 적금과 정책대출이 같은 노드
    age65 = "person:age:65-"
    assert "program:PG_basic_pension" in _in(age65, "eligibleIf")
    assert any(s.startswith("product:") for s in _in(age65, "benefitIf"))
    assert "program:PG_newborn_beotimmok" in _in("person:flag:newborn", "eligibleIf")


def test_service_bridge_and_rules():
    assert _out("need:N_leave_fund", "satisfiedBy") == {"ptype:P_installment_savings", "ptype:P_balanced_fund", "ptype:P_parking_account"}
    protected = "attr:risk=원금보장"
    assert "constraint:C_principal_protected" in _in(protected, "requiresAttr")
    assert "ptype:P_installment_savings" in _in(protected, "hasAttr") and "ptype:P_balanced_fund" not in _in(protected, "hasAttr")
    assert "category:saving" in _out("ptype:P_installment_savings", "coversCategory")
    assert "program:PG_beotimmok" in _out("ptype:PP_rent_policy_loan", "judgedBy")
    assert not any(e["rel"] == "about" for e in E) and not any(n["type"] == "chunk" for n in N.values())  # 법령 RAG는 온톨로지와 독립


def test_edges_keep_original_quotes():
    benefit_edges = [e for e in E if e["rel"] == "hasBenefit"]
    assert benefit_edges and all(e["props"].get("quote") for e in benefit_edges)
    elig = [e for e in E if e["rel"] == "eligibleIf" and e["s"].startswith("program:")]
    assert elig and all(e["props"].get("quote") for e in elig)


def test_api_and_neighbor_limits():
    st, s = dispatch("POST", "/api/graph/stats", b"{}")
    assert st == 200 and s["nodes"] == len(N)
    st, r = dispatch("POST", "/api/graph/node", json.dumps({"id": "category:saving", "limit": 5}).encode())
    g = next(x for x in r["groups"] if x["rel"] == "inCategory")
    assert st == 200 and g["total"] == len(load_products("saving")) and len(g["items"]) == 5
    assert dispatch("POST", "/api/graph/node", json.dumps({"id": "없는 노드"}).encode())[0] == 404
    st, r = dispatch("POST", "/api/graph/search", json.dumps({"q": "무주택"}).encode())
    assert st == 200 and r["results"][0]["id"] == "person:home:0"
