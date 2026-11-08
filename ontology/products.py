"""원문 저장소(knowledge/sources)의 공시 API 응답 → 상품 노드·범주 통계(docs/06 3.5절).

- 정형 항목(금리·기간·적립 유형·한도·가입제한 코드)은 코드가 그대로 옮긴다. 추출이 없다.
- 글 항목(우대조건·가입대상·기타 유의사항·만기 후 이자율)은 원문 그대로 texts에 두고, 조건 규칙은 ontology/conditions.py가
  따로 만든다(ontology/conditions.json). 상품 노드의 conditions_status는 그 검사 결과(verified / capped / needs_check).
- 결과는 원본에서 언제든 다시 만들 수 있다(만든 시각을 넣지 않아 같은 원본이면 같은 결과).
"""

from __future__ import annotations

import json
import re
import statistics
from functools import lru_cache
from pathlib import Path

from . import conditions, loans

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "knowledge/sources"
OUT = Path(__file__).resolve().parent

CATEGORY = {  # 범주 → 한글 이름, 범주 기본 속성(원문 근거가 아니라 범주의 일반적 성격. basis로 구분해 표시)
    "deposit": ("정기예금", {"risk": "원금보장형(예금자보호 여부는 원문 확인)", "liquidity": "만기형(중도해지 조건은 상품설명서 확인)",
                            "payment": "한 번에 맡김"}),
    "saving": ("적금", {"risk": "원금보장형(예금자보호 여부는 원문 확인)", "liquidity": "만기형(중도해지 조건은 상품설명서 확인)",
                       "payment": "매달 나눠 넣음"}),
}
JOIN_DENY = {"1": "제한없음", "2": "서민전용", "3": "일부제한"}
TEXT_FIELDS = {"join_member": "가입대상", "spcl_cnd": "우대조건", "etc_note": "기타 유의사항", "mtrt_int": "만기 후 이자율"}


def _index() -> list[dict]:
    p = SOURCES / "index.json"
    return json.loads(p.read_text(encoding="utf-8"))["sources"] if p.exists() else []


def latest_sources() -> list[dict]:
    """범주·권역마다 가장 최근 공시월의 원본만."""
    best: dict[tuple, dict] = {}
    for s in _index():
        if s.get("kind") != "api" or not s["source_id"].startswith("S_finlife_"):
            continue
        body = json.loads((ROOT / s["file"]).read_text(encoding="utf-8"))
        if body["category"] not in CATEGORY and body["category"] not in loans.LOAN:
            continue
        k = (body["category"], body["group"])
        if k not in best or s["source_id"] > best[k]["source_id"]:
            best[k] = s
    return [best[k] for k in sorted(best)]


def _option(o: dict) -> dict:
    return {"term_months": int(o["save_trm"]), "rate_type": o.get("intr_rate_type_nm"), "rsrv": o.get("rsrv_type_nm"),
            "base_rate": o.get("intr_rate"), "max_rate": o.get("intr_rate2")}


def products_from(source: dict) -> list[dict]:
    body = json.loads((ROOT / source["file"]).read_text(encoding="utf-8"))
    cat = body["category"]
    label, defaults = CATEGORY[cat]
    opts: dict[tuple, list] = {}
    for pg in body["pages"]:
        for o in pg.get("optionList") or []:
            opts.setdefault((o["fin_co_no"], o["fin_prdt_cd"]), []).append(_option(o))
    out = []
    for pg in body["pages"]:
        for b in pg.get("baseList") or []:
            key = (b["fin_co_no"], b["fin_prdt_cd"])
            out.append({
                "product_id": f"PRD_{cat}_{b['fin_co_no']}_{b['fin_prdt_cd']}",  # 저축은행은 범주가 달라도 같은 상품 코드를 쓴다
                "provider": b["kor_co_nm"], "provider_code": b["fin_co_no"], "name": b["fin_prdt_nm"],
                "category": cat, "category_label": label, "group": body["group"],
                "join_way": [w.strip() for w in (b.get("join_way") or "").split(",") if w.strip()],
                "join_deny": {"code": b.get("join_deny"), "label": JOIN_DENY.get(b.get("join_deny"), "알 수 없음")},
                "max_limit": b.get("max_limit"),
                "options": sorted(opts.get(key, []), key=lambda x: (x["term_months"], x["rsrv"] or "", x["rate_type"] or "")),
                "attributes": {k: {"value": v, "basis": "category_default"} for k, v in defaults.items()}
                | {"tax": {"value": "확인 필요", "basis": "none"}},
                "texts": {k: b.get(k) for k in TEXT_FIELDS if b.get(k)},
                "conditions_status": "raw",
                "source_id": source["source_id"], "as_of": b.get("dcls_month"), "disclosed_from": b.get("dcls_strt_day"),
                "dev_only": True,
            })
    return out


