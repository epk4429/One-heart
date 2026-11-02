"""공공기관 공식 안내 페이지를 원문 저장소에 보관한다(docs/12 3·8절 ①②, 13.1절 4단계).

사용: python tools/fetch_docs.py            → 아래 DOCS 전부
      python tools/fetch_docs.py hf_reverse_mortgage

- 출처 허용 목록(G1): ALLOWED 도메인만 받는다.
- 페이지 HTML에서 글만 뽑아(스크립트·스타일 제거) knowledge/sources/docs/<source_id>.txt로 저장하고, 글의 sha256을 index.json에 남긴다.
  규칙(ontology/programs.json)의 인용(quote)은 이 글에 글자 그대로 있어야 한다(G3, tests/test_programs.py).
- 화면이 스크립트로만 열리는 사이트(고용24 등)는 이 방식으로 받을 수 없다(docs/13 기록).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge/sources/docs"
INDEX = ROOT / "knowledge/sources/index.json"
ALLOWED = {"www.hf.go.kr", "nhuf.molit.go.kr", "basicpension.mohw.go.kr"}
DOCS = {  # source_id 꼬리 → (기관, 제목, 주소)
    "hf_reverse_mortgage": ("한국주택금융공사", "주택연금이란(가입요건)", "https://www.hf.go.kr/ko/sub03/sub03_01_01_01.do"),
    "hf_reverse_mortgage_payments": ("한국주택금융공사", "주택연금 월지급금 예시", "https://www.hf.go.kr/ko/sub03/sub03_01_01_02.do"),
    "hf_bogeumjari": ("한국주택금융공사", "보금자리론", "https://www.hf.go.kr/ko/sub01/sub01_01_01.do"),
    "nhuf_didimdol": ("주택도시기금", "내집마련디딤돌대출", "https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030101.jsp"),
    "nhuf_newborn_didimdol": ("주택도시기금", "신생아 특례 디딤돌대출", "https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030801.jsp"),
    "nhuf_beotimmok": ("주택도시기금", "버팀목전세자금", "https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020101.jsp"),
    "nhuf_newborn_beotimmok": ("주택도시기금", "신생아 특례 버팀목대출", "https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05021401.jsp"),
    "nhuf_subscription": ("주택도시기금", "주택청약종합저축", "https://nhuf.molit.go.kr/FP/FP07/FP0701/FP07010101.jsp"),
    "mohw_basic_pension_target": ("보건복지부 기초연금", "기초연금 대상자 안내", "https://basicpension.mohw.go.kr/menu.es?mid=a10102010000"),
    "mohw_basic_pension_amount": ("보건복지부 기초연금", "기초연금액 산정", "https://basicpension.mohw.go.kr/menu.es?mid=a10103010000"),
}


def page_text(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"허용 목록에 없는 출처예요: {host}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ONE-Heart dev snapshot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>|</(p|div|li|tr|h\d|dt|dd|table|section)>", "\n", raw)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    t = re.sub(r"[ \t\r\f\v ]+", " ", t)
    return "\n".join(line.strip() for line in t.split("\n") if line.strip()) + "\n"


def fetch(key: str) -> dict:
    org, title, url = DOCS[key]
    text = page_text(url)
    sid = f"S_doc_{key}_{time.strftime('%Y%m%d')}"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{sid}.txt"
    path.write_text(text, encoding="utf-8")
    meta = {"source_id": sid, "kind": "document", "publisher": org, "title": title, "url": url,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M"), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "file": path.relative_to(ROOT).as_posix(), "doc_key": key, "dev_only": True}
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"sources": []}
    idx["sources"] = [s for s in idx["sources"] if s["source_id"] != sid] + [meta]
    idx["sources"].sort(key=lambda s: s["source_id"])
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


if __name__ == "__main__":
    for k in sys.argv[1:] or list(DOCS):
        m = fetch(k)
        print(f"{m['file']}  {len((ROOT / m['file']).read_text(encoding='utf-8')):,}자  {m['title']}")
