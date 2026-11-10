"""상품 노드의 글 항목(우대조건·가입대상·기타 유의사항) → 조건 규칙(docs/06 3.5절).

코드가 원문을 항목으로 나누고 금액·조건 종류를 뽑는다. 그다음 기계 검사로 믿을 수 있는지 판정한다.
- G3 인용 글자 일치: 모든 항목·상한·유의사항의 quote가 원문에 그대로 있다.
- G4 숫자 일치: add_pp가 quote 안의 숫자(또는 "및"으로 이어진 숫자들의 합)다.
- G5 독립 대조: 뽑은 우대 항목으로 받을 수 있는 최대(상한 적용)가 공시 API의 정형 값 "최고 우대금리 − 기본금리"와 맞아야 한다.
  글(우대조건)과 숫자(옵션 금리)는 금융회사가 따로 제출한 항목이라 서로 독립적인 근거다.
- G6 단서 조항: "다만·단,·제외·경우에 한·중복 적용" 등은 caveats로 남긴다.
- G8 보수적 기본값: 금액이 없거나 종류를 모르는 항목, 공시보다 적게 뽑힌 상품은 needs_check → 화면에서 "확인 필요".
원문 사례 테스트(G7)는 tests/test_conditions.py에 사람이 원문을 읽고 적은 정답으로 둔다.

상태: verified(합이 공시와 맞음) / capped(항목은 모두 뽑혔고 합이 공시보다 큼 → 택일·단계형이 섞인 것으로 보고 공시 최고 우대로 제한)
      / needs_check(빠진 항목이 있거나 읽지 못한 항목이 있음).
"""

from __future__ import annotations

import re

# 우대 항목의 조건 종류. kind: action = 본인이 하면 받는 것 / attribute = 사람의 조건(가족 정보로 판정하거나 확인 필요) /
# relation = 그 금융회사와의 거래 관계(가족 정보로 알 수 없음 → 확인 필요). 앞에서부터 처음 맞는 것.
TAGS = [
    ("promo", "쿠폰·이벤트·추천·특판", "action", r"쿠폰|이벤트|추천|프로모션|특판|우대\s*코드|코드를\s*입력"),
    ("job", "직업·사업자·학력", "attribute", r"근로자|재직|공무원|군인|나라사랑|개인사업자|사업자\s*계좌|졸업|사관학교"),
    ("age", "나이", "attribute", r"만\s*\d+\s*[~∼-]?\s*\d*\s*세|청년|시니어|어르신|MZ"),
    ("child", "출산·자녀", "attribute", r"출산|임신|자녀|다자녀|육아|태아|아이"),
    ("housing", "주거(무주택 등)", "attribute", r"무주택|신혼|주택\s*소유|세대주"),
    ("welfare", "복지 대상(비과세종합저축·장애 등)", "attribute", r"비과세종합저축|장애|기초생활|국가유공|한부모|저소득|소득취약|전세사기"),
    ("new_customer", "첫 거래 고객", "relation", r"첫\s*거래|첫거래|첫\s*예금|신규\s*고객|최초\s*(거래|신규)|미보유|이력\s*미보유|보유\s*이력이\s*없|해지\s*이력|퍼스트\s*고객|처음"),
    ("loyalty", "주거래·거래 실적·등급", "relation", r"VIP|우수\s*고객|등급|주거래|평잔|총수신|요구불|거래\s*실적|장기\s*거래|복수\s*거래|교차\s*거래|탑스"),
    ("salary", "급여·연금 받기", "action", r"급여|소득\s*이체|연금\s*(입금|이체|수령)|연금이체"),
    ("utility", "공과금·관리비 자동이체", "action", r"공과금|관리비"),
    ("card", "카드 사용", "action", r"카드"),
    ("auto_transfer", "자동이체로 넣기", "action", r"자동\s*이체"),
    ("consent", "마케팅·정보 동의", "action", r"마케팅|동의|수신"),
    ("online", "비대면 가입·앱", "action", r"인터넷|모바일|스마트폰|비대면|앱|오픈뱅킹|전자명함|디지털|뱅킹|미발급|무통장|로그인"),
    ("linked", "다른 상품 함께 가입·보유", "action", r"동시\s*가입|동일자\s*가입|연결|보유|청약|함께|패키지|가입\s*고객"),
    ("deposit_size", "넣는 금액·잔액", "action", r"잔액|원금|월부금|목돈|예치|\d+\s*[천백]?\s*만\s*원\s*(이상|초과|이하)|만원이상"),
    ("goal", "목표·미션 달성", "action", r"목표|달성|별\s*모으기|스탬프|지속적\s*납입|매월|챌린지|걸음|미션|ESG|저탄소|탄소|인증|방문|실천|절감|서약|플라스틱|대중교통|회차|회전|성공|저금|입금\s*시|만기\s*해지|해지\s*시|유지"),
]
TAG = {t: {"label": l, "kind": k} for t, l, k, _ in TAGS}
_TAG_RE = [(t, re.compile(rx)) for t, _, _, rx in TAGS]
_AMT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~\s*(\d+(?:\.\d+)?))?\s*%\s*p?", re.I)
_CAPWORD = re.compile(r"최고|최대|합산|한도")
_CAVEAT = re.compile(r"다만|단,|단\)|\(단|제외|경우에\s*한|에\s*한함|한하여|불가|중복\s*적용|않음|않습니다|유의사항|참조|상품설명서")
_NONE = re.compile(r"^\s*(없음|해당\s*없음|해당무|해당사항\s*없음|-)\s*$|우대\s*조건\s*없이")
_BULLET = re.compile(r"^\s*([①-⑳]|\d+\s*[.)]|\d+-\d+\s*[.)]|[가나다라마바사아자차카타파하]\s*[.)]|[-*·•▶※ㆍ])")
_TIER = re.compile(r"\d+\s*(년|개월|회|만원|개|일|주차|주|회차)\s*(제|이상|이하|초과|미만)?\s*[:：]?\s*(연\s*)?\d")
_TIER_LINE = re.compile(r"\d+\s*(일|회차|회|주차|개월|년)\s*(제|이상|이하|미만)?\s*(저금\s*)?(성공|[:：,]|\d)|\d+\s*[~-]?\s*\d*\s*개월")
_SEG = re.compile(r"(개인형|기업형|공통|가입자격별|고객별|\d+\s*개월\s*(제|미만|이상)|\d+\s*년\s*제)")
_HEADER = re.compile(r"(경우|아래|다음|요건|충족\s*시|중|따라|차등|지급)\s*[:：]?\s*$|아래|다음의")