def _dist(xs: list[float]) -> dict:
    return {"min": min(xs), "median": round(statistics.median(xs), 2), "max": max(xs)}


def category_stats(products: list[dict]) -> dict:
    """범주·기간(·적립 유형)별 금리 분포. 방법 설계의 가정값과 해석 근거에 쓴다(상품 이름은 담지 않는다)."""
    out: dict = {}
    for cat in sorted({p["category"] for p in products}):
        ps = [p for p in products if p["category"] == cat]
        rows: dict[tuple, dict] = {}
        for p in ps:
            for o in p["options"]:
                if o["base_rate"] is None:
                    continue
                r = rows.setdefault((o["term_months"], o["rsrv"] or ""), {"base": [], "max": [], "products": set()})
                r["base"].append(o["base_rate"])
                r["max"].append(o["max_rate"] if o["max_rate"] is not None else o["base_rate"])
                r["products"].add(p["product_id"])
        out[cat] = {
            "label": CATEGORY[cat][0], "groups": sorted({p["group"] for p in ps}), "products": len(ps),
            "as_of": sorted({p["as_of"] for p in ps}),
            "by_term": [{"term_months": t, "rsrv": rs or None, "n_products": len(r["products"]), "n_options": len(r["base"]),
                         "base_rate": _dist(r["base"]), "max_rate": _dist(r["max"])}
                        for (t, rs), r in sorted(rows.items())],
        }
    return out


def build_files() -> dict[str, dict]:
    """원본 → {저장소 기준 경로: 내용}. 쓰지는 않는다(테스트가 저장된 파일과 비교한다)."""
    sources = latest_sources()
    products, loan_products = [], []
    for s in sources:
        body = json.loads((ROOT / s["file"]).read_text(encoding="utf-8"))
        if body["category"] in loans.LOAN:
            loan_products += loans.products_from(body, s)  # 대출: 금리 구간·한도·중도상환 수수료(ontology/loans.py)
        else:
            products += products_from(s)
    note = "개발용(dev_only). 금감원 금융상품 한눈에 공시 원본(knowledge/sources)에서 tools/build_products.py로 만든다. 직접 고치지 않는다."
    files = {}
    for cat in sorted({p["category"] for p in products}):
        ps = sorted((p for p in products if p["category"] == cat), key=lambda p: p["product_id"])
        files[f"ontology/products/{cat}.json"] = {"_note": note, "category": cat,
                                                  "sources": sorted({p["source_id"] for p in ps}), "products": ps}
    cond = conditions.build(products)  # 글 항목 → 조건 규칙(ontology/conditions.py)
    status = {r["product_id"]: r["status"] for r in cond["products"]}
    for body in files.values():
        for p in body["products"]:
            p["conditions_status"] = status[p["product_id"]]
    files["ontology/conditions.json"] = cond
    for cat in sorted({p["category"] for p in loan_products}):
        ps = sorted((p for p in loan_products if p["category"] == cat), key=lambda p: p["product_id"])
        files[f"ontology/products/{cat}.json"] = {"_note": note + " 대출 상품: terms에 한도·중도상환 수수료·우대 규칙과 검사 결과.",
                                                  "category": cat, "sources": sorted({p["source_id"] for p in ps}), "products": ps}
    files["ontology/category_stats.json"] = {
        "_note": note + " 범주·기간·적립 유형별 금리(연 %) 분포. base_rate=기본금리, max_rate=최고 우대금리.",
        "sources": [s["source_id"] for s in sources], "categories": category_stats(products), "loans": loans.stats(loan_products)}
    return files


def build_all() -> dict:
    """원본 → ontology/products/<범주>.json, category_stats.json, conditions.json. 만든 파일과 항목 수를 돌려준다."""
    out, files = {}, build_files()
    for rel, body in files.items():
        path = ROOT / rel
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        out[rel] = len(body["products"]) if "products" in body else sum(len(c["by_term"]) for c in body["categories"].values())
    out["(조건 규칙 검사)"] = files["ontology/conditions.json"]["summary"]
    for cat in loans.LOAN:
        ps = files.get(f"ontology/products/{cat}.json", {}).get("products", [])
        out[f"({loans.LOAN[cat]} 검사)"] = {s: sum(p["terms"]["status"] == s for p in ps) for s in ("verified", "needs_check")}
    return out


def load_products(category: str) -> list[dict]:
    p = OUT / "products" / f"{category}.json"
    return json.loads(p.read_text(encoding="utf-8"))["products"] if p.exists() else []


