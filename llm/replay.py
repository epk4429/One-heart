"""개발용 재생 공급자(LLM_PROVIDER=replay). 실제 LLM이 아니다.

역할별 입력(구조화된 dict)을 보고 규칙으로 그럴듯한 출력을 만든다. 어떤 가족을 넣어도 화면·API·엔진 배선을
돈 들이지 않고 끝까지 확인하기 위한 것이다. 화면 하단에 "AI: 재생(개발용) — 실제 LLM 아님"이 표시된다.
"""

from __future__ import annotations

import json
import re

from verify import find_numbers

from .providers import LLMResult


def _clip(t: str, n: int = 25) -> str:
    t = re.sub(r"\s+", " ", str(t)).strip().rstrip(".")
    return t if len(t) <= n else t[: n - 1] + "…"


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?요다])\s+", t or "") if s.strip()]


def _r1a(i):
    story = i["story"]
    ss = _sentences(story)
    living = next((s for s in ss if any(k in s for k in ("전세", "월세", "자가", "아파트", "집에"))), "")
    goal = next((s for s in ss if "싶" in s), i.get("reason") or "")
    diffs = [s for s in ss if any(k in s for k in ("쪽", "생각", "갈리", "반대", "부담", "걱정"))][:3]
    ages = sorted(m["age"] for m in i["members"])
    return {"family_stage": f"{len(i['members'])}명 가족 · {ages[0]}~{ages[-1]}세",
            "living": _clip(living) if living else "아직 이야기하지 않았어요",
            "shared_goal": _clip(goal) if goal else "아직 이야기하지 않았어요",
            "differences": [_clip(d, 20) for d in diffs] or ["무엇을 먼저 할지"],
            "member_questions": _member_questions(i, ss)}


MQ_RULES = [  # (이야기 속 말, 질문, 쉬운 질문)
    ("휴직", "휴직은 몇 개월쯤 생각하세요?", "휴직은 얼마나 하실 거예요?"),
    ("아이를", "아이는 언제쯤 갖고 싶으세요?", "아이는 언제쯤이 좋으세요?"),
    ("전세 만기", "전세 만기 뒤에는 어디서 살고 싶으세요?", "만기 뒤엔 어디 살고 싶으세요?"),
    ("병원비", "병원비는 한 달에 얼마쯤 드는지 아세요?", "병원비가 한 달에 얼마예요?"),
    ("간병", "간병이 필요해지면 어떻게 하고 싶으세요?", "간병은 어떻게 하고 싶으세요?"),
]


def _member_questions(i, ss):
    """이야기 속 말에 맞춘 질문. 문장에 이름·역할이 나온 사람에게, 아무도 안 나오면 성인 모두에게. 한 사람 2개까지."""
    out, per = [], {}
    for word, text, easy in MQ_RULES:
        sent = next((x for x in ss if word in x), None)
        if not sent:
            continue
        who = [m for m in i["members"] if m["name"] in sent or m["role"] in sent] or [m for m in i["members"] if m["age"] >= 19]
        for m in who:
            if per.get(m["member_id"], 0) < 2:
                per[m["member_id"]] = per.get(m["member_id"], 0) + 1
                out.append({"member_id": m["member_id"], "text": text, "easy": easy, "from": word})
    return out