def _lines(text: str) -> list[str]:
    return [l.strip() for l in (text or "").replace("\r", "").split("\n") if l.strip()]


def _amounts(line: str) -> list[tuple[float, float]]:
    return [(float(a), float(b) if b else float(a)) for a, b in _AMT.findall(line)]


def _tag(text: str) -> str:
    for t, rx in _TAG_RE:
        if rx.search(text):
            return t
    return "other"


def _is_cap(line: str, tag: str) -> bool:
    """상품 전체 상한·요약 줄: "최고우대금리 1.2%p", "합산 최대 0.2%p", "개인형 우대이율: 최대0.5%", "6개월제 최대 0.55%, 12개월제 최대 0.9%".
    "카드거래: 최대 0.3%"처럼 조건이 붙은 줄은 상한이 아니라 항목(그 항목의 최대값)이다."""
    if not _CAPWORD.search(line):
        return False
    if re.search(r"합산\s*(최대|최고)|최대\s*한도|최고\s*(우대|가산)|(우대|가산)\s*(금리|이율)\s*[:：]?\s*(최고|최대)", line) and tag in ("other", "promo"):
        return True
    return tag == "other" or bool(_SEG.search(line)) and tag in ("other", "job")


def _rank(line: str) -> int:
    """글머리 깊이: 1 = "1." "*" "▶" "※" / 2 = "①" "가." / 3 = "-" "·" / 4 = 글머리 없음(앞 줄에 이어지는 글)."""
    if re.match(r"^\s*(\d+\s*[.]|\d+-\d+\s*[.)]|[*▶※])", line):
        return 1
    if re.match(r"^\s*([①-⑳]|[가나다라마바사아자차카타파하]\s*[.)]|\d+\))", line):
        return 2
    if re.match(r"^\s*[-·•ㆍ]", line):
        return 3
    return 4


_ENUM = re.compile(r"^\s*([①-⑳]|\d+\s*[.)]|\d+-\d+\s*[.)]|[가나다라마바사아자차카타파하]\s*[.)])")
_ALT_CTX = re.compile(r"신규\s*고객|기존\s*고객|개인형|기업형")