def rate_benchmark(category: str = "deposit", term_months: int = 12, group: str = "020000") -> dict:
    """미래 계산 가정값의 근거: 한 권역·기간의 상품별 기본금리 중앙값(세전, 우대 제외).
    상품마다 그 기간 옵션의 평균을 한 표로 세서 옵션이 많은 상품이 끌고 가지 않게 한다."""
    per, srcs, as_of = [], set(), set()
    for p in load_products(category):
        xs = [o["base_rate"] for o in p["options"] if o["term_months"] == term_months and o["base_rate"] is not None]
        if p["group"] == group and xs:
            per.append(statistics.mean(xs))
            srcs.add(p["source_id"])
            as_of.add(p["as_of"])
    if not per:
        return {}
    return {"category": category, "term_months": term_months, "group": group, "median": round(statistics.median(per), 2),
            "n_products": len(per), "as_of": sorted(as_of), "source_ids": sorted(srcs)}


@lru_cache(maxsize=1)
def provider_names() -> frozenset[str]:
    """공시에 나온 금융회사 이름 전부(앞 단계 글에 회사 이름이 나오는지 검사, G12)."""
    return frozenset(p["provider"] for cat in {*CATEGORY, *loans.LOAN} for p in load_products(cat))


# ---------- G12: 앞 단계 글에 실제 상품 이름이 나오는지 ----------
# 공시 상품 이름에는 "정기예금", "신용대출"처럼 흔한 말이 많다. 그런 이름까지 막으면 AI가 쉬운 설명도 못 쓴다.
# 그래서 (1) 한 금융회사에만 있는 이름이고 (2) 흔한 금융 낱말·괄호·기호를 빼고도 두 글자 이상 남고(브랜드 부분)
# (3) 띄어쓰기를 뺀 길이가 5글자 이상인 이름만 '상품 이름'으로 본다(2026-11-08, 임의결정 31).
GENERIC_WORDS = sorted({
    "정기예금", "정기적금", "예금", "적금", "대출", "담보", "론", "자금", "일반", "기타", "개인", "사업자", "기업", "가계",
    "전세", "전월세", "보증금", "보증", "주택", "아파트", "부동산", "모기지", "중도금", "잔금", "경락", "이주비", "신용",
    "회전식", "회전", "자유", "적립식", "거치식", "정액", "정기", "입출금", "통장", "종합", "변동금리", "고정금리", "변동",
    "고정", "금리", "상품", "운전", "시설", "오토", "신차", "중고차", "중고", "할부", "리스", "카드", "장기", "단기",
    "비대면", "인터넷뱅킹", "스마트뱅킹", "인터넷", "스마트", "뱅킹", "모바일", "앱", "전용", "직장인", "청년", "서민",
    "예적금", "저축", "목돈", "만기", "특판", "특별", "우대", "플러스", "프리미엄", "신규", "대환", "협약", "이차보전",
    "지원", "소득", "연금", "노후", "자영업자", "월수", "일시", "분할", "균등", "원금", "이자", "상환",
}, key=len, reverse=True)


def _brand_part(name: str) -> str:
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", name)
    t = re.sub(r"[\s\-_+.,·/!~'’]", "", t)
    t = re.sub(r"^[A-Za-z](?=[가-힣])", "", t)       # e정기예금, m적금 같은 앞 글자
    t = re.sub(r"(\d+|Ⅱ|Ⅲ|II|III)$", "", t)          # 아파트론1, 임차론Ⅱ 같은 뒤 번호
    for g in GENERIC_WORDS:
        t = t.replace(g, "")
    return t


@lru_cache(maxsize=1)
def product_brand_names() -> frozenset[str]:
    """앞 단계 글에 나오면 안 되는 실제 상품 이름(흔한 말로 된 이름은 뺀다)."""
    by: dict[str, set[str]] = {}
    for cat in {*CATEGORY, *loans.LOAN}:
        for p in load_products(cat):
            by.setdefault(p["name"].strip(), set()).add(p["provider"])
    return frozenset(n for n, ps in by.items()
                     if len(ps) == 1 and len(re.sub(r"\s", "", n)) >= 5 and len(_brand_part(n)) >= 2)


@lru_cache(maxsize=1)
def stage_banned_names() -> frozenset[str]:
    """G12: 조건 비교 화면 앞 단계(역할 1a·4·5·6·7)의 글에 나오면 안 되는 이름 = 금융회사 이름 + 실제 상품 이름."""
    return provider_names() | product_brand_names()


def banned_names_in(text: str) -> list[str]:
    """글 속에 나온 금지 이름(긴 이름이 짧은 이름을 품으면 긴 것만)."""
    hits = sorted((n for n in stage_banned_names() if n and n in (text or "")), key=len, reverse=True)
    out: list[str] = []
    for h in hits:
        if not any(h in o for o in out):
            out.append(h)
    return sorted(out)
