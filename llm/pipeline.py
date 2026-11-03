"""단계별 흐름: 입력 조립(공개 범위) → 역할 호출 → 엔진 → 검증(docs/09 3절 API와 1:1).

각 함수는 검사된 가족 입력(family.validate 결과)과 그 단계에 필요한 상태만 받아 결과(dict)를 돌려준다.
서버는 상태를 저장하지 않는다.
공유 단계 역할(3~8)에는 대화 원문을 넣지 않는다(docs/03 A-2). 그 경계는 여기서만 지킨다.
"""

from __future__ import annotations

from engine import simulate
from engine.api import tool_summary
from engine.fmt import won
from ontology import cards
from ontology import load as load_ontology
from ontology import recommend as ontology_recommend
from verify import VerificationRecord, check_agreement, check_refs, find_numbers, verify_texts

from . import family as F
from .plan import PlanError, build_request, check_option, design_context, engine_option, normalize_goal
from .runner import run_role


# ---------- 공통 ----------
def _members(fam: dict) -> list[dict]:
    return [{"member_id": m["member_id"], "name": m["name"], "role": m["role"], "age": m["age"]}
            for m in fam["members"]]


def shared_summaries(summaries: dict, fam: dict) -> dict:
    """공유 단계에는 본인이 확인한 요약 세 칸과 맞춤 질문 답(details)만(구성원이 아닌 키·다른 필드는 버린다)."""
    mids = {m["member_id"] for m in fam["members"]}
    out = {}
    for mid, s in (summaries or {}).items():
        if mid in mids and isinstance(s, dict):
            out[mid] = {k: str(s.get(k, ""))[:80] for k in ("keep", "flexible", "worry")}
            det = [str(x)[:40] for x in (s.get("details") or []) if isinstance(x, str) and x.strip()][:2]
            if det:
                out[mid]["details"] = det  # 맞춤 질문 답에서 정한 것(본인 확인 요약의 일부)
    return out


def _user_texts(*objs) -> dict[str, str]:
    """가족이 직접 말한(입력한) 문장과 코드가 만든 설명. 검증 구조의 quote 허용 목록이 된다."""
    out, n = {}, 0

    def walk(o):
        nonlocal n
        if isinstance(o, str):
            out[f"u{n}"] = o
            n += 1
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    for o in objs:
        walk(o)
    return out


def _facts_for_llm(facts: dict) -> list[dict]:
    return [{"fact_id": k, "display": v["display"], "label": v.get("label", "")} for k, v in facts.items()]


def _overview(fam: dict) -> dict:
    p = F.profile(fam)
    return {"한 달 들어오는 돈": won(p["income_total"]), "한 달 나가는 돈(생활비·용돈)": won(p["expense_total"]),
            "한 달 대출 상환": won(p["loan_payment_total"]), "예금·투자": won(p["liquid_total"]),
            "전세 보증금": won(p["lease_deposit_total"]), "집 시세": won(p["home_total"]), "대출 잔액": won(p["loan_total"])}


def _fam_texts(fam: dict) -> list:
    """가족이 직접 넣은 글(이야기·이유·항목 이름)과 구성원 정보(인원·나이). 이 안의 숫자는 AI가 그대로 써도 된다."""
    ms = fam["members"]
    who = [f"{m['name']}({m['role']}, {m['age']}세)" for m in ms] + [f"가족 {len(ms)}명"]
    return [fam["story"]["text"], fam["room"]["reason"], [i["label"] for i in fam["finance"]], who]


# ---------- 화면 2: 가족 이야기 ----------
def story_understand(fam: dict, provider) -> dict:
    inp = {"story": fam["story"]["text"] or "(아직 쓰지 않았어요)", "today": F.today_label(fam),
           "reason": fam["room"]["reason"] or "(없음)", "members": _members(fam)}
    run = run_role("1a", inp, provider)
    out = {"run": run.__dict__}
    if run.ok:
        mq = [{k: str(q[k]).strip() for k in ("member_id", "text", "easy", "from")} for q in run.output.get("member_questions") or []]
        texts = {k: v for k, v in run.output.items() if isinstance(v, str)}
        texts.update({f"differences.{i}": d for i, d in enumerate(run.output["differences"])})
        texts.update({f"member_questions.{i}.{k}": q[k] for i, q in enumerate(mq) for k in ("text", "easy")})
        _, rec = verify_texts(texts, {}, role="1a", quotes=_user_texts(*_fam_texts(fam), _members(fam)))
        questions = {m["member_id"]: [{k: q[k] for k in ("text", "easy", "from")} for q in mq if q["member_id"] == m["member_id"]]
                     for m in fam["members"]}
        out.update(result={**run.output, "member_questions": questions}, verification=rec.to_dict())
    return out


