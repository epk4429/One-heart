"""금감원 "금융상품 한눈에" 오픈 API에서 상품 공시를 받아 원문 저장소에 그대로 저장한다(docs/06 3.5절).

사용: python tools/fetch_finlife.py --all                 → 공시 API 전 범주 × 전 권역(상품이 없는 권역은 건너뜀)
      python tools/fetch_finlife.py --cat saving --grp 020000 030300   (030300 = 저축은행)

- 인증키는 .env의 FINLIFE_API_KEY. 키는 파일·화면 어디에도 남기지 않는다.
- 응답은 손대지 않고 페이지별로 저장한다: knowledge/sources/S_finlife_<범주>_<권역>_<공시월>.json
- 저장한 원본은 개발용(dev_only)이다. 공개 화면에 써도 되는지는 아직 확인 전(docs/07 부록 B L12).
- 개인 인증키는 하루 호출 횟수 제한이 있다. 변환은 저장한 원본으로 하고(tools/build_products.py), 여기서는 받기만 한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm.providers import load_env  # noqa: E402

BASE = "https://finlife.fss.or.kr/finlifeapi/"  # 출처 허용 목록(G1): 이 주소 말고는 부르지 않는다
SOURCES = ROOT / "knowledge/sources"
CATEGORIES = {  # 범주 → (서비스 이름, 한글 이름). 서비스 이름은 각 API 안내 페이지의 테스트 양식에서 확인(2026-11-03)
    "deposit": ("depositProductsSearch", "정기예금"),
    "saving": ("savingProductsSearch", "적금"),
    "mortgage": ("mortgageLoanProductsSearch", "주택담보대출"),
    "rent_loan": ("rentHouseLoanProductsSearch", "전세자금대출"),
    "credit_loan": ("creditLoanProductsSearch", "개인신용대출"),
    "busi_loan": ("busiLoanProductsSearch", "개인사업자대출"),
    "company": ("companySearch", "금융회사 개요"),
    # 연금저축(annuitySavingProductsSearch)은 2026-11-03 응답이 비정상이라 --all에서 뺐다: 보험 권역은 46건이라면서
    # 4건만 오고 그마저 대출 상품(연금 항목 없음), 금융투자 권역은 297건이라면서 모든 쪽이 빈 목록. 다른 공식 출처가 필요하다.
    "annuity": ("annuitySavingProductsSearch", "연금저축"),
}
ALL = ["deposit", "saving", "mortgage", "rent_loan", "credit_loan", "busi_loan", "company"]
SANITY = {"annuity": "pnsn_kind"}  # 이 범주는 응답 기본정보에 이 항목이 있어야 정상
GROUPS = {"020000": "은행", "030200": "여신전문", "030300": "저축은행", "050000": "보험", "060000": "금융투자"}


class FetchError(Exception):
    pass


def _get(service: str, key: str, grp: str, page: int) -> dict:
    q = urllib.parse.urlencode({"auth": key, "topFinGrpNo": grp, "pageNo": str(page)})
    try:
        with urllib.request.urlopen(f"{BASE}{service}.json?{q}", timeout=30) as r:
            res = json.loads(r.read().decode("utf-8"))["result"]
    except Exception as e:  # noqa: BLE001 - 키가 섞인 주소가 메시지에 남지 않게
        raise FetchError(f"{service} {grp} {page}쪽: {type(e).__name__}") from None
    if res.get("err_cd") != "000":
        raise FetchError(f"{service} {grp}: {res.get('err_cd')} {res.get('err_msg')}")
    return res


def fetch(cat: str, grp: str, key: str) -> Path | None:
    service, label = CATEGORIES[cat]
    pages = [_get(service, key, grp, 1)]
    if not int(pages[0].get("total_count") or 0):
        return None  # 이 권역에는 이 범주 상품이 없다
    for p in range(2, int(pages[0].get("max_page_no") or 1) + 1):
        time.sleep(0.3)
        pages.append(_get(service, key, grp, p))
    must = SANITY.get(cat)
    if must and not all(must in b for pg in pages for b in pg.get("baseList") or []) or             sum(len(pg.get("baseList") or []) for pg in pages) == 0:
        raise FetchError(f"{service} {grp}: 응답이 비정상이에요(총 {pages[0].get('total_count')}건이라는데 목록이 비었거나 다른 상품)")
    months = sorted({b.get("dcls_month") for pg in pages for b in pg.get("baseList") or [] if b.get("dcls_month")})
    month = months[-1] if months else time.strftime("%Y%m")
    source_id = f"S_finlife_{cat}_{grp}_{month}"
    body = {"service": service, "category": cat, "group": grp, "pages": pages}
    text = json.dumps(body, ensure_ascii=False, indent=1)
    assert key not in text
    SOURCES.mkdir(parents=True, exist_ok=True)
    path = SOURCES / f"{source_id}.json"
    path.write_text(text, encoding="utf-8")
    meta = {
        "source_id": source_id, "kind": "api", "publisher": "금융감독원 금융상품통합비교공시(금융상품 한눈에)",
        "url": f"{BASE}{service}.json?topFinGrpNo={grp}", "title": f"{label} · {GROUPS.get(grp, grp)}",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M"), "effective_date": f"공시월 {', '.join(months)}",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "file": path.relative_to(ROOT).as_posix(),
        "counts": {"products": sum(len(pg.get("baseList") or []) for pg in pages),
                   "options": sum(len(pg.get("optionList") or []) for pg in pages)},
        "dev_only": True,
    }
    idx_path = SOURCES / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {"sources": []}
    idx["sources"] = [s for s in idx["sources"] if s["source_id"] != source_id] + [meta]
    idx["sources"].sort(key=lambda s: s["source_id"])
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="전 범주(연금저축 제외) × 전 권역")
    ap.add_argument("--cat", nargs="+", default=["saving", "deposit"], choices=sorted(CATEGORIES))
    ap.add_argument("--grp", nargs="+", default=["020000"], choices=sorted(GROUPS))
    a = ap.parse_args()
    if a.all:
        a.cat, a.grp = ALL, sorted(GROUPS)
    load_env()
    key = os.environ.get("FINLIFE_API_KEY", "").strip()
    if not key:
        sys.exit(".env에 FINLIFE_API_KEY가 없어요")
    for cat in a.cat:
        for grp in a.grp:
            try:
                p = fetch(cat, grp, key)
            except FetchError as e:
                print(f"받지 못했어요: {e}")
                continue
            if p is None:
                print(f"{CATEGORIES[cat][1]} · {GROUPS[grp]}: 상품 없음")
                continue
            meta = next(s for s in json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))["sources"]
                        if s["file"] == p.relative_to(ROOT).as_posix())
            print(f"{p.relative_to(ROOT)}  상품 {meta['counts']['products']} · 옵션 {meta['counts']['options']} · {meta['effective_date']}")


if __name__ == "__main__":
    main()