def parse_benefits(text: str) -> dict:
    """우대조건 글 → 항목·상한·유의사항. 항목: quote(원문 줄), context(위 머리말), add_pp(이 항목으로 받을 수 있는 최대),
    tag, kind, issues, rank(글머리 깊이), group(묶음·단계형·모두 충족 무리), alt(고객 구분 택일 무리)."""
    lines = _lines(text)
    if not lines or all(_NONE.search(l) or len(l) <= 6 and not _amounts(l) for l in lines):
        return {"items": [], "caps": [], "notes": [], "none": True}
    items, caps, notes, pending, context, cont, gid = [], [], [], [], None, None, 0

    def flush():
        """금액 없이 남은 줄(바로 위 항목 다음에 이어진 줄들): 위 항목보다 깊은 글머리("- 제공조건 : ~")이거나
        같은 종류의 조건("나. 앱푸시·이메일 중 하나 이상 동의")이면 그 항목의 세부 조건으로 붙이고, 아니면 '금액 없음' 항목으로 둔다."""
        nonlocal pending
        if pending:
            k = items.index(pending[0])
            prev = items[k - 1] if k and items[k - 1]["add_pp"] is not None else None
            for it in pending:
                if prev is not None and (it["rank"] >= 2 and it["rank"] > prev["rank"] or it["tag"] == prev["tag"]):
                    prev.setdefault("details", []).append(it["quote"])
                    items.remove(it)
        pending = []

    for line in lines:
        if _NONE.search(line):
            continue
        amts = _amounts(line)
        tag = _tag(line)
        rank = _rank(line)
        if amts and _is_cap(line, tag) and not (_ENUM.match(line) and not re.search(r"합산|최고\s*우대|최대\s*우대|최대\s*한도", line)):
            flush()
            caps.append({"quote": line, "cap_pp": max(b for _, b in amts)})
            cont = None
            continue
        if not amts:
            cont = None
            if (_CAVEAT.search(line) and re.search(r"유의사항|않|참조|불가|중복|\(단|다만", line)) or line.startswith("("):
                notes.append(line)  # 유의사항·단서: 상품 전체에 붙는 말
            elif (not _ENUM.match(line) or re.search(r"(경우|고객\s*중|중|따라|요건|충족\s*시)\s*[:：]?\s*$", line)) and (_HEADER.search(line) or re.search(r"경우|따라|요건|충족|별\s*우대|중\s*\d+\s*가지", line)
                                             or len(re.sub(r"[\s\W\d]|우대|금리|이율|조건|고객", "", line)) <= 6):
                flush()
                context = line  # 아래 항목들에 걸리는 머리말("신규고객", "1. ~인 경우", "*우대이율", "자동재예치 우대이율")
            else:
                it = {"quote": line, "context": context, "add_pp": None, "tag": tag if tag != "other" else _tag(context or ""),
                      "issues": ["금액 없음"], "rank": rank}
                items.append(it)
                pending.append(it)
            continue
        if pending and (re.match(r"^\s*각\s*", line) or rank == 4 or line.startswith("(")):
            a = max(b for _, b in amts)  # "-A ⏎ -B ⏎ 각 연0.2%p", "2. 급여이체 실적 ⏎ 인 경우 : 연 1.0%p"
            joint = len(pending) > 1 and not re.match(r"^\s*각", line) and re.search(r"모두|동시에", context or "")
            if joint:  # "아래의 조건을 모두 충족하는 경우": 여러 줄이 한 항목
                gid += 1
            for it in pending:
                it.update(add_pp=a, shared_quote=line)
                it["issues"].remove("금액 없음")
                if joint:
                    it.update(group=f"a{gid}")
            cont, pending = pending[-1], []
            continue
        if cont is not None and rank == 4 and not line.startswith("("):
            cont["add_pp"] = max(cont["add_pp"], max(b for _, b in amts))  # "1년: 0.6%p, 2년: 0.7%p, ⏎ 3년: 0.9%p, 5년: 1.0%p"
            cont.setdefault("more_quotes", []).append(line)
            cont["tiered"] = True
            continue
        flush()
        summed = len(amts) > 1 and re.search(r"및|\+|더하여", line) and not _TIER.search(line)
        add = round(sum(b for _, b in amts), 2) if summed else max(b for _, b in amts)
        it = {"quote": line, "context": context, "add_pp": add, "tag": tag if tag != "other" else _tag(context or ""),
              "issues": [], "rank": rank}
        if len(amts) > 1:
            it["summed" if summed else "tiered"] = True  # "및"으로 이어지면 더한 값, 기간·구간별로 다르면 최대값
        items.append(it)
        cont = it
    flush()
    _group(items)
    for it in items:
        it["kind"] = TAG.get(it["tag"], {}).get("kind", "unknown")
        if it["tag"] == "other" and it.get("role") != "group":
            it["issues"].append("조건 종류를 모름")
        cav = _CAVEAT.search(it["quote"] + " " + (it.get("context") or ""))
        if cav:
            it["caveat"] = cav.group(0)
        if it["kind"] == "attribute" and it.get("role") != "group":
            who = person_rule(chr(10).join([it["quote"]] + it.get("more_quotes", [])))
            if who:
                assert who["quote"] in text  # G3
                it["who"] = who
    return {"items": items, "caps": caps, "notes": notes, "none": False}