# ---------- 화면 3: 각자의 생각 ----------
def _qa(qa) -> list[list[str]]:
    out = []
    for x in (qa or [])[:6]:
        if isinstance(x, (list, tuple)) and len(x) == 2:
            out.append([str(x[0])[:200], str(x[1])[:F.LIMITS["answer"]]])
    return out


def interview_review(fam: dict, mid: str, qa, provider, clarification: dict | None = None) -> dict:
    """1:1 대화 정리: 요약 + 말뜻 확인이 필요한 말(역할 1b). 원문 대화는 이 역할에만 들어간다."""
    qa = _qa(qa)
    if not qa:
        raise PlanError("대화 답이 없어요")
    clar = None
    if clarification:
        clar = {"word": str(clarification.get("word", ""))[:40], "meaning": str(clarification.get("meaning", ""))[:80]}
    run = run_role("1b", {"member": F.member(fam, mid), "qa": qa, "clarification": clar}, provider)
    out = {"run": run.__dict__}
    if run.ok:
        o = run.output
        details = [x.strip() for x in o.get("details") or []][:2]
        texts = {k: o[k] for k in ("keep", "flexible", "worry")} | {f"details.{n}": x for n, x in enumerate(details)}
        _, rec = verify_texts(texts, {}, role="1b", quotes=_user_texts(qa, clar))
        amb = o.get("ambiguous") or []
        out.update(result={"keep": o["keep"], "flexible": o["flexible"], "worry": o["worry"], "details": details,
                           "ambiguous": amb[:1],
                           "question": o.get("question", "") if amb else "",
                           "easy_question": o.get("easy_question", "") if amb else "",
                           "choices": (o.get("choices") or [])[:3] if amb else []},
                   verification=rec.to_dict())
    return out


def interview_resolve(fam: dict, mid: str, detect: dict, answer: str, provider) -> dict:
    amb = (detect.get("ambiguous") or [{}])[0]
    inp = {"member": F.member(fam, mid), "word": str(amb.get("word", ""))[:40],
           "easy_question": str(detect.get("easy_question", ""))[:200],
           "choices": [str(c)[:80] for c in (detect.get("choices") or [])[:3]], "answer": str(answer)[:F.LIMITS["answer"]]}
    run = run_role("2b", inp, provider)
    return {"run": run.__dict__, "result": run.output if run.ok else None}