def _r1b(i):
    ans = [a for _, a in i["qa"]] + ["", "", ""]
    out = {"keep": _clip(ans[0]) or "아직 말하지 않았어요", "worry": _clip(ans[1]) or "아직 말하지 않았어요",
           "flexible": _clip(ans[2]) or "아직 말하지 않았어요", "ambiguous": [], "question": "", "easy_question": "",
           "choices": [], "details": list(dict.fromkeys(_clip(x, 30) for x in ans[3:5] if x.strip() and "정하지 못" not in x))}
    if i.get("clarification"):
        out["keep"] = _clip(i["clarification"]["meaning"])
        return out
    text = " ".join(ans)
    if "집" in text and any(k in text for k in ("물려", "지키", "지킨")):
        out["ambiguous"] = [{"word": "집을 지킨다", "why": "사시는 것과 물려주는 것은 계산이 달라요",
                             "candidates": ["살아 있는 동안 이 집에 산다", "자녀에게 물려준다"]}]
        out["question"] = "'집'을 지키고 싶다고 하셨는데, 이 집에 계속 사시는 것과 물려주시는 것 중 어느 쪽에 더 가까우세요?"
        out["easy_question"] = "아래에서 마음에 가장 가까운 것을 하나만 눌러 주세요."
        out["choices"] = ["내가 살아 있는 동안 이 집에서 살고 싶다", "자식에게 이 집을 꼭 물려주고 싶다",
                          "지금은 잘 모르겠다 (나중에 답하기)"]
    return out


def _r2b(i):
    a = i["answer"]
    if "나중에" in a or "모르" in a and len(a) < 12:
        return {"resolved": False, "meaning": "", "confirm_message": "괜찮아요. 편하실 때 다시 여쭤볼게요."}
    return {"resolved": True, "meaning": _clip(a, 30),
            "confirm_message": f"알겠습니다. '{_clip(a, 30)}'이 가장 중요하다고 정리할게요. 맞으신가요?"}


def _agreed_points(i) -> list[str]:
    """금융 목표와 직접 관련된 공통점: 고른 목표 + 모두가 확인한 가장 큰 걱정."""
    pts = []
    for d in (i.get("goal_details") or [])[:1]:
        pts.append(f"가족이 함께 이루려는 목표는 같아요 ({_clip(str(d), 40)})")
    worries = [(v or {}).get("worry") for v in (i.get("summaries") or {}).values()]
    worries = [w for w in worries if w]
    if worries:
        pts.append(f"돈 문제로 걱정되는 점이 있어요 ({_clip(worries[0], 30)})")
    return pts or ["정한 목표를 가족의 돈 계획으로 함께 이루고 싶어 해요"]


def _r3(i):
    sums = i["summaries"]
    stances = {m["member_id"]: _clip((sums.get(m["member_id"]) or {}).get("keep") or "함께 정하고 싶어요", 28) for m in i["members"]}
    return {"headline": "가족 모두 함께 계획을 세우고 싶어 해요. 무엇을 먼저 할지가 조금 달라요.",
            "agreed_points": _agreed_points(i),
            "issues": [{"title": "무엇을 먼저 할까", "kind": "order", "stances": stances,
                        "shared": "서로가 지키고 싶은 것을 함께 지키는 것"}]}


def _tip_tag(i, k: int, phrase: str) -> str:
    """받은 꿀팁 조각(tips) 중 k번째에서 숫자·표시 글자가 없는 한 줄(15~80자)을 그대로 떼어 근거 표시를 만든다. 없으면 빈 글."""
    tips = i.get("tips") or []
    if not tips or not phrase:
        return ""
    for t in tips[k % len(tips):] + tips[: k % len(tips)]:
        for line in t["text"].split("\n"):
            q = line.strip(" □◦◈☞-*·")
            if 15 <= len(q) <= 80 and not re.search(r"[\d|\[\]]", q):
                return f"[[tip:{t['tip_id']}|{phrase}|{q}]] "
    return ""


def _covers(i) -> dict:
    sums = i["summaries"]
    return {m["member_id"]: _clip((sums.get(m["member_id"]) or {}).get("keep") or "함께 정하고 싶은 것", 22) + "을(를) 지키는 조건으로 정해요"
            for m in i["members"]}


def _r4a(i):
    lead = _tip_tag(i, 0, "금융감독원 금융꿀팁이 알려 주는 기본 원칙이라서")
    return {"proposal": "각자 꼭 지키고 싶다고 한 것을 모두 지키는 조건을 먼저 정하고, 그 조건이 채워지는 때를 함께 정해 보면 어떨까요?",
            "reasons": [lead + "서로 지키고 싶은 것이 달라서 순서보다 조건으로 정하는 편이 모두를 챙길 수 있어요",
                        "함께 정한 목표를 이루려면 필요한 돈이 모이는 때가 분명해야 해서"],
            "covers": _covers(i), "to": [m["member_id"] for m in i["members"]]}