def _group(items: list[dict]) -> None:
    """묶음·단계형·택일 무리를 찾는다.
    - 묶음: 윗 글머리 줄 아래에 더 깊은 글머리 항목들이 있고, 그 합 또는 최대가 윗줄 금액과 같으면 윗줄은 묶음(role=group)이 되어
      아래 항목들의 상한이 된다. 예: "자동이체 연속 성공: 최고 연 3%p" 아래 ①1%p ②2%p(합), "급여실적 1%p(①/② 중복 불가)" 아래 ①1 ②1(택일).
    - 단계형: "3일 성공 2% ⏎ 7일 성공 3% ⏎ …", "3~5개월 0.6% ⏎ 6~11개월 0.6% ⏎ …"처럼 같은 종류가 구간별로 이어지면 그중 하나(최대값).
    - 택일 무리: "신규고객 ⏎ ①… ⏎ 기존고객 ⏎ ①…"처럼 고객 구분 머리말 아래 무리는 그중 하나."""
    n, gid = len(items), 0
    for i, x in enumerate(items):
        a = x["add_pp"]
        if a is None or x.get("group"):
            continue
        run, top = [], 0 if x["rank"] == 4 else x["rank"]  # 글머리 없는 제목 줄("자동이체 연속 성공 우대금리 : 최고 3%p")은 가장 위
        for r in items[i + 1:]:
            if r["rank"] <= top or r.get("group"):
                break
            run.append(r)
        if not run or any(r["add_pp"] is None for r in run):
            continue
        s, m = sum(r["add_pp"] for r in run), max(r["add_pp"] for r in run)
        if abs(s - a) <= 0.051 or abs(m - a) <= 0.001:
            gid += 1
            x.update(role="group", group=f"g{gid}", group_rule="sum" if abs(s - a) <= 0.051 else "one_of")
            for r in run:
                r["group"] = f"g{gid}"
                if r["tag"] == "other":
                    r["tag"] = x["tag"]  # "- 5회이상 : 0.2%p, …"는 위 묶음 줄("자동이체 입금횟수")의 종류
    i = 0
    while i < n:
        j = i
        while (j + 1 < n and not items[i].get("group") and not items[j + 1].get("group") and items[j + 1]["add_pp"] is not None
               and items[j + 1]["tag"] == items[i]["tag"] and _TIER_LINE.search(items[j + 1]["quote"]) and _TIER_LINE.search(items[i]["quote"])):
            j += 1
        if j > i:
            gid += 1
            for r in items[i:j + 1]:
                r.update(group=f"t{gid}", tier=True)
        i = j + 1
    alts = sorted({it["context"] for it in items if it.get("context") and _ALT_CTX.search(it["context"])})
    if len(alts) > 1:
        for it in items:
            if it.get("context") in alts:
                it["alt"] = it["context"]


# 우대 합산(묶음은 상한까지, 단계형·택일은 그중 큰 것)은 계산엔진이 한다(2026-11-11, CLAUDE.md 5절). 온톨로지는 항목을 만들고 판정만.
from engine.rates import applicable, reachable  # noqa: E402,F401  (예전 이름 그대로 쓰는 곳이 있어 다시 내보낸다)


# ---------- 사람 조건(5단계): 우대·가입대상의 사람 조건을 가족 정보로 판정 ----------
# 가족이 고르는 사람 조건. 고르면 '해당', 안 고르면 '모름'(해당 안 됨이 아님). 금융회사가 가입할 때 증빙으로 확인한다.
PERSON = {
    "pregnant": "임신 중이에요(출산 예정)", "newborn": "2년 안에 태어난 아이가 있어요", "single_parent": "한부모 가정이에요",
    "disabled": "장애인으로 등록돼 있어요", "low_income": "기초생활수급·차상위예요", "employee": "직장에 다녀요(근로자)",
    "self_employed": "자영업자(개인사업자)예요",
}
_KIDS_AGE = re.compile(r"(?:만\s*)?(\d+)\s*세\s*(이하|미만)?\s*(?:의\s*)?(?:다자녀|자녀|가구원|고객\s*수|아동)")
_NUM = {"한": 1, "두": 2, "세": 3, "네": 4}
_COUNT = re.compile(r"(\d|한|두|세|네)\s*[명인]\s*(이상)?")
_TIER_KIDS = re.compile(r"(\d)\s*명\s*(이상)?\s*[^\d%]{0,12}?(\d+(?:\.\d+)?)\s*%")
_HOLDER_AGE = re.compile(r"만?\s*(\d+)\s*세?\s*[~∼-]\s*만?\s*(\d+)\s*세\s*(이하|미만)?|만?\s*(\d+)\s*세\s*(이상|이하|미만)?")