# ---------- 화면 4: 공동 목표 설정 ----------
def goal_analyze(fam: dict, summaries: dict, story_understanding: dict, provider,
                 clarifications: list[dict] | None = None) -> dict:
    shared = shared_summaries(summaries, fam)
    su = {k: story_understanding.get(k) for k in ("family_stage", "living", "shared_goal", "differences")}
    r3 = run_role("3", {"members": _members(fam), "story_understanding": su, "summaries": shared,
                        "finance_overview": _overview(fam)}, provider)
    out = {"analysis_run": r3.__dict__}
    if not r3.ok:
        return out
    facts = F.facts(fam)
    clar = [{k: str(c.get(k, ""))[:80] for k in ("member_id", "word", "meaning")} for c in (clarifications or [])]
    given = cards.for_family(fam)  # 재무 원리 카드: 가족 정보로 고른 묶음만 준다(docs/12 5·6절)
    r4 = run_role("4a", {"members": _members(fam), "analysis": r3.output, "summaries": shared,
                         "clarifications": clar, "cards": cards.brief(given), "facts": _facts_for_llm(facts)}, provider)
    out["proposal_run"] = r4.__dict__
    quotes = _user_texts(shared, su, clar, *_fam_texts(fam), [c["text"] for c in given])  # 카드 설명의 숫자(예: 1~2년)는 근거 문구에 써도 된다
    texts = {"headline": r3.output["headline"]}
    texts.update({f"agreed_points.{i}": t for i, t in enumerate(r3.output["agreed_points"])})
    texts.update({f"issues.{i}.note": it["note"] for i, it in enumerate(r3.output["issues"])})
    if r4.ok:
        texts["proposal"] = r4.output["proposal"]
        texts.update({f"bridges.{i}": b["how"] for i, b in enumerate(r4.output.get("bridges", []))})
    rendered, rec = verify_texts(texts, facts, role="3+4a", quotes=quotes)
    issues = []
    for i, it in enumerate(r3.output["issues"]):
        pos = it["positions"]
        gap = max(pos.values()) - min(pos.values())
        issues.append({**it, "note": rendered.get(f"issues.{i}.note", it["note"]),
                       "gap_level": "large" if gap >= 0.6 else "medium" if gap >= 0.35 else "small"})
    out.update(result={"headline": rendered["headline"],
                       "agreed_points": [rendered[f"agreed_points.{i}"] for i in range(len(r3.output["agreed_points"]))],
                       "issues": issues,
                       "proposal": ({"text": rendered["proposal"], "to": r4.output["to"],
                                     "bridges": r4.output.get("bridges", []),
                                     "cards": [cards.view(c) for c in cards.used_ids(rendered["proposal"])]} if r4.ok else None)},
               verification=rec.to_dict())
    return out


def _traceable_amount(value: float, facts: dict, texts: list[str]) -> bool:
    """목표 금액이 가족 입력(facts)이나 가족의 말에 있는 숫자인지."""
    if any(isinstance(f.get("value"), (int, float)) and abs(f["value"] - value) <= 0.5 for f in facts.values()):
        return True
    return any(h.kind == "money" and abs(h.value - value) <= 0.5 for t in texts for h in find_numbers(t))


def goal_criterion(fam: dict, proposal_text: str, replies: dict, summaries: dict, provider,
                   story_understanding: dict | None = None) -> dict:
    facts = F.facts(fam)
    shared = shared_summaries(summaries, fam)
    mids = {m["member_id"] for m in fam["members"]}
    replies = {k: str(v)[:F.LIMITS["answer"]] for k, v in (replies or {}).items() if k in mids}
    proposal_text = cards.strip(str(proposal_text))[:400]  # 카드 근거 표시는 떼고 문장만
    has_loans = bool(F.profile(fam)["repaying_loans"])
    shared_goal = str((story_understanding or {}).get("shared_goal") or "")[:80]
    run = run_role("4b", {"members": _members(fam), "proposal": proposal_text, "replies": replies, "summaries": shared,
                          "facts": _facts_for_llm(facts), "has_repaying_loans": has_loans, "shared_goal": shared_goal}, provider)
    out = {"run": run.__dict__}
    if not run.ok:
        return out
    quotes = _user_texts(replies, proposal_text, shared, shared_goal, *_fam_texts(fam))
    rendered, rec = verify_texts({"criterion": run.output["criterion"]}, facts, role="4b", quotes=quotes)
    g = run.output["goal"]
    goal = {"type": g["type"], "label": str(g.get("label") or "")[:40] or None,
            "within_months": g.get("within_months") if isinstance(g.get("within_months"), int) else None,
            "base_member_id": g.get("base_member_id") if g.get("base_member_id") in mids else None,
            "target_amount": None, "target_note": None}
    ta = g.get("target_amount")
    if g["type"] == "reach_target" and isinstance(ta, (int, float)) and not isinstance(ta, bool) and ta > 0:
        if _traceable_amount(float(ta), facts, list(quotes.values())):
            goal["target_amount"] = round(float(ta), 1)
        else:
            rec.violations.append({"type": "untraceable_target", "text": f"{ta:g}만원", "severity": "warning",
                                   "path": "goal.target_amount"})
            goal["target_note"] = "AI가 근거를 찾지 못한 금액이라 비워 뒀어요. 가족이 정해 주세요."
    out.update(result={"criterion": rendered["criterion"], "criterion_raw": run.output["criterion"], "goal": goal},
               verification=rec.to_dict())
    return out