def _r4c(i):
    last = i["rounds"][-1]["replies"]
    names = {m["member_id"]: m["name"] for m in i["members"]}
    spk = {m: r for m, r in last.items() if r.get("v") != "good"}
    cond = ", ".join(f"{names.get(m, '가족')}님의 '{_clip(r.get('text', ''), 24)}'" for m, r in spk.items()) or "가족의 의견"
    lead = _tip_tag(i, 1, "금융감독원 금융꿀팁이 알려 주는 기본 원칙이라서")
    return {"proposal": f"앞 제안에 {cond}을(를) 조건으로 더해서, 모두가 지키고 싶은 것을 함께 지키는 기준으로 정해 보면 어떨까요?",
            "reasons": [lead + "의견을 낸 분의 지키고 싶은 것을 조건으로 넣으면 모두가 받아들이기 쉬워서",
                        "이미 좋다고 한 분의 지키고 싶은 것도 그대로 지켜져서"],
            "covers": _covers(i),
            "heard": {m: f"'{_clip(r.get('text', ''), 24)}'을(를) 이번 제안의 조건으로 넣었어요" for m, r in spk.items()},
            "changed": "의견을 낸 분의 조건을 제안에 더했어요", "to": [m["member_id"] for m in i["members"]]}


def _r4d(i):
    last = i["rounds"][-1]["replies"]
    sums = i["summaries"]
    stances = {}
    for m in i["members"]:
        r = last.get(m["member_id"]) or {}
        stances[m["member_id"]] = _clip(r.get("text") or (sums.get(m["member_id"]) or {}).get("keep") or "제안대로 괜찮아요", 28)
    return {"message": "아직 서로 다르게 바라는 부분이 있어요. 아래 부분에 대해 서로 이야기를 나눠 보면 좋겠어요.",
            "topics": [{"title": "무엇을 더 지켜야 할까", "kind": "value", "stances": stances,
                        "shared": "모두 가족이 함께 지내는 것을 지키고 싶어 해요"}]}


def _r4b(i):
    fg = i.get("fixed_goal")
    if fg:
        ids = {f["fact_id"] for f in i["facts"]}
        note = ("지금처럼 모으면 5년 뒤 {{fact:size.after_5y}}이 돼요. 각자 지키고 싶은 것을 해치지 않는 선에서 금액과 기한을 정해 보세요."
                if "size.after_5y" in ids else
                "지금 상환대로면 대출은 {{fact:size.payoff}} 다 갚아요. 생활이 흔들리지 않는 선에서 기한을 정해 보세요."
                if "size.payoff" in ids else
                "지금 한 달 생활비는 {{fact:size.expense}}예요. 이 금액을 기준으로 은퇴 후 필요한 돈을 정해 보세요."
                if "size.expense" in ids else "")
        return {"criterion": "각자 꼭 지키고 싶은 것을 모두 지키면서, 정한 목표를 향해 함께 나아가요.", "size_note": note}
    text = " ".join(list(i["replies"].values()) + [s.get("keep", "") for s in i["summaries"].values()])
    oldest = max(i["members"], key=lambda m: m["age"])
    nums = [f for f in i["facts"] if f["fact_id"].startswith("item.")]
    goal = {"type": "reach_target", "label": "함께 정한 목표 금액 모으기", "target_amount": None, "target_source": None,
            "within_months": None, "base_member_id": None}
    if oldest["age"] >= 60:
        goal.update(type="runway", label="예금으로 지낼 수 있는 기간", base_member_id=oldest["member_id"])
    elif i["has_repaying_loans"] and any(k in text for k in ("빚", "대출", "갚")):
        goal.update(type="debt_free", label="대출 다 갚기")
    else:
        money = [h.value for h in find_numbers(text) if h.kind == "money"]
        if money:
            goal.update(target_amount=max(money), target_source="가족의 말")
        m = re.search(r"(\d+)\s*년\s*안", text)
        if m:
            goal["within_months"] = int(m.group(1)) * 12
    del nums
    return {"criterion": "가족 모두가 꼭 지키고 싶은 것을 지키면서 목표를 이루는 때를 계산해요.", "goal": goal}