def _line(t: str, rx: str) -> str:
    """rx가 처음 나오는 원문 줄(근거로 보여 줄 인용)."""
    return next(l.strip() for l in t.split(chr(10)) if re.search(rx, l))


def _composite(t: str) -> bool:
    """여러 조건을 나열한 줄("-정기예금 이용 -첫번째 적금 가입 … -60세 이상", "착한운전마일리지 신청자, 저공해차량 운전자, …")은 어느 조건인지 하나로 정할 수 없다."""
    return len(re.findall(r"(?:^|\s)-\S", t)) >= 3 or t.count(",") >= 3


def person_rule(t: str) -> dict | None:
    """사람 조건 글 → 판정 규칙. 하나로 정할 수 없으면 None(화면에서 '해당되면'으로 남는다). quote는 원문에 그대로 있는 글.
    type: age(계좌 주인 나이) / kids(18세 이하 자녀 수, tiers = 명수별 우대) / flags(가족이 고르는 조건 중 하나라도)."""
    if not t or _composite(t) or re.search(r"비과세종합저축|전세사기|세대주|청년층|중소기업|졸업|계좌\s*실적|통장\s*가입|아이계좌|아이사랑|공무원|국가유공", t):
        return None  # 비과세종합저축: 2026년 대상 변경을 1차 출처(법령)로 확인 못 함(docs/06 부록 A). 나머지: 가족 정보로 알 수 없음
    flags = []
    for f, rx in (("single_parent", r"한부모"), ("disabled", r"장애인\s*(등록|연금)|장애인\s*$|장애인\s*고객"), ("low_income", r"기초생활|차상위|소득취약|저소득"),
                  ("pregnant", r"임신|출산\s*예정|출산예정|가입\s*기간\s*(중|내)[^%]*출산|가입기가\s*중\s*출산"),
                  ("newborn", r"\d\s*년\s*이내\s*출생"), ("employee", r"직장인|근로자|재직"), ("self_employed", r"자영업|개인사업자")):
        if re.search(rx, t):
            flags.append(f)
    if flags:
        if "single_parent" in flags or "disabled" in flags or "low_income" in flags:
            flags = [f for f in flags if f in ("single_parent", "disabled", "low_income")]
        if re.search(r"다둥이|미성년\s*자녀\s*\d", t) and "pregnant" in flags:
            return None  # "다둥이 가정 출산시": 출산과 자녀 수가 함께 걸린 조건
        return {"type": "flags", "flags": flags, "quote": _line(t, r"한부모|장애인|기초생활|차상위|소득취약|저소득|임신|출산|출생|직장인|근로자|재직|자영업|개인사업자")}
    k = _KIDS_AGE.search(t)
    if k or re.search(r"다자녀|미성년\s*자녀|미성년자\s*자녀", t):
        if k and not (int(k.group(1)) == 18 and k.group(2) != "미만" or int(k.group(1)) == 19 and k.group(2) == "미만"):
            return None  # 12세·16세·미취학 등 자녀 나이 조건: 가족 정보로 자녀 나이를 알 수 없다
        if re.search(r"가구원|고객\s*수|미취학", t):
            return None
        tiers = [[int(n), float(pp)] for n, _, pp in _TIER_KIDS.findall(t)]
        c = _COUNT.search(t)
        if tiers:
            lo = min(n for n, _ in tiers)
        elif c:
            lo = _NUM.get(c.group(1)) or int(c.group(1))
        elif re.search(r"다자녀", t):
            return {"type": "kids", "min": 3, "maybe_from": 2, "tiers": None, "quote": _line(t, "다자녀")}  # 은행마다 2명·3명
        else:
            lo = 1
        q = _line(t, "다자녀|미성년|자녀")
        return {"type": "kids", "min": lo, "maybe_from": None, "tiers": tiers or None, "quote": q}
    if re.search(r"자녀|아이|육아|태아", t):
        return None
    a = _HOLDER_AGE.search(t)
    if a:
        r_lo, r_hi, r_op, lo, op = a.groups()
        q = a.group(0).strip()
        if r_lo:
            return {"type": "age", "min": int(r_lo), "max": int(r_hi) - (r_op == "미만"), "quote": q}
        lo = int(lo)
        if op in ("이하", "미만"):
            return {"type": "age", "min": None, "max": lo - (op == "미만"), "quote": q}
        return {"type": "age", "min": lo, "max": None, "quote": q}
    return None


