"""한국부동산원 「전국주택가격동향조사」 월간 통계표에서 지역·주택 종류별 평균·중위 매매가격·전세가격을 뽑는다.

공동 목표 설정 2단계 '통계 기준'(지역·집 종류별 집값)에 쓴다(docs/08 4절).
- 원본: e-나라지표(index.go.kr) 주택매매가격 동향(idxCd=1240) 첨부 '통계표.xlsx'. 로그인 없이 받을 수 있다(2026-11-08 확인).
- 원본(약 38MB)은 저장소에 넣지 않고 knowledge/raw/에 둔다(git 제외). 스냅샷 JSON에 원본의 sha256을 적어 대조할 수 있게 한다.
- '가격' 시트(원자료)를 읽는다. 단위는 천원(통계표 27~30 '단위 : 천원'). 스냅샷에는 만원으로 바꿔 넣는다.

쓰는 법:
  python tools/fetch_reb_prices.py --seq 17768 --label 202609          # 내려받기 + 뽑기
  python tools/fetch_reb_prices.py --file 받은파일.xlsx --label 202609  # 이미 받은 파일에서 뽑기
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import urllib.request
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "knowledge" / "raw"
OUT = ROOT / "knowledge" / "sources"
PAGE = "https://www.index.go.kr/unify/idx-info.do?idxCd=1240"
URL = "https://www.index.go.kr/unity/potal/FileDown.do?seq={seq}&id=1240&div=1"
STATS = {"중위매매가": "median_sale", "평균매매가": "mean_sale", "중위전세가": "median_jeonse", "평균전세가": "mean_jeonse"}
TYPES = {"00.종합": "all", "01.아파트": "apt", "02.연립다세대": "row", "03.단독주택": "detached"}


def _clean(v) -> str:
    return "" if v is None else str(v).strip()


def extract(xlsx: Path) -> dict:
    import openpyxl
    warnings.filterwarnings("ignore")
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = list(wb["가격"].iter_rows(values_only=True))
    hdr = rows[0]
    last = max(i for i, h in enumerate(hdr) if isinstance(h, dt.datetime))
    month = hdr[last].strftime("%Y-%m")
    regions: dict[str, dict] = {}
    for r in rows[1:]:
        stat, typ = _clean(r[8]), _clean(r[6])
        if stat not in STATS or typ not in TYPES or r[last] is None:
            continue
        code = _clean(r[5])
        names = [_clean(x) for x in r[:5]]
        name = " ".join(n.split(".", 1)[-1] for n in names[1:] if n) or names[0].split(".", 1)[-1]
        reg = regions.setdefault(code, {"code": code, "name": name, "group": names[0], "sido": names[1] or None,
                                        "level": "sido" if names[1] and not any(names[2:]) else
                                                 "group" if not names[1] else "sub", "values": {}})
        reg["values"].setdefault(TYPES[typ], {})[STATS[stat]] = round(float(r[last]) / 10, 1)  # 천원 → 만원
    return {"month": month, "regions": list(regions.values())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", help="e-나라지표 첨부 번호(통계표.xlsx)")
    ap.add_argument("--file", help="이미 받은 통계표.xlsx")
    ap.add_argument("--label", required=True, help="통계 기준월, 예: 202609")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    raw = RAW / f"reb_house_price_{a.label}.xlsx"
    if a.file:
        shutil.copyfile(a.file, raw)
        url = None
    else:
        url = URL.format(seq=a.seq)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": PAGE})
        with urllib.request.urlopen(req, timeout=120) as resp, open(raw, "wb") as f:
            shutil.copyfileobj(resp, f)
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    data = extract(raw)
    snap = {
        "source_id": f"S_reb_house_price_{a.label}",
        "title": "한국부동산원 「전국주택가격동향조사」 지역·주택 종류별 평균·중위 매매가격·전세가격",
        "publisher": "한국부동산원(국가승인통계 제304004호)", "page": PAGE, "download_url": url,
        "sheet": "가격", "month": data["month"], "unit": "만원(원본 천원을 10으로 나눔)",
        "raw_file": raw.name, "raw_sha256": sha, "fetched": dt.date.today().isoformat(),
        "note": "평균·중위가격은 표본 기준이라 표본 교체 때 불연속이 있을 수 있다(원본 개요). 연립·단독은 시도 단위까지만 공표.",
        "regions": data["regions"],
    }
    out = OUT / f"S_reb_house_price_{a.label}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {data['month']}, 지역 {len(data['regions'])}곳")


if __name__ == "__main__":
    main()
