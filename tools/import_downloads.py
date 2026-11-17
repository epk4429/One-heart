"""형님이 공식 사이트에서 내려받은 파일(표·PDF·웹 본문 글)을 원문 저장소(knowledge/sources)로 옮긴다(2026-11-17).

사용: python tools/import_downloads.py [내려받은 파일을 둔 폴더(기본 knowledge/raw/dl_20261117)]
필요한 패키지(개발 PC에만, 배포 묶음에는 불필요): pip install xlrd openpyxl pypdf

- 표(.xls/.xlsx): 칸 내용을 그대로 `knowledge/sources/S_<기관>_<이름>_<YYYYMM>.json`의 grid에 담는다(해석은 ontology가 따로 한다).
- PDF·웹 본문: 글만 뽑아 `knowledge/sources/docs/S_doc_<키>_<날짜>.txt`로 저장한다(ontology/programs.json의 인용 검사 대상).
- 두 가지 모두 knowledge/sources/index.json에 sha256·출처 주소를 남긴다(tests/test_knowledge.py가 원본이 그대로인지 본다).
- 원본 파일은 knowledge/raw/(git 제외)에 그대로 있다. 이 도구는 거기서 언제든 다시 만들 수 있다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "knowledge/sources"
DOCS = SOURCES / "docs"
INDEX = SOURCES / "index.json"
FETCHED = "2026-11-17"

# (원본 파일 이름 앞부분, source_id, 기관, 제목, 주소, 기준)
TABLES = [
    ("가계신용대출_상품별금리현황_", "S_fsb_credit_loan_202611", "저축은행중앙회 소비자포털", "저축은행 가계신용대출 · 상품별 금리현황",
     "https://www.fsb.or.kr/ratloanconf_0100.act", "공시 2026-11"),
    ("중도상환수수료율_", "S_fsb_prepay_fee_202611", "저축은행중앙회 소비자포털", "저축은행 중도상환수수료율(저축은행별)",
     "https://www.fsb.or.kr/ratlfeemdrp_0100.act", "2026년 기준"),
    ("입출금자유예금_", "S_fsb_checking_202611", "저축은행중앙회 소비자포털", "저축은행 입출금자유예금",
     "https://www.fsb.or.kr/ratanym_0100.act", "공시 2026-11"),
    ("정기예금_", "S_fsb_deposit_202611", "저축은행중앙회 소비자포털", "저축은행 정기예금 현재금리",
     "https://www.fsb.or.kr/ratedepo_0100.act", "공시 2026-11"),
    ("정기적금_", "S_fsb_saving_202611", "저축은행중앙회 소비자포털", "저축은행 정기적금 현재금리",
     "https://www.fsb.or.kr/rateinst_0100.act", "공시 2026-11"),
    ("가계대출금리(", "S_kfb_household_loan_202611", "전국은행연합회 소비자포털", "은행 가계대출금리(신용점수별)",
     "https://portal.kfb.or.kr/compare/loan_household_new.php", "공시 2026-10"),
    ("대출수수료(", "S_kfb_loan_fee_202611", "전국은행연합회 소비자포털", "은행 대출관련 제증명서 발급수수료",
     "https://portal.kfb.or.kr/compare/commission_loan.php", "2026-11-17 조회"),
    ("예금상품금리비교_", "S_kfb_deposit_202611", "전국은행연합회 소비자포털", "은행 예금금리(정기예금)",
     "https://portal.kfb.or.kr/compare/receiving_deposit_3.php", "2026-11-17 조회"),
    ("중소기업대출금리[", "S_kfb_sme_loan_202611", "전국은행연합회 소비자포털", "은행 중소기업대출금리(신용대출 신용등급별)",
     "https://portal.kfb.or.kr/compare/loan_snmindustry.php", "공시 2026-10"),
]
# (원본 파일 이름 앞부분(또는 정확한 이름), doc_key, 기관, 제목, 주소, 기준일)
DOC_FILES = [
    ("소득세법(법률)", "law_income_tax", "국가법령정보센터", "소득세법", "https://www.law.go.kr/법령/소득세법", "2026-07-01"),
    ("고용보험법(법률)", "law_employment_insurance", "국가법령정보센터", "고용보험법", "https://www.law.go.kr/법령/고용보험법", "2026-09-18"),
    ("고용정책 상세_제도안내", "work24_parental_leave_benefit", "고용24", "육아휴직급여(고용24 제도안내)",
     "https://m.work24.go.kr/cm/c/f/1100/selecSystInfo.do?systClId=SC00000251&systId=SI00000402", ""),
    ("(최종) 2025년도 부모급여", "mohw_parent_benefit_2025_guide", "보건복지부", "2025년도 부모급여 사업안내(2025년 기준)",
     "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?wlfareInfoId=WLF00004657&wlfareInfoReldBztpCd=01", "2025"),
    ("국세청.pdf", "nts_eitc", "국세청", "근로장려금 소개", "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?mi=2450&cntntsId=7781", ""),
]
DOC_TEXTS = [  # 웹 본문을 직접 읽어 저장한 글
    ("web_bokjiro_", "bokjiro_parent_benefit_2026", "보건복지부(복지로)", "부모급여 지원(2026년 기준)", "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?wlfareInfoId=WLF00004657&wlfareInfoReldBztpCd=01", "2026"),
    ("web_kinfa2_", "kinfa_counseling", "서민금융진흥원", "서민금융통합지원센터 상담과 햇살론일반", "https://www.kinfa.or.kr/counselingSupport/centerIntroduction.do", "2026-11-17"),
    ("web_hf_", "hf_bogeumjari_rates_2026_11", "한국주택금융공사", "보금자리론 금리안내(2026년 11월)", "https://www.hf.go.kr/ko/sub01/sub01_01_04.do", "2026-11-09 공시"),
    ("web_kfb_", "kfb_prepay_fee_credit", "전국은행연합회", "은행 대출 중도상환수수료율(신용, 2026년)", "https://portal.kfb.or.kr/compare/commission_loan_search.php", "2026년 기준"),
    ("web_ccrs_", "ccrs_debt_adjustment_compare", "신용회복위원회", "채무조정제도 비교", "https://www.ccrs.or.kr/cms/com/index.do?MENU_ID=490", ""),
    ("web_kinfa_", "kinfa_future_youth_savings", "서민금융진흥원", "청년미래적금 상품 안내", "https://fill4young.kinfa.or.kr/yfs/main", "2026-11-17"),
]


def _grid(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    if path.suffix == ".xls":
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_index(0)
        for r in range(sh.nrows):
            rows.append([str(c).strip() for c in sh.row_values(r)])
    else:
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if c is None else str(c).strip() for c in row])
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def _put(meta: dict) -> None:
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"sources": []}
    idx["sources"] = [s for s in idx["sources"] if s["source_id"] != meta["source_id"]] + [meta]
    idx["sources"].sort(key=lambda s: s["source_id"])
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _find(folder: Path, prefix: str, exts: tuple[str, ...]) -> Path:
    hits = sorted(p for p in folder.iterdir() if p.name.startswith(prefix) and p.suffix.lower() in exts)
    if len(hits) != 1:
        raise SystemExit(f"{prefix}로 시작하는 파일이 {len(hits)}개예요: {[p.name for p in hits]}")
    return hits[0]


def import_tables(folder: Path) -> None:
    for prefix, sid, publisher, title, url, basis in TABLES:
        src = _find(folder, prefix, (".xls", ".xlsx"))
        grid = _grid(src)
        body = {"title": title, "basis": basis, "grid": grid}
        text = json.dumps(body, ensure_ascii=False, indent=1)
        path = SOURCES / f"{sid}.json"
        path.write_text(text, encoding="utf-8")
        _put({"source_id": sid, "kind": "table", "publisher": publisher, "url": url, "title": title, "fetched_at": FETCHED,
              "effective_date": basis, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
              "file": path.relative_to(ROOT).as_posix(), "counts": {"rows": len(grid)}, "dev_only": True})
        print(f"{sid}  {len(grid)}줄  ← {src.name}")


def _pdf_text(path: Path) -> str:
    import pypdf
    text = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(path).pages)
    return text.replace("\xa0", " ")  # 줄 끝·낱말 사이의 특수 공백은 보통 공백으로(인용 글자 일치 검사가 같은 글로 보게)


def import_docs(folder: Path) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for prefix, key, publisher, title, url, basis in DOC_FILES + DOC_TEXTS:
        from_text = prefix.startswith("web_")
        src = _find(folder, prefix, (".txt",) if from_text else (".pdf",))
        text = src.read_text(encoding="utf-8") if from_text else _pdf_text(src)
        sid = f"S_doc_{key}_{FETCHED.replace('-', '')}"
        path = DOCS / f"{sid}.txt"
        path.write_text(text, encoding="utf-8")
        _put({"source_id": sid, "kind": "document", "publisher": publisher, "title": title, "url": url, "fetched_at": FETCHED,
              "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "file": path.relative_to(ROOT).as_posix(),
              "doc_key": key, "dev_only": True, **({"effective_date": basis} if basis else {})})
        print(f"{sid}  {len(text)}자  ← {src.name}")


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "knowledge/raw/dl_20261117"
    import_tables(folder)
    import_docs(folder)