def person_label(who: dict) -> str:
    if who["type"] == "age":
        lo, hi = who["min"], who["max"]
        return f"나이 만 {lo}~{hi}세" if lo is not None and hi is not None else f"나이 만 {lo}세 이상" if lo is not None else f"나이 만 {hi}세 이하"
    if who["type"] == "kids":
        return f"다자녀(18세 이하 자녀 {who['min']}명 이상 기준)" if who.get("maybe_from") else f"18세 이하 자녀 {who['min']}명 이상"
    return " 또는 ".join(PERSON[f] for f in who["flags"])


def judge_person(who: dict, age: int, kids: int | None, flags: set[str]) -> tuple[str, float | None]:
    """(met | not_met | unknown, 명수별 우대가 있으면 그 금리). 나이는 계좌 주인 나이로 확실히 판정.
    자녀 수는 가족이 '없음·1·2·3명 이상'을 고르면 판정, '모름'이면 unknown. 다른 조건은 고르면 met, 안 고르면 unknown(not_met 아님)."""
    if who["type"] == "age":
        ok = (who["min"] is None or age >= who["min"]) and (who["max"] is None or age <= who["max"])
        return ("met" if ok else "not_met"), None
    if who["type"] == "kids":
        if kids is None:
            return "unknown", None
        if kids >= who["min"]:
            hit = [pp for n, pp in (who["tiers"] or []) if kids >= n]
            return "met", (max(hit) if hit else None)
        return ("unknown" if who.get("maybe_from") and kids >= who["maybe_from"] else "not_met"), None
    return ("met" if set(who["flags"]) & flags else "unknown"), None


_AGE = re.compile(r"(?:만\s*)?(\d+)\s*세?\s*[~∼-]\s*(?:만\s*)?(\d+)\s*세\s*(이하|미만)?|(?:만\s*)?(\d+)\s*세\s*(이상|이하|미만|초과)?")


def parse_eligibility(join_member: str, join_deny: str) -> dict:
    """가입대상 글 + 가입제한 코드 → 판정할 수 있는 조건과 알 수 없는 조건."""
    t = join_member or ""
    conds, unknown = [], []
    parent = re.search(r"부모|자녀를?\s*둔|자녀의|자녀가", t)  # 부모도 가입할 수 있는 상품(자녀 적금 등)
    for m in _AGE.finditer(t):
        r_lo, r_hi, r_op, lo, op1 = m.groups()  # "19~39세"·"1~19세"처럼 앞 숫자에 '세'가 없는 범위도 범위로 읽는다
        lo, hi, op2 = (r_lo, r_hi, r_op) if r_lo else (lo, None, None)
        q = m.group(0)
        if re.match(r"\s*(의\s*)?(미성년\s*)?(다자녀|자녀|아동|가구원|손자)", t[m.end():]):
            continue  # "만 18세이하 다자녀를 둔 부모": 자녀 나이지 가입하는 사람 나이가 아니다
        if hi:
            conds.append({"var": "age", "op": ">=", "value": int(lo), "quote": q})
            conds.append({"var": "age", "op": "<=" if op2 != "미만" else "<", "value": int(hi), "quote": q})
        else:
            op = {"이상": ">=", "이하": "<=", "미만": "<", "초과": ">", None: ">="}[op1]
            conds.append({"var": "age", "op": op, "value": int(lo), "quote": q})
    if conds and _composite(t):  # "기초생활수급자, 소년소녀가장, …, 만65세이상 차상위계층, …": 나이는 여러 대상 중 하나에만 걸린다
        conds = []
        unknown.append({"var": "여러 대상 중 하나", "quote": t.strip()[:60]})
    if parent:  # "-만 18세 이하 본인 -만 18세 이하 자녀를 둔 부모": 나이 상한은 자녀 본인 가입 쪽이라 부모를 빼면 안 된다
        conds = [c for c in conds if c["op"] in (">=", ">")]
    entity = {"individual": bool(re.search(r"개인|제한\s*없|누구나|거래대상자는\s*제한|내국인|실명", t)) or not t,
              "sole_proprietor": "excluded" if re.search(r"개인사업자\s*(는\s*)?제외", t)  # "개인(개인사업자 제외)"를 먼저 본다
              else "included" if re.search(r"개인\s*(및|과|\()?\s*개인사업자|개인사업자\s*포함", t) else "unknown"}
    for kw in ("청년", "서민", "장애", "기초생활", "다자녀", "한부모", "외국인", "임직원", "학생", "군인", "사업자등록", "근로자", "자녀", "부모", "여성", "남성"):
        if kw == "외국인" and not re.search(r"외국인\s*(전용|만|대상\s*상품)", t):
            continue  # "비거주 외국인 외 제한없음", "내·외국인 대상": 제외 문구라 가족마다 다른 조건이 아니다
        if kw in t and not (kw == "청년" and conds):
            unknown.append({"var": kw, "quote": kw})
    if re.search(r"무주택", t):
        unknown.append({"var": "무주택", "quote": re.search(r"무주택\s*\S*", t).group(0)})
    who = person_rule(t) if not re.search(r"하나\s*이상|또는|본인|및\s*자녀", t) else None
    if who and who["type"] == "kids":  # "만 18세이하 다자녀를 둔 부모"처럼 자녀 조건 하나뿐인 가입대상
        unknown = [u for u in unknown if u["var"] not in ("자녀", "부모", "다자녀")] + [{"var": "자녀 수", "quote": who["quote"], "who": who}]
    if re.search(r"보유한|보유\s*고객|통장\s*보유", t):
        unknown.append({"var": "다른 상품 보유", "quote": re.search(r"[^\s,]*\s*[^\s,]*\s*(보유한|보유\s*고객|통장\s*보유)", t).group(0)})
    if join_deny == "2":
        unknown.append({"var": "서민전용", "quote": "가입제한 2(서민전용)"})
    elif join_deny == "3":
        unknown.append({"var": "일부제한", "quote": "가입제한 3(일부제한)"})
    return {"conditions": conds, "unknown": unknown, "entity": entity, "one_per_person": bool(re.search(r"1\s*인\s*1\s*계좌", t))}


