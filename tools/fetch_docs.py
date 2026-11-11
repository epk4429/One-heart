"""공공기관 공식 안내 페이지를 원문 저장소에 보관한다(docs/06 3.5·3.7절).

사용: python tools/fetch_docs.py            → 아래 DOCS·LAWS·FSS_TIPS 전부
      python tools/fetch_docs.py hf_reverse_mortgage

- 출처 허용 목록(G1): ALLOWED 도메인만 받는다.
- 페이지 HTML에서 글만 뽑아(스크립트·스타일 제거) knowledge/sources/docs/<source_id>.txt로 저장하고, 글의 sha256을 index.json에 남긴다.
  규칙(ontology/programs.json)의 인용(quote)은 이 글에 글자 그대로 있어야 한다(G3, tests/test_programs.py).
- 화면이 스크립트로만 열리는 사이트(고용24 등)는 이 방식으로 받을 수 없다(docs/06 부록 A).
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
ALLOWED = {"www.hf.go.kr", "nhuf.molit.go.kr", "basicpension.mohw.go.kr", "www.law.go.kr", "www.fss.or.kr", "www.nhis.or.kr"}
FSS_TIPS = {  # source_id 꼬리 → (제목, 게시글 주소). 금융감독원 '금융꿀팁 200선'. 본문은 첨부 한글(HWP) 파일이다. 재무 원리 카드(ontology/cards.json)의 출처
    "fss_tip_001": ("금융꿀팁 200선 (1) 현명한 신용관리요령", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34628&menuNo=200498"),
    "fss_tip_026": ("금융꿀팁 200선 (26) 은행거래 100% 활용법(2): 예적금 수익률 높이기", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34653&menuNo=200498"),
    "fss_tip_030": ("금융꿀팁 200선 (30) 사회초년생을 위한 금융꿀팁", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34657&menuNo=200498"),
    "fss_tip_035": ("금융꿀팁 200선 (35) 보험 가입전 필수 체크포인트 5가지", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34662&menuNo=200498"),
    "fss_tip_040": ("금융꿀팁 200선 (40) 은행거래 100% 활용법(4): 대출이자 부담줄이기", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34667&menuNo=200498"),
    "fss_tip_048": ("금융꿀팁 200선 (48) 어르신을 위한 금융꿀팁(1): 은행거래", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34675&menuNo=200498"),
    "fss_tip_049": ("금융꿀팁 200선 (49) 맞벌이부부를 위한 금융꿀팁", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34676&menuNo=200498"),
    "fss_tip_050": ("금융꿀팁 200선 (50) 금리인하요구권 활용하기", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34677&menuNo=200498"),
    "fss_tip_063": ("금융꿀팁 200선 (63) 전세자금대출자를 위한 금융꿀팁", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34690&menuNo=200498"),
    "fss_tip_078": ("금융꿀팁 200선 (78) 금리인상기, 금리부담 완화 등을 위한 금융정보", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34705&menuNo=200498"),
    "fss_tip_122": ("금융꿀팁 200선 (122) 사회초년생 및 은퇴준비자의 연금저축 활용법", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=34748&menuNo=200498"),
    "fss_tip_136": ("금융꿀팁 200선 (136) 전세 계약시 유의사항 및 전세보증금 반환보증 활용법", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=57653&menuNo=200498"),
    "fss_tip_139": ("금융꿀팁 200선 (139) 보험계약 해지 전 보험계약대출 등 다른 방안 먼저 알아보기", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=57893&menuNo=200498"),
    "fss_tip_143": ("금융꿀팁 200선 (143) 신입사원의 금융상품 현명하게 가입하기(보험)", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=131881&menuNo=200498"),
    "fss_tip_146": ("금융꿀팁 200선 (146) 신입사원의 금융상품 현명하게 가입하기(예적금)", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=131884&menuNo=200498"),
    "fss_tip_149": ("금융꿀팁 200선 (149) 신입사원의 금융상품 현명하게 가입하기(투자)", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=136622&menuNo=200498"),
    "fss_tip_152": ("금융꿀팁 200선 (152) 대출 청약철회권 활용하기", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=136625&menuNo=200498"),
    "fss_tip_157": ("금융꿀팁 200선 (157) 은퇴준비자의 연금설계를 위한 꿀팁", "https://www.fss.or.kr/fss/bbs/B0000173/view.do?nttId=189291&menuNo=200498"),
}
LAWS = {  # source_id 꼬리 → 법령 이름(국가법령정보센터 현행 법령). 제도·법 RAG의 법령 원문(docs/06 4절)
    "law_basic_pension": "기초연금법",
    "law_hf_corp": "한국주택금융공사법",
    "law_hf_corp_decree": "한국주택금융공사법 시행령",
    "law_housing_fund": "주택도시기금법",
    "law_housing_supply_rule": "주택공급에 관한 규칙",
    "law_depositor_protection": "예금자보호법",
    "law_tax_special": "조세특례제한법",
    # 공동 목표 설정 2단계 '통계 기준'(docs/08 4절). RAG 목록(rag/index.py)에는 넣지 않았다
    "law_local_tax": "지방세법",
    "law_realtor_rule": "공인중개사법 시행규칙",
    "law_ltc_insurance": "노인장기요양보험법",
}
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
    # 공동 목표 설정 2단계 '통계 기준'(docs/08 4절): 장기요양 급여비용(보건복지부 고시, 건강보험공단 법령 정보)
    "nhis_ltc_cost_notice": ("국민건강보험공단", "장기요양급여 제공기준 및 급여비용 산정방법 등에 관한 고시",
                             "https://www.nhis.or.kr/lm/lmxsrv/law/lawFullContent.do?SEQ=1637"),
}


def page_text(url: str, data: bytes | None = None) -> str:
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"허용 목록에 없는 출처예요: {host}")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (ONE-Heart dev snapshot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>|</(p|div|li|tr|h\d|dt|dd|table|section)>", "\n", raw)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    t = re.sub(r"[ \t\r\f\v ]+", " ", t)
    return "\n".join(line.strip() for line in t.split("\n") if line.strip()) + "\n"


def law_text(name: str) -> tuple[str, str, str]:
    """국가법령정보센터 현행 법령 본문 → (글, 시행일, 주소). 법령 화면은 틀(iframe)만 주고 본문은 lsInfoR.do가 준다(인증키 없음)."""
    url = "https://www.law.go.kr/법령/" + name
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/"), headers={"User-Agent": "Mozilla/5.0 (ONE-Heart dev snapshot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        shell = r.read().decode("utf-8", errors="replace")
    m = re.search(r'lsInfoP\.do\?lsiSeq=(\d+)[^"]*?efYd=(\d+)', html.unescape(shell))
    if not m:
        raise ValueError(f"법령을 찾지 못했어요: {name}")
    body = f"https://www.law.go.kr/LSW/lsInfoR.do?lsiSeq={m.group(1)}&chrClsCd=010202&urlMode=lsInfoP&efYd={m.group(2)}&ancYnChk=0"
    return page_text(body, data=b""), m.group(2), body


def hwp_text(data: bytes) -> str:
    """한글(HWP 5) 파일 → 문단 글. 본문 레코드(HWPTAG_PARA_TEXT)의 글자만 읽고 표·그림 같은 컨트롤은 건너뛴다.
    olefile이 필요하다(pip install olefile, 이 도구에서만 씀)."""
    import io
    import struct
    import zlib

    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    compressed = bool(struct.unpack("<I", ole.openstream("FileHeader").read()[36:40])[0] & 1)
    paras = []
    for e in sorted((e for e in ole.listdir() if e[0] == "BodyText"), key=lambda e: int(e[1][7:])):
        raw = ole.openstream(e).read()
        raw = zlib.decompress(raw, -15) if compressed else raw
        i = 0
        while i < len(raw):
            h = struct.unpack("<I", raw[i:i + 4])[0]
            i += 4
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            if size == 0xFFF:
                size = struct.unpack("<I", raw[i:i + 4])[0]
                i += 4
            rec, i = raw[i:i + size], i + size
            if tag != 67:
                continue
            chars, j = [], 0
            while j < len(rec):
                c = struct.unpack("<H", rec[j:j + 2])[0]
                if c in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23):  # 컨트롤 문자: 8글자(16바이트)
                    chars.append(" " if c == 9 else "")
                    j += 16
                    continue
                chars.append(chr(c) if c >= 32 else "")
                j += 2
            s = "".join(chars).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
            s = re.sub(r"[ \t ]+", " ", s).strip()
            if s:
                paras.append(s)
    return "\n".join(paras) + "\n"


def fss_tip_text(url: str) -> tuple[str, str]:
    """금융꿀팁 게시글 → 첨부 한글 파일의 글, 첨부 주소."""
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"허용 목록에 없는 출처예요: {host}")
    ua = {"User-Agent": "Mozilla/5.0 (ONE-Heart dev snapshot)"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=30) as r:
        page = r.read().decode("utf-8", errors="replace")
    m = re.search(r'href="(/fss/cmmn/file/fileDown\.do\?[^"]+)"', page)
    if not m:
        raise ValueError(f"첨부 파일이 없어요: {url}")
    file_url = "https://www.fss.or.kr" + html.unescape(m.group(1))
    with urllib.request.urlopen(urllib.request.Request(file_url, headers=ua), timeout=60) as r:
        data = r.read()
    if not data.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(f"한글(HWP) 파일이 아니에요: {file_url}")
    return hwp_text(data), file_url


def fetch(key: str) -> dict:
    eff = file_url = None
    if key in LAWS:
        org, title = "국가법령정보센터", LAWS[key]
        text, eff, url = law_text(title)
    elif key in FSS_TIPS:
        org, (title, url) = "금융감독원", FSS_TIPS[key]
        text, file_url = fss_tip_text(url)
    else:
        org, title, url = DOCS[key]
        text = page_text(url)
    sid = f"S_doc_{key}_{time.strftime('%Y%m%d')}"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{sid}.txt"
    path.write_text(text, encoding="utf-8")
    meta = {"source_id": sid, "kind": "document", "publisher": org, "title": title, "url": url,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M"), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "file": path.relative_to(ROOT).as_posix(), "doc_key": key, "dev_only": True}
    if file_url:
        meta["attachment_url"] = file_url  # 글은 게시글에 붙은 한글 파일에서 뽑았다
    if eff:
        meta["effective_date"] = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"sources": []}
    idx["sources"] = [s for s in idx["sources"] if s["source_id"] != sid] + [meta]
    idx["sources"].sort(key=lambda s: s["source_id"])
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


if __name__ == "__main__":
    for k in sys.argv[1:] or list(DOCS) + list(LAWS) + list(FSS_TIPS):
        m = fetch(k)
        print(f"{m['file']}  {len((ROOT / m['file']).read_text(encoding='utf-8')):,}자  {m['title']}")