def _spec(oid, label, desc, ret, **kw):
    return {"option_id": oid, "label": label, "description": desc, "return_id": ret,
            "monthly_changes": kw.get("mc", []), "adjustments": kw.get("adj", []), "events": kw.get("ev", []),
            "lump_sums": [], "policies": kw.get("pol", [])}


def _r5(i):
    ctx = i["context"]
    lim = ctx["limits"]["monthly_adjustment_abs_max"]
    pols = {p["policy"]: p for p in ctx["policies"]}
    t = i["goal_full"]["type"]
    cut, spend = min(50, lim), min(100, lim)
    a = _spec("A", "목표 먼저", "지출을 조금 줄이고 조금 더 불어나는 곳에 넣어요.", "stock30",
              adj=[{"label": "여유 지출 줄이기", "amount": cut, "reason": "목표를 빨리 이루기 위해"}])
    b = _spec("B", "함께 챙기기", "지금 생활은 지키고, 원금이 줄지 않는 곳 위주로 모아요.", "deposit_heavy")
    c = _spec("C", "지금 여유 먼저", "지금 생활의 여유를 늘리고, 불어날 수 있는 곳에 넣어요.", "stock_heavy",
              adj=[{"label": "여유 지출", "amount": -spend, "reason": "지금의 여유를 위해"}])
    if t == "runway":
        a = _spec("A", "지금 그대로", "집은 그대로 두고 예금으로 생활해요.", "safe")
        b = _spec("B", "집에 살면서 연금 받기" if "reverse_mortgage" in pols else "생활비 조금 아끼기",
                  "지금 집에 계속 살면서 매달 생활비를 더 받아요." if "reverse_mortgage" in pols else "생활비를 조금 줄여요.",
                  "safe", pol=[{"policy": "reverse_mortgage", "from_month": 1}] if "reverse_mortgage" in pols else [],
                  adj=[] if "reverse_mortgage" in pols else [{"label": "생활비 아끼기", "amount": cut, "reason": "예금을 오래 쓰기 위해"}])
        c = _spec("C", "작은 집으로" if "sell_home" in pols else "더 불리기",
                  "작은 집으로 옮기고 남는 돈을 생활비로 써요." if "sell_home" in pols else "조금 더 불어나는 곳에 넣어요.",
                  "safe" if "sell_home" in pols else "deposit_heavy",
                  pol=[{"policy": "sell_home", "month": 6, "new_home_ratio": 0.6}] if "sell_home" in pols else [])
    elif t == "debt_free":
        loan = next(p for p in ctx["policies"] if p["policy"] == "extra_repayment")
        a = _spec("A", "빚 먼저", "매달 대출을 더 갚아요.", "safe",
                  pol=[{"policy": "extra_repayment", "item_id": loan["params"]["item_id"], "amount": cut}])
    return {"options": [a, b, c], "design_notes": [{"option_id": o, "intent": x, "why": w} for o, x, w in
                                                   zip("ABC", ["목표 우선", "균형", "현재 여유"], _why5(i, t))]}