_AMOUNT = r"\d[\d,.]*\s*[천백십만억]*\s*원"
_MONTHLY = re.compile(r"월\s*(?:별\s*)?(?:납입한도\s*)?(?:최고\s*)?(?:" + _AMOUNT + r"\s*(?:이상|~|∼)\s*)?(" + _AMOUNT + r")\s*(이내|이하|까지)")
_MONTHLY_KEY = re.compile(r"(?:월\s*(?:가입\s*한도|최대\s*불입액|최대\s*납입액|불입\s*한도|납입\s*한도|가입한도)\s*[:：]?\s*(?:최대\s*)?|최대\s*월\s*)(" + _AMOUNT + r")")
_NO_MONTHLY_LIMIT = re.compile(r"월부금\s*제한\s*없음|월\s*불입(?:액)?\s*제한\s*없음|납입\s*한도\s*(?:는\s*)?(?:제한\s*)?없음|최고\s*금액은\s*제한\s*없음")


def to_manwon(s: str) -> float | None:
    """'50만원' 50, '1천만원' 1000, '5백만원' 500, '1천원' 0.1, '1백만원' 100."""
    m = re.fullmatch(r"\s*(\d[\d,.]*)\s*([천백십]?)\s*(만|억)?\s*원\s*", s)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    n *= {"천": 1000, "백": 100, "십": 10, "": 1}[m.group(2)]
    unit = m.group(3)
    return round(n * 10000 if unit == "억" else n if unit == "만" else n / 10000, 4)


def parse_limits(etc_note: str, join_member: str) -> dict:
    t = (etc_note or "") + "\n" + (join_member or "")
    m = _MONTHLY.search(t) or _MONTHLY_KEY.search(t)
    if m and to_manwon(m.group(1)) is not None:
        return {"monthly_max_manwon": to_manwon(m.group(1)), "quote": m.group(0), "unlimited": False}
    u = _NO_MONTHLY_LIMIT.search(t)  # "월부금제한없음", "최고금액은 제한없음": 월 한도가 없다고 적혀 있음
    return {"monthly_max_manwon": None, "quote": u.group(0) if u else None, "unlimited": bool(u)}


