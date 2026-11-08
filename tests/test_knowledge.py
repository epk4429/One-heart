"""원문 저장소와 상품 노드(docs/06 3.5·5절): 원본이 그대로인지, 노드가 원본에서 그대로 다시 만들어지는지."""

import hashlib
import json
from pathlib import Path

from ontology.products import build_files, latest_sources

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "knowledge/sources/index.json").read_text(encoding="utf-8"))["sources"]
BASE = "https://finlife.fss.or.kr/finlifeapi/"


from tools.fetch_docs import ALLOWED as ALLOWED_DOCS  # noqa: E402

def test_sources_untouched_and_keyless():
    assert INDEX
    for s in INDEX:
        text = (ROOT / s["file"]).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == s["sha256"], s["source_id"]  # G2
        if s["kind"] == "api":
            assert s["url"].startswith(BASE) and "auth" not in s["url"]  # G1, 인증키 안 남김
        else:
            assert s["url"].split("/")[2] in ALLOWED_DOCS  # G1 출처 허용 목록(tools/fetch_docs.py)
        assert "auth" not in text and s["dev_only"] is True


def test_products_rebuild_from_sources():
    for rel, body in build_files().items():
        saved = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert saved == body, f"{rel}가 원본과 달라요. python tools/build_products.py로 다시 만드세요"


def test_product_nodes_match_raw():
    files = build_files()
    ids = {s["source_id"] for s in INDEX}
    for s in latest_sources():
        raw = json.loads((ROOT / s["file"]).read_text(encoding="utf-8"))
        if raw["category"] not in ("deposit", "saving"):
            continue  # 대출은 test_loans.py
        base = {f"PRD_{raw['category']}_{b['fin_co_no']}_{b['fin_prdt_cd']}": b for pg in raw["pages"] for b in pg["baseList"]}
        n_opt = sum(len(pg["optionList"]) for pg in raw["pages"])
        nodes = [p for p in files[f"ontology/products/{raw['category']}.json"]["products"] if p["source_id"] == s["source_id"]]
        assert len(nodes) == len(base) == s["counts"]["products"]
        assert sum(len(p["options"]) for p in nodes) == n_opt == s["counts"]["options"]
        for p in nodes:
            assert p["source_id"] in ids and p["conditions_status"] in ("verified", "capped", "needs_check")
            b = base[p["product_id"]]
            assert p["texts"].get("spcl_cnd") == b.get("spcl_cnd") or (not b.get("spcl_cnd") and "spcl_cnd" not in p["texts"])
            for o in p["options"]:
                assert o["term_months"] > 0 and 0 <= o["base_rate"] <= 20
                assert o["max_rate"] is None or o["max_rate"] >= o["base_rate"]


def test_category_stats_sane():
    stats = build_files()["ontology/category_stats.json"]["categories"]
    assert {"saving", "deposit"} <= set(stats)
    for c in stats.values():
        for r in c["by_term"]:
            assert 0 < r["n_products"] <= c["products"]
            for k in ("base_rate", "max_rate"):
                assert r[k]["min"] <= r[k]["median"] <= r[k]["max"]
            assert "name" not in r and "provider" not in r  # 범주 통계에는 상품 이름이 들어가지 않는다(docs/06 2.2절)


def test_product_ids_unique_across_categories():
    """저축은행은 정기예금·적금에 같은 상품 코드를 쓰기도 한다(2026-11-03 발견). 상품 ID에 범주를 넣어 겹치지 않게."""
    ids = [p["product_id"] for rel, body in build_files().items() if rel.startswith("ontology/products/") for p in body["products"]]
    assert len(ids) == len(set(ids))
