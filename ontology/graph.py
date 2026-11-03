"""온톨로지 그래프(공유 노드): 흩어진 온톨로지 데이터를 노드·관계 하나의 그래프로 묶는다(2026-11-04 형님 요청).

실제 상품 2,070개가 하나하나 노드이고, 상품이 가진 항목(금융회사·범주·가입 방법·우대 종류·사람 조건·원문)은
**여러 상품·제도가 함께 가리키는 공유 노드**가 된다. 예: "만 65세 이상" 노드 하나에 그 우대를 가진 적금들과 기초연금이 함께 이어진다.
그 위에 서비스의 다리(약속이 들어오는 필요 → 상품 유형 → 범주·제도)와 재무 원리 카드·RAG 조각이 붙는다.

판정·비교 계산은 지금처럼 fit.py·programs.py가 한다. 이 그래프는 같은 데이터를 '연결'로 보여 주고 찾아보기 위한 것이다
(새 사실을 만들지 않는다: 모든 노드·관계는 vocab·product_types·rules·programs·conditions·products·cards·RAG 조각에서 그대로 나온다).

사용: python -m ontology.graph   → 노드·관계 수 요약
API:  /api/graph/stats, /api/graph/node, /api/graph/search (server/app.py), 화면 web/graph.html
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from . import loans
from .products import CATEGORY, load_products
from .search import load as load_core

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

TYPES = {  # 노드 종류 → 화면 이름
    "need": "필요", "constraint": "제약", "ptype": "상품 유형", "attr": "유형 속성", "category": "상품 범주",
    "product": "실제 상품", "provider": "금융회사", "channel": "가입 방법", "benefit": "우대 종류",
    "person": "사람·가족 조건", "check": "확인 필요 조건", "program": "공적 제도", "card": "재무 원리 카드",
    "source": "원문", "chunk": "RAG 조각",
}
RELS = {  # 관계 → 화면 이름(나가는 쪽에서 읽는 말)
    "satisfiedBy": "채우는 상품 유형", "requiresAttr": "통과하려면 필요한 속성", "hasAttr": "속성",
    "coversCategory": "실제 상품 범주", "inCategory": "범주", "judgedBy": "판정하는 제도", "offeredBy": "금융회사",
    "joinVia": "가입 방법", "hasBenefit": "우대 종류", "benefitIf": "사람 조건 우대", "eligibleIf": "가입·자격 조건",
    "checkNeeded": "확인 필요 조건", "source": "원문", "supports": "근거가 되는 필요", "about": "다루는 대상",
}
ATTR_FIELDS = ("risk", "liquidity", "term")  # 제약 규칙이 보는 속성(rules.json)과 같은 칸
FLAG_LABEL = {"single_parent": "한부모", "disabled": "장애", "low_income": "기초생활·차상위", "pregnant": "임신·출산 예정",
              "newborn": "2년 안 출산·출생", "employee": "근로자(직장인)", "self_employed": "자영업·개인사업자"}
CHECK_TO_FLAG = {"한부모": "single_parent", "장애": "disabled", "기초생활": "low_income"}


def _won(v: float) -> str:
    """만원 → 읽기 쉬운 금액."""
    if v >= 10000:
        return f"{v / 10000:g}억원"
    return f"{v / 1000:g}천만원" if v % 1000 == 0 else f"{v:,.0f}만원"


def _age_key(lo: int | None, hi: int | None) -> tuple[str, str]:
    if lo is not None and hi is not None:
        return f"person:age:{lo}-{hi}", f"만 {lo}~{hi}세"
    if lo is not None:
        return f"person:age:{lo}-", f"만 {lo}세 이상"
    return f"person:age:-{hi}", f"만 {hi}세 이하"


def _age_from_cond(op: str, value: int) -> tuple[str, str]:
    return {">=": _age_key(value, None), ">": _age_key(value + 1, None),
            "<=": _age_key(None, value), "<": _age_key(None, value - 1)}[op]


class _G:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._seen: set[tuple] = set()

    def node(self, nid: str, ntype: str, label: str, **props) -> str:
        if nid not in self.nodes:
            label = " ".join(str(label).split())  # 공시 상품명 속 줄바꿈 등
            self.nodes[nid] = {"id": nid, "type": ntype, "label": label, "props": {k: v for k, v in props.items() if v not in (None, "", [])}}
        return nid

    def edge(self, s: str, rel: str, t: str, **props) -> None:
        key = (s, rel, t, json.dumps(props, ensure_ascii=False, sort_keys=True))
        if key in self._seen:
            return
        self._seen.add(key)
        self.edges.append({"s": s, "rel": rel, "t": t, "props": {k: v for k, v in props.items() if v not in (None, "", [])}})


def _sources() -> dict[str, dict]:
    idx = json.loads((ROOT / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]
    return {s["source_id"]: s for s in idx}


@lru_cache(maxsize=1)
def build() -> dict:
    g = _G()
    core = load_core()
    srcs = _sources()
    latest_doc = {}
    for sid, s in sorted(srcs.items()):
        if s.get("doc_key"):
            latest_doc[s["doc_key"]] = sid

    def src(sid: str | None) -> str | None:
        if not sid or sid not in srcs:
            return None
        s = srcs[sid]
        return g.node(f"source:{sid}", "source", s.get("title") or sid, publisher=s.get("publisher"), url=s.get("url"),
                      fetched_at=s.get("fetched_at"), effective_date=s.get("effective_date"))

    # 1) 서비스의 다리: 필요 → 상품 유형 → 속성·범주·제도, 제약 → 속성
    for n in core["needs"].values():
        g.node(f"need:{n['id']}", "need", n["label"], self_route=n.get("self"), only_if=(n.get("requires") or {}).get("why"))
    for c in core["constraints"].values():
        g.node(f"constraint:{c['id']}", "constraint", c["label"])
    for t in core["types"].values():
        tid = g.node(f"ptype:{t['id']}", "ptype", t["label"], kind=t["kind"], route=t.get("data"), summary=t.get("summary"),
                     data_note=t.get("data_note"))
        for f in ATTR_FIELDS:
            v = t["attributes"].get(f)
            if v and v != "해당 없음":
                g.edge(tid, "hasAttr", g.node(f"attr:{f}={v}", "attr", f"{_ATTR_NAME[f]}: {v}"))
        for feat in t.get("features") or []:
            g.edge(tid, "hasAttr", g.node(f"attr:features={feat}", "attr", f"기능: {feat}"))
        g.edge(tid, "hasAttr", g.node(f"attr:requires_home_sale={str(t['requires_home_sale']).lower()}", "attr",
                                      "집을 팔아야 함" if t["requires_home_sale"] else "집을 팔지 않아도 됨"))
        g.edge(tid, "hasAttr", g.node(f"attr:kind={t['kind']}", "attr", f"종류: {_KIND_NAME.get(t['kind'], t['kind'])}"))
        if t.get("real_category"):
            cat = t["real_category"]
            g.edge(tid, "coversCategory", g.node(f"category:{cat}", "category", _cat_label(cat)))
        for pg in t.get("programs") or []:
            g.edge(tid, "judgedBy", f"program:{pg}")
    for n in core["needs"].values():
        for tid in n["satisfied_by"]:
            g.edge(f"need:{n['id']}", "satisfiedBy", f"ptype:{tid}")
    for cid, rule in core["rules"].items():
        vals = rule.get("in") or ([rule["equals"]] if "equals" in rule else [rule["contains"]] if "contains" in rule else [])
        for v in vals:
            f = rule["field"]
            key = f"attr:{f}={str(v).lower() if isinstance(v, bool) else v}"
            label = (("집을 팔아야 함" if v else "집을 팔지 않아도 됨") if f == "requires_home_sale" else
                     f"기능: {v}" if f == "features" else f"종류: {_KIND_NAME.get(v, v)}" if f == "kind" else f"{_ATTR_NAME.get(f, f)}: {v}")
            g.edge(f"constraint:{cid}", "requiresAttr", g.node(key, "attr", label), reason_if_not=rule["reason"])

    # 2) 공적 제도와 자격 조건(공유 노드)
    programs = json.loads((HERE / "programs.json").read_text(encoding="utf-8"))["programs"]
    for p in programs:
        pid = g.node(f"program:{p['id']}", "program", p["label"], publisher=p.get("publisher"), kind=p.get("kind"),
                     summary=p.get("summary"))
        s = src(latest_doc.get(p.get("source")))
        if s:
            g.edge(pid, "source", s)
        for e in p["eligibility"]:
            target, who = _program_cond(g, e)
            if target:
                g.edge(pid, "eligibleIf", target, who=who, quote=e.get("quote"), rule=e.get("label"))
        for u in p.get("unmodeled") or []:
            g.edge(pid, "checkNeeded", g.node(f"check:{u['label']}", "check", u["label"]), quote=u.get("quote"))

    # 3) 실제 상품과 항목(공유 노드)
    cond = {r["product_id"]: r for r in json.loads((HERE / "conditions.json").read_text(encoding="utf-8"))["products"]}
    from .conditions import TAG
    for cat in list(CATEGORY) + list(loans.LOAN):
        for pr in load_products(cat):
            rates = [o.get("base_rate") for o in pr.get("options") or [] if o.get("base_rate") is not None]
            r = cond.get(pr["product_id"])
            t = pr.get("terms") or {}
            lim, pre = t.get("limit") or {}, t.get("prepay") or {}
            pid = g.node(f"product:{pr['product_id']}", "product", pr["name"], provider=pr["provider"],
                         category=pr.get("category_label"), as_of=pr.get("as_of"),
                         base_rate_range=f"{min(rates):g}~{max(rates):g}%" if rates else None,
                         terms=sorted({o["term_months"] for o in pr.get("options") or [] if o.get("term_months")}) or None,
                         monthly_max=f"월 {_won(r['limits']['monthly_max_manwon'])}" if r and (r.get("limits") or {}).get("monthly_max_manwon") else None,
                         deposit_max=_won(pr["max_limit"] / 10000) if pr.get("max_limit") and cat == "deposit" else None,  # 적금의 max_limit은 월 한도라 위 monthly_max로
                         loan_limit=(f"{'집값' if lim.get('ratio_of') == 'home' else '보증금'}의 {lim['ratio_pct']:g}%" if lim.get("ratio_pct") else "")
                                    + (f" (최대 {_won(lim['max_manwon'])})" if lim.get("max_manwon") else "") or None,
                         prepay_fee=(f"고정 {pre['fixed_pct']:g}% / 변동 {pre['variable_pct']:g}%" if pre.get("fixed_pct") is not None and pre.get("variable_pct") is not None
                                     else "없음" if pre.get("none") else None),
                         terms_status=t.get("status"),
                         benefit_status=r.get("benefit_status") if r else None)
            g.edge(pid, "inCategory", g.node(f"category:{cat}", "category", _cat_label(cat)))
            g.edge(pid, "offeredBy", g.node(f"provider:{pr['provider']}", "provider", pr["provider"]))
            for w in pr.get("join_way") or []:
                g.edge(pid, "joinVia", g.node(f"channel:{w}", "channel", w))
            s = src(pr.get("source_id"))
            if s:
                g.edge(pid, "source", s)
            if not r:
                continue
            for b in r["benefits"]:
                if b.get("role") == "group" or b["tag"] == "other":
                    continue
                meta = TAG.get(b["tag"], {})
                bid = g.node(f"benefit:{b['tag']}", "benefit", f"우대: {meta.get('label', b['tag'])}",
                             kind={"action": "하면 받음", "attribute": "사람 조건", "relation": "거래 관계"}.get(meta.get("kind"), ""))
                g.edge(pid, "hasBenefit", bid, add_pp=b.get("add_pp"), quote=b["quote"])
                if b.get("who"):
                    for t, label in _who_nodes(b["who"]):
                        g.edge(pid, "benefitIf", g.node(t, "person", label), add_pp=b.get("add_pp"), who="계좌 주인", quote=b["who"]["quote"])
            for c in r["eligibility"]["conditions"]:
                if c["var"] == "age":
                    key, label = _age_from_cond(c["op"], int(c["value"]))
                    g.edge(pid, "eligibleIf", g.node(key, "person", label), who="계좌 주인", quote=c.get("quote"))
            for u in r["eligibility"]["unknown"]:
                if u.get("who"):
                    for t, label in _who_nodes(u["who"]):
                        g.edge(pid, "eligibleIf", g.node(t, "person", label), quote=u["who"]["quote"])
                elif u["var"] == "무주택":
                    g.edge(pid, "eligibleIf", g.node("person:home:0", "person", "무주택"), quote=u.get("quote"))
                elif u["var"] in CHECK_TO_FLAG:
                    f = CHECK_TO_FLAG[u["var"]]
                    g.edge(pid, "eligibleIf", g.node(f"person:flag:{f}", "person", FLAG_LABEL[f]), quote=u.get("quote"))
                else:
                    g.edge(pid, "checkNeeded", g.node(f"check:{u['var']}", "check", f"가입대상 확인: {u['var']}"), quote=u.get("quote"))

    # 4) 재무 원리 카드 → 필요, 원문
    for c in json.loads((HERE / "cards.json").read_text(encoding="utf-8"))["cards"]:
        cid = g.node(f"card:{c['id']}", "card", c["title"], text=c["text"], published=c["published"])
        for n in c["needs"]:
            g.edge(cid, "supports", f"need:{n}")
        for q in c["quotes"]:
            s = src(latest_doc.get(q["doc_key"]))
            if s:
                g.edge(cid, "source", s, quote=q["quote"])

    # 5) RAG 조각 → 다루는 제도·상품 유형, 원문
    path = ROOT / "knowledge/rag/chunks.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ch = json.loads(line)
            kid = g.node(f"chunk:{ch['chunk_id']}", "chunk", ch.get("article") or ch.get("title") or ch["chunk_id"],
                         text=ch["text"][:300])
            for n in ch["nodes"]:
                g.edge(kid, "about", f"program:{n}" if n.startswith("PG_") else f"ptype:{n}")
            s = src(ch.get("source_id"))
            if s:
                g.edge(kid, "source", s)

    dangling = [e for e in g.edges if e["s"] not in g.nodes or e["t"] not in g.nodes]
    assert not dangling, dangling[:3]
    return {"nodes": g.nodes, "edges": g.edges}


_ATTR_NAME = {"risk": "위험도", "liquidity": "꺼내 쓰기", "term": "기간"}
_KIND_NAME = {"product": "상품", "policy": "공적 제도", "action": "가족의 행동", "consult": "상담 연결"}


def _cat_label(cat: str) -> str:
    return CATEGORY[cat][0] if cat in CATEGORY else loans.LOAN[cat]


def _who_nodes(who: dict) -> list[tuple[str, str]]:
    """conditions.person_rule 결과 → 공유 사람 조건 노드들."""
    if who["type"] == "age":
        return [_age_key(who.get("min"), who.get("max"))]
    if who["type"] == "kids":
        return [(f"person:kids:{who['min']}+", f"18세 이하 자녀 {who['min']}명 이상")]
    return [(f"person:flag:{f}", FLAG_LABEL[f]) for f in who.get("flags", [])]


def _program_cond(g: _G, e: dict) -> tuple[str | None, str | None]:
    """제도 자격 조건 → 공유 노드(상품의 같은 조건과 같은 노드가 되게 한다)."""
    var, op, v = e["var"], e["op"], e["value"]
    if var == "always":
        return None, None
    if var == "home_count":
        key, label = {("==", 0): ("person:home:0", "무주택"), (">=", 1): ("person:home:1+", "집 1채 이상"),
                      ("<=", 1): ("person:home:-1", "집 1채 이하")}[(op, v)]
        return g.node(key, "person", label), "세대"
    if var in ("owner_age", "eldest_age"):
        key, label = _age_from_cond(op, int(v))
        return g.node(key, "person", label), "집 주인" if var == "owner_age" else "가족 중 가장 나이 많은 사람"
    if var == "newborn_2y":
        return g.node("person:flag:newborn", "person", FLAG_LABEL["newborn"]), "가족"
    names = {"household_income_year": ("부부합산 연소득", True), "net_assets": ("순자산", True),
             "home_value_gongsi": ("집 공시가격", True), "income_recognition_month": ("소득인정액(월)", True)}
    name, money = names.get(var, (var, False))
    label = f"{name} {_won(v) if money else v} {'이하' if op == '<=' else '이상' if op == '>=' else op}"
    return g.node(f"person:{var}{op}{v}", "person", label), "세대" if var != "income_recognition_month" else "노인 부부"


# ---------- 찾아보기(API·화면) ----------
def stats() -> dict:
    gr = build()
    return {"nodes": len(gr["nodes"]), "edges": len(gr["edges"]),
            "by_type": {TYPES[k]: v for k, v in Counter(n["type"] for n in gr["nodes"].values()).most_common()},
            "by_rel": {RELS[k]: v for k, v in Counter(e["rel"] for e in gr["edges"]).most_common()},
            "types": TYPES, "rels": RELS}


@lru_cache(maxsize=1)
def _adjacency() -> dict[str, list[tuple[str, dict]]]:
    adj: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for e in build()["edges"]:
        adj[e["s"]].append(("out", e))
        adj[e["t"]].append(("in", e))
    return adj


def neighbors(node_id: str, limit: int = 30) -> dict | None:
    """노드 하나와 이웃. (관계, 방향, 이웃 종류)마다 limit개까지만 주고 전체 수를 함께 준다(범주처럼 이웃이 수백 개인 노드)."""
    gr = build()
    if node_id not in gr["nodes"]:
        return None
    groups: dict[tuple, list] = defaultdict(list)
    for d, e in _adjacency().get(node_id, []):
        other = e["t"] if d == "out" else e["s"]
        groups[(e["rel"], d, gr["nodes"][other]["type"])].append((gr["nodes"][other], e["props"]))
    out = []
    for (rel, d, ntype), items in sorted(groups.items(), key=lambda kv: (-len(kv[1]) if kv[0][1] == "out" else 0, kv[0])):
        items.sort(key=lambda x: x[0]["label"])
        out.append({"rel": rel, "rel_label": RELS[rel], "dir": d, "type": ntype, "type_label": TYPES[ntype], "total": len(items),
                    "items": [{"node": {k: n[k] for k in ("id", "type", "label")}, "edge": p} for n, p in items[:limit]]})
    return {"node": gr["nodes"][node_id], "type_label": TYPES[gr["nodes"][node_id]["type"]], "groups": out}


def search(q: str, limit: int = 20) -> list[dict]:
    """이름에 글자가 들어간 노드(공유 노드·서비스 노드를 실제 상품보다 먼저)."""
    q = (q or "").strip()
    if not q:
        return []
    order = {t: i for i, t in enumerate(["need", "constraint", "ptype", "program", "person", "benefit", "category", "provider",
                                         "card", "attr", "channel", "check", "product", "source", "chunk"])}
    hits = [n for n in build()["nodes"].values() if q in n["label"] or q == n["id"]]
    hits.sort(key=lambda n: (order[n["type"]], len(n["label"])))
    deg = _adjacency()
    return [{"id": n["id"], "type": n["type"], "type_label": TYPES[n["type"]], "label": n["label"], "degree": len(deg.get(n["id"], []))}
            for n in hits[:limit]]


if __name__ == "__main__":
    print(json.dumps(stats(), ensure_ascii=False, indent=1))