def check_product(p: dict) -> dict:
    """상품 하나의 조건 규칙 + 검사 결과."""
    texts = p.get("texts", {})
    raw = texts.get("spcl_cnd") or ""
    ben = parse_benefits(raw)
    elig = parse_eligibility(texts.get("join_member", ""), p["join_deny"]["code"])
    limits = parse_limits(texts.get("etc_note", ""), texts.get("join_member", ""))
    for it in ben["items"]:  # G3·G4: 검사가 깨지면 코드가 잘못된 것이라 바로 멈춘다
        assert it["quote"] in raw and all(d in raw for d in it.get("details", []) + it.get("more_quotes", []))
        if it["add_pp"] is not None:
            q = " ".join([it["quote"], it.get("shared_quote", "")] + it.get("more_quotes", []))
            nums = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", q)}
            assert it["add_pp"] in nums or it.get("summed") and it["add_pp"] == round(sum(b for _, b in _amounts(q)), 2)
    assert all(c["quote"] in raw for c in ben["caps"]) and all(n in raw for n in ben["notes"])
    for c in elig["conditions"]:
        assert c["quote"] in texts.get("join_member", "")
    gaps = [round(o["max_rate"] - o["base_rate"], 2) for o in p["options"] if o["max_rate"] is not None]
    disclosed = max(gaps) if gaps else 0.0
    total = reachable(ben["items"])
    cap = max((c["cap_pp"] for c in ben["caps"]), default=None)  # 여러 상한 줄이면 가장 큰 것이 전체 상한(나머지는 부분 상한)
    reach = round(min(total, cap), 2) if cap is not None and ben["items"] else (cap or 0.0) if cap is not None else total
    issues, benefit_status = [], "verified"
    if ben["none"] or not ben["items"] and cap is None and disclosed <= 0.005:
        if disclosed > 0.005:
            issues.append(f"우대조건이 없다고 적혀 있는데 공시 최고 우대금리가 기본보다 {disclosed}%p 높음")
    else:
        if not ben["items"]:
            issues.append("우대 항목을 나누지 못함(원문에 세부 조건이 없음)")
        bad = [it for it in ben["items"] if it["issues"]]
        if bad:
            issues.append(f"읽지 못한 항목 {len(bad)}개")
        if reach < disclosed - 0.051:  # G5: 공시보다 적게 뽑힘 = 빠진 항목
            issues.append(f"뽑은 우대 {reach}%p < 공시 최고 우대 {disclosed}%p")
        elif reach > disclosed + 0.051 and disclosed <= 0.005:  # 원문에는 우대가 있는데 공시 최고금리 = 기본금리: 어느 쪽이 맞는지 모름
            issues.append(f"원문 우대 최대 {reach}%p인데 공시 최고 우대금리가 기본금리와 같음")
        elif reach > disclosed + 0.051 and not issues:
            benefit_status = "capped"  # 택일·단계형이 섞여 합이 공시보다 큼. 공시 최고 우대로 제한해 쓴다
    if issues:
        benefit_status = "needs_check"
    elig_issues = ["가입대상에 판정할 수 없는 조건: " + ", ".join(u["var"] for u in elig["unknown"])] if elig["unknown"] else []
    eligibility_status = "needs_check" if elig_issues else "verified"
    issues += elig_issues
    status = "needs_check" if "needs_check" in (benefit_status, eligibility_status) else benefit_status
    caveats = sorted({it["caveat"] for it in ben["items"] if it.get("caveat")}) + ben["notes"]
    return {
        "product_id": p["product_id"], "source_id": p["source_id"],
        "eligibility": elig, "benefits": ben["items"], "benefit_caps": ben["caps"], "limits": limits,
        "check": {"items_reachable_pp": total, "cap_pp": cap, "reachable_pp": reach, "disclosed_bonus_pp": disclosed,
                  "caveats": caveats},
        "status": status, "benefit_status": benefit_status, "eligibility_status": eligibility_status, "issues": issues,
    }


def build(products: list[dict]) -> dict:
    recs = [check_product(p) for p in products]
    count = {s: sum(r["status"] == s for r in recs) for s in ("verified", "capped", "needs_check")}
    count["benefit"] = {s: sum(r["benefit_status"] == s for r in recs) for s in ("verified", "capped", "needs_check")}
    count["eligibility_needs_check"] = sum(r["eligibility_status"] != "verified" for r in recs)
    return {
        "_note": "개발용(dev_only). 상품 노드의 우대조건·가입대상 글에서 코드가 뽑은 조건 규칙(ontology/conditions.py). "
                 "verified는 그대로, capped는 공시 최고 우대금리를 상한으로 쓰고, needs_check는 화면에서 '확인 필요'.",
        "tags": TAG,
        "summary": {"products": len(recs), **count},
        "products": recs,
    }