# ---------- 화면 5: 미래 계산 ----------
def _option_view(fam: dict, goal: dict, spec: dict, result: dict) -> dict:
    meta = engine_option(fam, goal, spec)["meta"]
    return {"option_id": result["option_id"], "label": spec.get("label"), "description": spec.get("description"),
            "changes": meta["changes"], "goal_hit": result["goal_hit_display"],
            "facts": [{"fact_id": f["fact_id"], "display": f["display"], "label": f.get("label", "")}
                      for f in result["facts"] if ".range." not in f["fact_id"]]}


def _goal_view(goal: dict) -> dict:
    v = {"type": goal["type"], "label": goal["label"], "start": won(goal["start_pool"]) + f"({goal['pool_label']})",
         "horizon_years": goal["horizon_months"] // 12}
    if goal.get("target_amount"):
        v["target"] = won(goal["target_amount"])
    if goal.get("within_months"):
        v["within_years"] = round(goal["within_months"] / 12, 1)
    return v


def _design_inputs(fam: dict, goal: dict, shared: dict) -> dict:
    return {"members": _members(fam), "summaries": shared, "finance": F.shared_finance(fam),
            "finance_overview": _overview(fam), "context": design_context(fam, goal), "goal": _goal_view(goal),
            "family": fam, "goal_full": goal}


def simulate_specs(fam: dict, goal: dict, specs: list[dict], *, include_monthly: bool = True) -> dict:
    return simulate(build_request(fam, goal, specs), include_monthly=include_monthly)


def options_design(fam: dict, goal_raw: dict, criterion: str, summaries: dict, provider, *, use_tools: bool = True) -> dict:
    goal = normalize_goal(fam, goal_raw)
    shared = shared_summaries(summaries, fam)

    def tool_handler(name: str, args: dict) -> dict:
        if name != "run_simulation":
            return {"error": "모르는 도구"}
        try:
            specs = [check_option(fam, goal, s) for s in (args.get("options") or [])]
            if not specs:
                return {"error": "options가 비었어요"}
            return tool_summary(simulate_specs(fam, goal, specs, include_monthly=False))
        except PlanError as e:
            return {"error": str(e)}

    tools = [{"name": "run_simulation",
              "description": "설계한 방법(options 배열, 최종 출력과 같은 형식)으로 미래 현금흐름과 목표 달성 시점을 계산한다. "
                             "형식이 틀리면 error로 이유를 알려 준다. 숫자는 이 결과만 쓴다.",
              "input_schema": {"type": "object", "properties": {"options": {"type": "array", "items": {"type": "object"}}},
                               "required": ["options"]}}] if use_tools else None
    given = cards.for_family(fam)  # 재무 원리 카드(근거는 design_notes.why 안에 녹인다)
    inp = {"criterion": str(criterion)[:300], **_design_inputs(fam, goal, shared), "cards": cards.brief(given)}
    r5 = run_role("5", inp, provider, tools=tools, tool_handler=tool_handler if use_tools else None)
    out = {"design_run": r5.__dict__}
    if not r5.ok:
        return out
    specs = [check_option(fam, goal, s) for s in r5.output["options"]]
    sim = simulate_specs(fam, goal, specs)
    if "error" in sim:
        out["error"] = sim["error"]
        return out
    by_id = {r["option_id"]: r for r in sim["results"]}
    views = [_option_view(fam, goal, s, by_id[s["option_id"]]) for s in specs]
    facts = {f["fact_id"]: f for r in sim["results"] for f in r["facts"]}
    r6 = run_role("6a", {"members": _members(fam), "summaries": shared, "options": views, "goal": _goal_view(goal)},
                  provider)
    out["interpret_run"] = r6.__dict__
    texts = {f"desc.{v['option_id']}": v["description"] or "" for v in views}
    texts.update({f"note.{n.get('option_id')}": str(n.get("intent", "")) for n in r5.output.get("design_notes", [])
                  if isinstance(n, dict)})
    texts.update({f"why.{n.get('option_id')}": str(n.get("why", "")) for n in r5.output.get("design_notes", [])
                  if isinstance(n, dict)})
    rate_texts = [x for r in inp["context"]["returns"] for x in (r["source"], f"{r['label']} 연 {r['expected_return']:g}%")]
    if r6.ok:
        for oid, v in r6.output["per_option"].items():
            texts[f"{oid}.easy"] = v["easy"]
            texts.update({f"{oid}.member.{m}": t for m, t in v["per_member"].items()})
    rendered, rec = verify_texts(texts, facts, role="5+6a", run_id=sim["run_id"],
                                 quotes=_user_texts(shared, views, *_fam_texts(fam), [c["text"] for c in given], rate_texts))
    notes = []
    for n in r5.output.get("design_notes", []):
        if isinstance(n, dict):
            why = rendered.get(f"why.{n.get('option_id')}", "")
            notes.append({"option_id": n.get("option_id"), "intent": rendered.get(f"note.{n.get('option_id')}", ""),
                          "why": why, "cards": [cards.view(c) for c in cards.used_ids(why)]})
    out.update(specs=specs, goal=goal, design_notes=notes, simulation=sim,
               views=[{"option_id": v["option_id"], "changes": v["changes"]} for v in views],
               interpretation={oid: {"easy": rendered.get(f"{oid}.easy"),
                                     "per_member": {m: rendered.get(f"{oid}.member.{m}") for m in
                                                    r6.output["per_option"][oid]["per_member"]}}
                               for oid in by_id} if r6.ok else None,
               verification=rec.to_dict())
    return out


# ---------- 화면 6: 합의안 ----------
def agreement_check(fam: dict, goal: dict, specs: list[dict], sim: dict, summaries: dict, provider) -> dict:
    by_id = {r["option_id"]: r for r in sim["results"]}
    views = [_option_view(fam, goal, s, by_id[s["option_id"]]) for s in specs]
    shared = shared_summaries(summaries, fam)
    keeps = [{"member_id": m, "name": F.member(fam, m)["name"], "keep": s["keep"]} for m, s in shared.items()]
    ffacts = F.facts(fam, goal)
    run = run_role("6b", {"keeps": keeps, "options": views, "goal": _goal_view(goal),
                          "family_facts": _facts_for_llm(ffacts)}, provider)
    out = {"run": run.__dict__}
    if run.ok:
        facts = {f["fact_id"]: f for r in sim["results"] for f in r["facts"]} | ffacts
        texts = {"note": run.output["note"]}
        for oid, row in run.output["keep_check"].items():
            texts.update({f"{oid}.{m}": c.get("reason", "") for m, c in row.items()})
        rendered, rec = verify_texts(texts, facts, role="6b", run_id=sim["run_id"],
                                     quotes=_user_texts(keeps, views, *_fam_texts(fam)))
        kc = {oid: {m: {"ok": c["ok"], "reason": rendered[f"{oid}.{m}"]} for m, c in row.items()}
              for oid, row in run.output["keep_check"].items()}
        out.update(result={"keep_check": kc, "note": rendered["note"]}, verification=rec.to_dict())
    return out


def _stances(stances: dict, fam: dict, option_ids: list[str]) -> dict:
    mids = {m["member_id"] for m in fam["members"]}
    out = {}
    for mid, row in (stances or {}).items():
        if mid not in mids or not isinstance(row, dict):
            continue
        out[mid] = {oid: {"v": x.get("v"), "text": str(x.get("text", ""))[:F.LIMITS["answer"]]}
                    for oid, x in row.items() if oid in option_ids and isinstance(x, dict) and x.get("v") in ("good", "cond", "no")}
    return out


def agreement_revise(fam: dict, goal: dict, specs: list[dict], sim: dict, stances: dict, summaries: dict, provider) -> dict:
    by_id = {r["option_id"]: r for r in sim["results"]}
    views = [_option_view(fam, goal, s, by_id[s["option_id"]]) | {"spec": s} for s in specs]
    shared = shared_summaries(summaries, fam)
    st = _stances(stances, fam, list(by_id))
    inp = {"options": views, "stances": st, "summaries": shared, "finance": F.shared_finance(fam),
           "context": design_context(fam, goal), "family": fam, "goal_full": goal}
    run = run_role("5r", inp, provider)
    out = {"run": run.__dict__}
    if not run.ok:
        return out
    o = run.output
    new_id = f"{o['from_option_id']}2"
    spec = check_option(fam, goal, {**o["option"], "option_id": new_id, "label": o["label"]}, allowed_ids=(new_id,))
    rsim = simulate_specs(fam, goal, [spec])
    facts = {f["fact_id"]: f for r in sim["results"] + rsim["results"] for f in r["facts"]}
    labels = {r["id"]: r["label"] for r in F.assumptions()["returns"]}  # 가정값 id는 화면에 이름으로
    raw_changes = [c for c in o["changes"] if isinstance(c, dict)][:6]
    texts = {"why": o["why"]}
    for n, c in enumerate(raw_changes):
        for k in ("field", "before", "after"):
            texts[f"c{n}.{k}"] = labels.get(str(c.get(k, "")), str(c.get(k, "")))
    rendered, rec = verify_texts(texts, facts, role="5r", run_id=rsim["run_id"],
                                 quotes=_user_texts(st, views, engine_option(fam, goal, spec)["meta"]["changes"],
                                                    *_fam_texts(fam)))
    changes = [{"field": rendered[f"c{n}.field"][:80], "before": rendered[f"c{n}.before"][:120],
                "after": rendered[f"c{n}.after"][:120], "reason_member_id": str(c.get("reason_member_id", ""))}
               for n, c in enumerate(raw_changes)]
    out.update(result={"from_option_id": o["from_option_id"], "label": o["label"], "spec": spec, "changes": changes,
                       "why": rendered["why"], "simulation": rsim,
                       "view_changes": engine_option(fam, goal, spec)["meta"]["changes"]},
               verification=rec.to_dict())
    return out


def contribution_facts(fam: dict, spec: dict, result: dict) -> list[dict]:
    """분담방식 후보 숫자: 매달 모이는 돈 + 가족끼리 주고받는 돈(보태는 돈·용돈) + 구성원과 연결된 조정 + 대출 더 갚기."""
    out = []
    if result["monthly_flow"] > 0:
        out.append(F._fact("agree.monthly_saving", result["monthly_flow"], "만원/월", "월 " + won(result["monthly_flow"]),
                           "매달 모이는 돈"))
    over = {c["item_id"]: c["amount"] for c in spec["monthly_changes"]}
    for it in fam["finance"]:
        if it["kind"] in ("transfer_in", "transfer_out") and it["owner_id"] != "joint":
            amt = over.get(it["item_id"], it["amount"])
            if amt and fam["disclosure"].get(it["item_id"], "share") == "share":
                name = F.member(fam, it["owner_id"])["name"]
                out.append(F._fact(f"agree.item.{it['item_id']}", amt, "만원/월", "월 " + won(amt), f"{name}님 · {it['label']}"))
    for j, a in enumerate(spec["adjustments"]):
        if a.get("member_id"):
            name = F.member(fam, a["member_id"])["name"]
            out.append(F._fact(f"agree.adj.{j}", abs(a["amount"]), "만원/월", "월 " + won(abs(a["amount"])),
                               f"{name}님 · {a['label']}"))
    for pol in spec["policies"]:
        if pol["policy"] == "extra_repayment":
            loan = next(i for i in fam["finance"] if i["item_id"] == pol["item_id"])
            out.append(F._fact(f"agree.extra.{pol['item_id']}", pol["amount"], "만원/월", "월 " + won(pol["amount"]),
                               f"{loan['label']} 더 갚기"))
    return out


def agreement_draft(fam: dict, goal: dict, criterion: str, spec: dict, result: dict, method_label: str,
                    conditions: list[dict], summaries: dict, provider, revision: dict | None = None,
                    version: int = 1) -> dict:
    cfacts = contribution_facts(fam, spec, result)
    facts = F.facts(fam, goal) | {f["fact_id"]: f for f in result["facts"]} | {f["fact_id"]: f for f in cfacts}
    view = _option_view(fam, goal, spec, result)
    shared = shared_summaries(summaries, fam)
    mids = {m["member_id"] for m in fam["members"]}
    conditions = [{"member_id": c["member_id"], "text": str(c.get("text", ""))[:F.LIMITS["answer"]]}
                  for c in (conditions or []) if isinstance(c, dict) and c.get("member_id") in mids]
    rv = None
    if revision:
        rv = {"label": str(revision.get("label", ""))[:60], "changes": revision.get("changes", [])[:5],
              "why": str(revision.get("why", ""))[:300]}
    inp = {"members": _members(fam), "today": F.today_label(fam), "criterion": str(criterion)[:300], "goal": _goal_view(goal),
           "option": view, "conditions": conditions, "revision": rv, "summaries": shared,
           "contribution_facts": _facts_for_llm({f["fact_id"]: f for f in cfacts}), "facts": _facts_for_llm(facts)}
    run = run_role("7", inp, provider)
    out = {"run": run.__dict__}
    if not run.ok:
        return out
    o = run.output
    texts = {"goal": o["goal"], "target_amount_label": o["target_amount_label"], "timing": o["timing"]}
    texts.update({f"change_conditions.{i}": t for i, t in enumerate(o["change_conditions"])})
    texts.update({f"commitments.{i}": c["text"] for i, c in enumerate(o["commitments"])})
    texts.update({f"review.events.{i}": t for i, t in enumerate(o["review"].get("events", []))})
    texts.update({f"report.reasons.{i}": t for i, t in enumerate(o["report"].get("reasons", []))})
    texts.update({f"report.action_plan.{i}": a.get("what", "") for i, a in enumerate(o["report"].get("action_plan", []))})
    texts.update({f"report.action_plan.{i}.when": str(a.get("when", "")) for i, a in enumerate(o["report"].get("action_plan", []))})
    texts.update({f"report.outcomes.{i}.label": str(x.get("label", "")) for i, x in enumerate(o["report"].get("outcomes", []))})
    texts.update({f"contribution.{i}": c.get("label", "") for i, c in enumerate(o["contribution"])})
    rendered, rec = verify_texts(texts, facts, role="7", run_id=None,
                                 quotes=_user_texts(conditions, criterion, shared, rv, view, *_fam_texts(fam)))
    contribution = []
    for i, c in enumerate(o["contribution"]):
        if "part_of" in c:
            contribution.append({"label": rendered[f"contribution.{i}"], "amount": float(c["amount"]), "part_of": c["part_of"]})
        elif c.get("fact_id") in facts:
            contribution.append({"label": rendered[f"contribution.{i}"], "amount": facts[c["fact_id"]]["value"],
                                 "fact_id": c["fact_id"]})
    interval = o["review"]["interval_months"]
    agreement = {
        "goal": rendered["goal"], "method": {"display_label": method_label, "monthly_flow": result["monthly_flow"]},
        "target_amount": {"label": rendered["target_amount_label"],
                          **({"value": goal["target_amount"]} if goal["type"] == "reach_target" else {})},
        "contribution": contribution, "timing": {"text": rendered["timing"]},
        "review": {"interval_months": interval, "interval_label": "6개월마다" if interval == 6 else "1년마다",
                   "next": F.today_label(fam, interval),
                   "events": [rendered[f"review.events.{i}"] for i in range(len(o["review"].get("events", [])))]},
        "change_conditions": [rendered[f"change_conditions.{i}"] for i in range(len(o["change_conditions"]))],
        "commitments": [{"commitment_id": f"c{i + 1}", "text": rendered[f"commitments.{i}"], "source": c.get("source", {})}
                        for i, c in enumerate(o["commitments"])],
        "report": {"reasons": [rendered[f"report.reasons.{i}"] for i in range(len(o["report"].get("reasons", [])))],
                   "outcomes": [{"label": rendered[f"report.outcomes.{i}.label"], "display": facts[x["fact_id"]]["display"]}
                                for i, x in enumerate(o["report"].get("outcomes", [])) if x.get("fact_id") in facts],
                   "action_plan": [{"when": rendered[f"report.action_plan.{i}.when"], "what": rendered[f"report.action_plan.{i}"]}
                                   for i, a in enumerate(o["report"].get("action_plan", []))]},
        "version": version,
    }
    saving = next((f["value"] for f in cfacts if f["fact_id"] == "agree.monthly_saving"), None)
    check_agreement(agreement, saving, goal, conditions, rec)
    out.update(result=agreement, verification=rec.to_dict())
    return out


# ---------- 화면 7: 상품 추천 ----------
def recommend(fam: dict, agreement: dict, provider) -> dict:
    o = load_ontology()
    vocab = {"needs": [{"id": n["id"], "label": n["label"], **({"only_if": n["requires"]["why"]} if n.get("requires") else {})}
                       for n in o["needs"].values()],
             "constraints": [{"id": c["id"], "label": c["label"]} for c in o["constraints"].values()]}
    commitments = [{"commitment_id": str(c.get("commitment_id")), "text": str(c.get("text", ""))[:200]}
                   for c in (agreement.get("commitments") or [])[:8]]
    goal_text = str(agreement.get("goal", ""))[:200]
    run = run_role("8", {"goal": goal_text, "commitments": commitments, "vocab": vocab}, provider)
    out = {"run": run.__dict__}
    if not run.ok:
        return out
    rec = VerificationRecord(run_id=None, role="8")
    refs = []
    for i, m in enumerate(run.output["mappings"]):
        refs += [(f"mappings.{i}.need_ids", x, set(o["needs"])) for x in m.get("need_ids", [])]
        refs += [(f"mappings.{i}.constraint_ids", x, set(o["constraints"])) for x in m.get("constraint_ids", [])]
    check_refs(refs, rec)
    coms = {c["commitment_id"]: {"no": int(c["commitment_id"][1:]) if c["commitment_id"][1:].isdigit() else None,
                                 "text": c["text"]} for c in commitments}
    coms["goal"] = {"no": None, "text": goal_text}
    # 조건이 있는 필요(예: 주택연금 = 집이 있고 55세 이상)는 가족 상황이 맞을 때만 연결한다(AI 매핑 실수를 코드가 막음)
    p = F.profile(fam)
    oldest = max(m["age"] for m in fam["members"])
    dropped = []

    def eligible(nid: str) -> bool:
        r = o["needs"][nid].get("requires") or {}
        if r.get("home") and not p["home_total"]:
            return False
        if r.get("home_or_assets") and not (p["home_total"] or p["liquid_total"] >= 10000):
            return False
        if r.get("repaying_loan") and not p["repaying_loans"]:
            return False
        return oldest >= r.get("min_age", 0)

    mappings = []
    for m in run.output["mappings"]:
        keep = [n for n in m.get("need_ids", []) if eligible(n)]
        dropped += [{"commitment_id": m.get("commitment_id"), "need_id": n, "reason": o["needs"][n]["requires"]["why"]}
                    for n in m.get("need_ids", []) if n not in keep]
        for n in keep:  # 꼭 지켜야 하는 돈(휴직 준비금·비상금·병원비)은 '원금 보장'을 기본 제약으로
            extra = [c for c in o["needs"][n].get("default_constraints", []) if c not in m.get("constraint_ids", [])]
            if extra:
                mappings.append({**m, "need_ids": [n], "constraint_ids": list(m.get("constraint_ids", [])) + extra})
        keep = [n for n in keep if not o["needs"][n].get("default_constraints")]
        if keep or not m.get("need_ids"):
            mappings.append({**m, "need_ids": keep})
    merged: dict[str, dict] = {}
    for m in mappings:
        for n in m.get("need_ids", []):
            if n in merged:
                merged[n]["constraint_ids"] = sorted(set(merged[n]["constraint_ids"]) | set(m.get("constraint_ids", [])))
            else:
                merged[n] = {**m, "need_ids": [n], "constraint_ids": list(m.get("constraint_ids", []))}
    raw = ontology_recommend(list(merged.values()), coms)
    has_product = {r["need_id"] for r in raw if r.get("product_type_id")}
    recs, seen = [], set()
    for r in raw:  # 여러 약속이 같은 필요·상품으로 이어지면 한 번만, 상품이 있는 필요에는 '연결 없음' 카드를 빼기
        key = (r["need_id"], r.get("product_type_id"))
        if key in seen or (r.get("product_type_id") is None and r["need_id"] in has_product):
            continue
        seen.add(key)
        recs.append(r)
    out.update(result={"mappings": run.output["mappings"], "recommendations": recs, "dropped_needs": dropped},
               verification=rec.to_dict())
    return out