WHY5 = {  # 목표 종류 → 방법 A·B·C의 근거(근거 문구, 뒷말). 근거 문구가 있으면 받은 꿀팁 조각에서 원문 한 줄을 인용해 붙인다
    "reach_target": [("꼭 써야 하는 지출을 먼저 챙기고 남는 돈으로 모으는 게 기본이라서", "여유 지출을 조금 줄여 더 모아요."),
                     ("쓸 시기가 가까운 돈은 안전한 곳에 두는 게 원칙이라서", "예금·적금 위주로 모아요."),
                     (None, "지금 생활의 여유를 먼저 지키는 방법이에요.")],
    "runway": [("갑자기 쓸 돈은 바로 꺼낼 수 있게 두는 게 기본이라서", "집은 그대로 두고 예금으로 생활해요."),
               ("생활비 쓰임새에 맞춰 돈을 나눠 두는 게 도움이 돼서", "지금 집에 계속 사시는 걸 지켜요."),
               (None, "다른 두 방법과 비교해 볼 수 있게 만든 방법이에요.")],
    "debt_free": [("빚은 갚을 수 있는 만큼만 지는 게 기본이라서", "매달 조금 더 갚아 빨리 줄여요."),
                  ("갑자기 쓸 돈은 바로 꺼낼 수 있게 따로 두는 게 기본이라서", "비상금을 지키면서 갚아요."),
                  (None, "지금 생활의 여유를 먼저 지키는 방법이에요.")],
}


def _why5(i, t):
    return [_tip_tag(i, k, phrase) + tail for k, (phrase, tail) in enumerate(WHY5[t])]


def _r5r(i):
    nos = {o["option_id"]: sum(1 for st in i["stances"].values() if (st.get(o["option_id"]) or {}).get("v") == "no")
           for o in i["options"]}
    base = min(i["options"], key=lambda o: nos[o["option_id"]])
    spec = dict(base["spec"])
    order = ["safe", "deposit_heavy", "stock20", "stock30", "stock_heavy"]
    before = spec["return_id"]
    k = order.index(before)
    spec["return_id"] = order[k + 1] if k + 1 < len(order) else order[k - 1]
    who = next((m for m, st in i["stances"].items() if (st.get(base["option_id"]) or {}).get("v") == "no"), None)
    return {"from_option_id": base["option_id"], "label": f"{base['label']} · 불리는 방식 조정안", "option": spec,
            "changes": [{"field": "돈을 불리는 방식", "before": before, "after": spec["return_id"], "reason_member_id": who or ""}],
            "why": "반대 이유를 반영해 방법의 뼈대는 그대로 두고 돈을 불리는 방식만 바꿨어요."}


def _r6a(i):
    word = {"reach_target": "목표에 닿아요", "runway": "예금으로 지낼 수 있어요", "debt_free": "대출을 다 갚아요"}[i["goal"]["type"]]
    return {"per_option": {o["option_id"]: {"easy": f"{o['option_id']}를 고르면 {{{{fact:{o['option_id']}.goal_hit_years}}}} 뒤에 {word}." if i["goal"]["type"] != "runway"
                                            else f"{o['option_id']}를 고르면 예금으로 {{{{fact:{o['option_id']}.goal_hit_years}}}} 지낼 수 있어요.",
                                            "per_member": {m["member_id"]: f"{m['name']}님이 지키고 싶은 것과 함께 살펴봐 주세요." for m in i["members"]}}
                           for o in i["options"]}}


def _r6b(i):
    return {"keep_check": {o["option_id"]: {k["member_id"]: {"ok": o["option_id"] != "C" or n % 2 == 0,
                                                             "reason": "결과: {{fact:%s.goal_hit_years}}" % o["option_id"]}
                                            for n, k in enumerate(i["keeps"])} for o in i["options"]},
            "note": "방법마다 각자 지키고 싶은 것이 지켜지는지 살펴봤어요. 어떤 방법으로 할지는 가족이 정해요."}


def _r7(i):
    cf = i["contribution_facts"]
    ids = [f["fact_id"] for f in cf]
    pick = ([x for x in ids if x == "agree.monthly_saving" or x.startswith("agree.extra.")] if "agree.monthly_saving" in ids
            else ids[:3])  # 매달 모이는 돈과 그 안에 든 항목을 함께 적지 않는다
    contrib = [{"label": f["label"], "fact_id": f["fact_id"]} for f in cf if f["fact_id"] in pick]
    coms = [{"text": "기준이 채워지면 함께 다시 모여 다음 걸음을 정해요.", "source": {"type": "goal_setting"}}]
    for c in i["conditions"]:
        coms.append({"text": _clip(c["text"], 60), "source": {"type": "condition", "member_id": c["member_id"]}})
    for mid, s in i["summaries"].items():
        if len(coms) >= 3:
            break
        coms.append({"text": f"'{_clip(s['keep'], 30)}'은 꼭 지켜요.", "source": {"type": "keep", "member_id": mid}})
    while len(coms) < 3:
        coms.append({"text": "정기 점검 때 약속을 함께 확인해요.", "source": {"type": "goal_setting"}})
    oid = i["option"]["option_id"]
    return {"goal": _clip(i["criterion"], 60), "target_amount_label": _goal_amount_text(i["goal"]), "contribution": contrib,
            "timing": "기준이 채워질 때", "review": {"interval_months": 6, "events": ["수입이 크게 바뀔 때"]},
            "change_conditions": ["6개월마다", "수입·지출이 크게 바뀔 때"], "commitments": coms[:6],
            "report": {"reasons": ["반대한 사람 없이 모인 방법이에요.", "가족이 붙인 조건을 약속으로 남겼어요."],
                       "outcomes": [{"label": {"reach_target": "목표 달성까지", "runway": "예금으로 지낼 수 있는 기간", "debt_free": "대출을 다 갚는 때"}[i["goal"]["type"]],
                                     "fact_id": f"{oid}.goal_hit_years"}],
                       "action_plan": [{"when": "이번 달", "what": "자동이체를 약속대로 설정해요."}]}}


def _goal_amount_text(goal: dict) -> str:
    """합의서 '목표 금액' 칸 예시 문구(목표 금액이 있으면 금액·기한, 없으면 목표 이름)."""
    target, within = goal.get("target"), goal.get("within_years")  # 역할 6b 입력(_goal_view): 금액은 이미 '3억원' 같은 글, 기한은 년
    if goal.get("type") != "reach_target" or not target:
        return goal["label"]
    return str(target) + (f", {within:g}년 안에" if within else "")


_KEY = [("집", "N_home_purchase_prep"), ("휴직", "N_leave_fund"), ("용돈", "N_shared_transfer_record"),
        ("보태", "N_shared_transfer_record"), ("병원", "N_medical_fund_separate"), ("간병", "N_care_cost_cover"),
        ("물려", "N_inheritance_planning"), ("주택연금", "N_living_income_at_home"), ("대출", "N_debt_repayment"),
        ("비상금", "N_emergency_fund"), ("교육", "N_education_fund"), ("노후", "N_retirement_income")]


def _r8(i):
    have = {n["id"] for n in i["vocab"]["needs"]}
    out = []
    for c in i["commitments"]:
        needs = sorted({nid for k, nid in _KEY if k in c["text"] and nid in have})[:2]
        out.append({"commitment_id": c["commitment_id"], "need_ids": needs, "constraint_ids": [], "why": "낱말 규칙(재생)"})
    return {"mappings": out}


_FN = {"1a": _r1a, "1b": _r1b, "2b": _r2b, "3": _r3, "4a": _r4a, "4b": _r4b, "4c": _r4c, "4d": _r4d, "5": _r5, "5r": _r5r,
       "6a": _r6a, "6b": _r6b, "7": _r7, "8": _r8}


class ReplayProvider:
    model = "replay(개발용)"

    def complete(self, system, messages, *, tools=None, role_key: str | None = None, inputs: dict | None = None,
                 **_kw) -> LLMResult:
        if role_key not in _FN or inputs is None:
            raise ValueError(f"재생 출력 없음: {role_key}")
        return LLMResult(text=json.dumps(_FN[role_key](inputs), ensure_ascii=False), model=self.model)

    def tool_result_message(self, call, content):
        return {"role": "tool", "content": content}
