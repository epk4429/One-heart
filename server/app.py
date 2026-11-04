"""API 처리기(docs/09 3절). 로컬 dev_server.py와 Vercel 함수(api/index.py)가 함께 쓴다.

상태는 저장하지 않는다. 클라이언트(브라우저)가 가족 입력과 단계 결과를 갖고 있다가 필요한 만큼 보내고,
서버는 매번 가족 입력과 방법(spec)을 다시 검사한 뒤 엔진으로 다시 계산한다(엔진 결과는 클라이언트 값을 믿지 않음).
AI를 부르는 요청은 체험 코드·호출 제한·예산을 먼저 확인한다(server/guard.py).
"""

from __future__ import annotations

import json
import os

from engine import ENGINE_VERSION, compare, simulate
from llm import family as F
from llm import pipeline as P
from llm import goals
from llm.plan import GOAL_TYPES, PlanError, build_request, check_option, normalize_goal
from llm.providers import DEFAULT_MODELS, LLMError, get_provider, load_env

from ontology import graph as ontology_graph
from ontology.fit import BAND_LABEL as FIT_BANDS
from ontology.fit import REAL as FIT_REAL
from ontology.fit import compare as fit_compare
from ontology.loans import LOAN as FIT_LOANS
from ontology.programs import judge as judge_program
from ontology.routes import ROUTE_LABEL
from ontology.routes import coverage as need_routes
from ontology.products import load_products
from rag.index import TOPICS as RAG_TOPICS
from rag.index import available as rag_available
from rag.index import laws as rag_laws
from rag.index import search as rag_search

from . import guard

MAX_BODY = 256 * 1024


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


_provider = None


def provider(ctx: dict):
    """요청마다 비용을 세는 래퍼를 씌운 공급자."""
    global _provider
    if _provider is None:
        load_env()
        try:
            _provider = get_provider()
        except LLMError as e:
            raise ApiError("llm_unavailable", str(e), 503)
    return guard.MeteredProvider(_provider, ctx["code_key"])


def _need(body: dict, *keys: str) -> None:
    for k in keys:
        if k not in body:
            raise ApiError("bad_request", f"'{k}'가 필요해요")


def custom_family_allowed() -> bool:
    """'우리 가족으로 체험하기'를 열지. Vercel(공개)에서는 기본으로 닫고(예시 가족만), 로컬 개발에서는 연다.
    ALLOW_CUSTOM_FAMILY=1/0으로 바꿀 수 있다."""
    v = os.environ.get("ALLOW_CUSTOM_FAMILY")
    if v is not None and v.strip() != "":
        return v.strip().lower() in ("1", "true", "yes", "on")
    return not os.environ.get("VERCEL")


def _same_as_preset(fam: dict) -> bool:
    """예시 가족 그대로인지(가족방·구성원·이야기). 금융정보는 가족 홈의 재점검으로 바뀔 수 있어 보지 않는다."""
    pid = fam.get("preset_id")
    if not pid:
        return False
    try:
        p = F.validate(F.preset(pid))
    except F.FamilyError:
        return False
    return all(fam[k] == p[k] for k in ("room", "members", "story"))


def real_products_allowed() -> bool:
    """실제 상품 공시(ontology/products)를 쓸지. 데이터가 있으면 공개 배포(Vercel)에서도 켠다(2026-11-03 형님 결정:
    공개 사이트도 형님만 쓰니 상관없음). REAL_PRODUCTS=1/0으로 바꿀 수 있다."""
    v = os.environ.get("REAL_PRODUCTS")
    if v is not None and v.strip() != "":
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(load_products("saving"))


def _family(body: dict) -> dict:
    _need(body, "family")
    try:
        fam = F.validate(body["family"])
    except F.FamilyError as e:
        raise ApiError("bad_family", str(e))
    if not custom_family_allowed() and not _same_as_preset(fam):
        raise ApiError("examples_only", "체험판에서는 예시 가족만 쓸 수 있어요", 403)
    return fam


def _member_id(fam: dict, body: dict) -> str:
    mid = body.get("member_id")
    if mid not in {m["member_id"] for m in fam["members"]}:
        raise ApiError("bad_request", "없는 구성원이에요")
    return mid


def _goal(fam: dict, body: dict) -> dict:
    _need(body, "goal")
    try:
        return normalize_goal(fam, body["goal"])
    except PlanError as e:
        raise ApiError("bad_goal", str(e))


def _specs(fam: dict, goal: dict, raw: list, *, allow_revised: bool = True) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        raise ApiError("bad_request", "방법이 1~3개 필요해요")
    out = []
    for s in raw:
        oid = s.get("option_id") if isinstance(s, dict) else None
        ids = ("A", "B", "C", "A2", "B2", "C2") if allow_revised else ("A", "B", "C")
        try:
            out.append(check_option(fam, goal, s, allowed_ids=(oid,) if oid in ids else ids))
        except PlanError as e:
            raise ApiError("bad_option", str(e))
    return out


def _sim(fam: dict, goal: dict, specs: list[dict], **kw) -> dict:
    out = P.simulate_specs(fam, goal, specs, **kw)
    if "error" in out:
        raise ApiError("bad_input", json.dumps(out["error"], ensure_ascii=False))
    return out


def _err_if_failed(out: dict) -> dict:
    """역할 호출이 실패했으면 화면이 '다시 시도'를 보이도록 오류로 바꾼다."""
    for k in ("run", "analysis_run", "design_run"):
        r = out.get(k)
        if r and not r.get("ok"):
            errs = r.get("errors") or []
            if any("호출 실패" in e for e in errs):
                raise ApiError("llm_unavailable", errs[-1], 503)
            raise ApiError("llm_bad_output", "AI 응답 형식이 맞지 않았어요: " + "; ".join(errs[-3:]), 502)
    if out.get("error"):
        raise ApiError("bad_option", str(out["error"]), 502)
    return out


def _strip(out: dict) -> dict:
    """화면에는 호출 기록 중 필요한 것만."""
    res = {k: v for k, v in out.items() if not k.endswith("run")}
    res["calls"] = [{"role": v.get("role"), "model": v.get("model"), "latency_s": v.get("latency_s"),
                     "attempts": v.get("attempts"), "tool_calls": v.get("tool_calls"),
                     "cost_usd": (v.get("usage") or {}).get("cost_usd")}
                    for k, v in out.items() if k.endswith("run") and isinstance(v, dict)]
    return res


def _llm(fn):
    fn.uses_llm = True
    return fn


# ---------- 공개 라우트(AI 안 씀) ----------
def r_health(_b, _ctx):
    load_env()
    name = os.environ.get("LLM_PROVIDER", "hf")
    model = "replay(개발용)" if name == "replay" else os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(name, "")
    return {"ok": True, "provider": name, "model": model, "engine_version": ENGINE_VERSION,
            "access_required": guard.access_required(), "budget_store": guard.backend(),
            "custom_family": custom_family_allowed()}


def r_access(b, _ctx):
    try:
        key = guard.check_code(b.get("code"))
    except guard.GuardError as e:
        raise ApiError(e.code, e.message, e.status)
    st = guard.status(key)
    left = None
    if "code_budget_usd" in st:
        left = max(0, round(100 * (1 - st["code_spent_usd"] / st["code_budget_usd"])))
    return {"ok": True, "remaining_pct": left}


def r_config(_b, _ctx):
    a = F.assumptions()
    return {"custom_family": custom_family_allowed(), "real_products": real_products_allowed(), "need_routes": need_routes(),
            "rag": {"available": rag_available(), "topics": RAG_TOPICS},
            "route_labels": ROUTE_LABEL, "questions": F.QUESTIONS, "kinds": {k: v[2] for k, v in F.KINDS.items()},
            "monthly_kinds": [k for k, v in F.KINDS.items() if v[0] == "monthly"], "loan_types": F.LOAN_TYPES,
            "goal_types": GOAL_TYPES, "limits": F.LIMITS, "goal_input": goals.public_config(),
            "assumptions": {"returns": a["returns"], "inflation": a["inflation"],
                            "reverse_mortgage": a["reverse_mortgage"]["source"], "sell_home": a["sell_home"]["source"]}}


def r_preset(b, _ctx):
    try:
        return F.preset(str(b.get("preset_id")))
    except F.FamilyError as e:
        raise ApiError("not_found", str(e), 404)


def r_family_check(b, _ctx):
    fam = _family(b)
    return {"family": fam, "profile": F.profile(fam)}


def r_goal_check(b, _ctx):
    fam = _family(b)
    return {"goal": _goal(fam, b)}


# ---------- AI 라우트 ----------
@_llm
def r_story(b, ctx):
    return _strip(_err_if_failed(P.story_understand(_family(b), provider(ctx))))


@_llm
def r_review(b, ctx):
    fam = _family(b)
    mid = _member_id(fam, b)
    try:
        out = P.interview_review(fam, mid, b.get("qa"), provider(ctx), b.get("clarification"))
    except PlanError as e:
        raise ApiError("bad_request", str(e))
    return _strip(_err_if_failed(out))


@_llm
def r_resolve(b, ctx):
    _need(b, "detect", "answer")
    fam = _family(b)
    return _strip(_err_if_failed(P.interview_resolve(fam, _member_id(fam, b), b["detect"], b["answer"], provider(ctx))))


@_llm
def r_goal_analyze(b, ctx):
    _need(b, "summaries", "story_understanding")
    fam = _family(b)
    return _strip(_err_if_failed(P.goal_analyze(fam, b["summaries"], b["story_understanding"], provider(ctx),
                                                b.get("clarifications"))))


@_llm
def r_goal_revise(b, ctx):
    """가족이 조건·다른 의견을 냈을 때 의견을 모은 수정 제안(역할 4c)."""
    _need(b, "summaries", "analysis", "rounds")
    fam = _family(b)
    try:
        return _strip(_err_if_failed(P.goal_revise(fam, b["summaries"], b["analysis"], b["rounds"], provider(ctx),
                                                   b.get("clarifications"), b.get("discussion") or "")))
    except ValueError as e:
        raise ApiError("bad_request", str(e))


@_llm
def r_goal_stuck(b, ctx):
    """제안을 여러 번 고쳐도 모이지 않을 때 이야기가 필요한 부분을 안내(역할 4d)."""
    _need(b, "summaries", "rounds")
    fam = _family(b)
    try:
        return _strip(_err_if_failed(P.goal_stuck(fam, b["summaries"], b["rounds"], provider(ctx))))
    except ValueError as e:
        raise ApiError("bad_request", str(e))


@_llm
def r_goal_criterion(b, ctx):
    _need(b, "proposal", "replies", "summaries")
    fam = _family(b)
    out = _strip(_err_if_failed(P.goal_criterion(fam, b["proposal"], b["replies"], b["summaries"], provider(ctx),
                                                 b.get("story_understanding"), b.get("reasons"))))
    # 확정된 목표를 계산할 수 있는지 서버가 바로 확인한다(화면에서 따로 계산 버튼을 누르지 않는다)
    try:
        out["goal_check"] = {"ok": True, "goal": normalize_goal(fam, out["result"]["goal"])}
    except PlanError as e:
        out["goal_check"] = {"ok": False, "message": str(e)}
    return out


@_llm
def r_options_design(b, ctx):
    _need(b, "criterion", "summaries", "goal")
    fam = _family(b)
    _goal(fam, b)  # 먼저 목표가 계산 가능한지 확인(AI 호출 전에 돈 안 들이고 거른다)
    try:
        out = P.options_design(fam, b["goal"], b["criterion"], b["summaries"], provider(ctx))
    except PlanError as e:
        raise ApiError("bad_option", str(e), 502)
    return _strip(_err_if_failed(out))


def r_simulate(b, _ctx):
    """엔진만: 방법들을 다시 계산한다. override가 있으면 첫 방법의 월 저축·수익률만 바꿔 본다(슬라이더)."""
    fam = _family(b)
    goal = _goal(fam, b)
    specs = _specs(fam, goal, b.get("specs"))
    ov = b.get("override") or {}
    if not ov:
        return _sim(fam, goal, specs)
    req = build_request(fam, goal, specs[:1])
    opt = req["options"][0]
    if isinstance(ov.get("expected_return"), (int, float)):
        opt["expected_return"] = max(0.0, min(12.0, float(ov["expected_return"])))
    if isinstance(ov.get("monthly_delta"), (int, float)) and ov["monthly_delta"]:
        opt["cashflows"].append({"label": "직접 바꾼 값", "amount": max(-1000.0, min(1000.0, float(ov["monthly_delta"]))),
                                 "category": "manual"})
    out = simulate(req)
    if "error" in out:
        raise ApiError("bad_input", json.dumps(out["error"], ensure_ascii=False))
    return out


@_llm
def r_agreement_check(b, ctx):
    _need(b, "specs", "summaries")
    fam = _family(b)
    goal = _goal(fam, b)
    specs = _specs(fam, goal, b["specs"])
    return _strip(_err_if_failed(P.agreement_check(fam, goal, specs, _sim(fam, goal, specs), b["summaries"], provider(ctx))))


@_llm
def r_agreement_revise(b, ctx):
    _need(b, "specs", "stances", "summaries")
    fam = _family(b)
    goal = _goal(fam, b)
    specs = _specs(fam, goal, b["specs"], allow_revised=False)
    try:
        out = P.agreement_revise(fam, goal, specs, _sim(fam, goal, specs), b["stances"], b["summaries"], provider(ctx))
    except PlanError as e:
        raise ApiError("bad_option", str(e), 502)
    return _strip(_err_if_failed(out))


@_llm
def r_agreement_draft(b, ctx):
    _need(b, "criterion", "spec", "conditions", "summaries")
    fam = _family(b)
    goal = _goal(fam, b)
    spec = _specs(fam, goal, [b["spec"]])[0]
    result = _sim(fam, goal, [spec])["results"][0]
    label = str(b.get("method_label") or f"{spec['option_id']}. {spec['label']}")[:60]
    version = b.get("version", 1)
    version = version if isinstance(version, int) and 1 <= version <= 50 else 1
    return _strip(_err_if_failed(P.agreement_draft(fam, goal, b["criterion"], spec, result, label, b["conditions"],
                                                   b["summaries"], provider(ctx), b.get("revision"), version)))


@_llm
def r_recommend(b, ctx):
    _need(b, "agreement")
    return _strip(_err_if_failed(P.recommend(_family(b), b["agreement"], provider(ctx))))


def _opt_num(b: dict, k: str, lo: float, hi: float, label: str):
    v = b.get(k)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise ApiError("bad_request", f"{label}은(는) {lo:g}~{hi:g} 사이 숫자여야 해요")
    return v


def r_products_fit(b, _ctx):
    """합의안 약속에 맞는 실제 상품을 '우리 목표에 잘 맞는 순서'로(ontology/fit.py). AI 없음, 비용 없음.
    category(saving·deposit·mortgage·rent_loan·credit_loan·busi_loan) 또는 product_type_id로 범주를 고른다."""
    if not real_products_allowed():
        raise ApiError("not_available", "이 체험판에서는 실제 상품 비교를 쓰지 않아요", 404)
    _need(b, "need_id")
    fam = _family(b)
    mid = _member_id(fam, b)
    cat = b.get("category") or FIT_REAL.get(str(b.get("product_type_id") or ""))
    com = b.get("commitment") if isinstance(b.get("commitment"), dict) else None
    com = {"no": com.get("no") if isinstance(com.get("no"), int) else None, "text": str(com.get("text", ""))[:120]} if com else None
    if cat in ("saving", "deposit"):
        term = b.get("term_months", 12)
        if term not in (1, 3, 6, 12, 24, 36):
            raise ApiError("bad_request", "기간은 1·3·6·12·24·36개월 중 하나예요")
        params = {"term": term, "actions": [a for a in (b.get("actions") or []) if isinstance(a, str)][:12],
                  "monthly": _opt_num(b, "monthly", 1, 10000, "매달 넣을 돈(만원)"), "amount": _opt_num(b, "amount", 1, 1000000, "맡길 돈(만원)")}
        pr = b.get("person") if isinstance(b.get("person"), dict) else {}
        kids = pr.get("kids")
        if kids is not None and kids not in (0, 1, 2, 3):
            raise ApiError("bad_request", "자녀 수는 0·1·2·3(3명 이상) 중 하나예요")
        params["person"] = {"kids": kids, "flags": [f for f in (pr.get("flags") or []) if isinstance(f, str)][:10]}
    elif cat in FIT_LOANS:
        params = {"amount": _opt_num(b, "amount", 1, 1000000, "빌릴 돈(만원)"), "months": int(_opt_num(b, "months", 1, 480, "기간(개월)") or 360),
                  "home_price": _opt_num(b, "home_price", 1, 10000000, "집값(만원)"),
                  "deposit_amount": _opt_num(b, "deposit_amount", 1, 1000000, "보증금(만원)"),
                  "prepay_month": (int(v) if (v := _opt_num(b, "prepay_month", 1, 480, "일찍 갚을 달")) else None)}
        for k, allowed, dflt in (("repay", ("split", "bullet"), "split"), ("method", ("equal_payment", "equal_principal"), "equal_payment"),
                                 ("rate_pref", ("any", "fixed", "variable"), "any"), ("house", ("아파트", "아파트외"), "아파트"),
                                 ("band", tuple(FIT_BANDS), "avg")):
            v = b.get(k, dflt)
            if v not in allowed:
                raise ApiError("bad_request", f"{k}는 {', '.join(allowed)} 중 하나예요")
            params[k] = v
    else:
        return {"available": False}
    return fit_compare(fam, str(b["need_id"]), category=cat, member_id=mid, commitment=com, **params)


def r_rag_search(b, _ctx):
    """법령 원문 찾기(rag/index.py): 색인된 법령 조문에서 찾는다. 온톨로지와 독립(제도·상품 ID를 받지 않는다). AI 없음, 비용 없음.
    결과는 원문 그대로이고 자격·금리 판단에는 쓰지 않는다."""
    if not rag_available():
        raise ApiError("not_available", "이 체험판에서는 원문 찾기를 쓰지 않아요", 404)
    known = {x["doc_key"] for x in rag_laws()}
    laws = [n for n in (b.get("laws") or []) if isinstance(n, str) and n in known][:7]
    q = str(b.get("query") or "").strip()[:80]
    if not q:
        raise ApiError("bad_request", "찾을 질문이 필요해요")
    topic = any(q == t[1] for ts in RAG_TOPICS.values() for t in ts)
    return {"query": q, "results": rag_search(q, laws or None, topic=topic),
            "note": "법령 원문을 그대로 보여 줘요(AI가 요약하지 않았어요). 자격·금리 판단은 위 판정을 보세요. 최종 판단은 기관이 해요."}


def r_graph_stats(b, _ctx):
    """온톨로지 그래프(ontology/graph.py)의 노드·관계 수. AI 없음."""
    return ontology_graph.stats()


def r_graph_node(b, _ctx):
    """노드 하나와 이웃(관계·종류별로 limit개까지 + 전체 수). AI 없음."""
    nid = str(b.get("id") or "")[:200]
    limit = max(1, min(200, int(b.get("limit") or 30)))
    out = ontology_graph.neighbors(nid, limit)
    if out is None:
        raise ApiError("not_found", "없는 노드예요", 404)
    return out


def r_graph_search(b, _ctx):
    """이름으로 노드 찾기. AI 없음."""
    return {"results": ontology_graph.search(str(b.get("q") or "")[:40])}


def r_programs_judge(b, _ctx):
    """필요에 이어진 제도(정책금융·공적 제도)를 가족 정보로 판정(ontology/programs.py, 공식 원문 인용). AI 없음, 비용 없음."""
    _need(b, "need_id")
    fam = _family(b)
    routes = need_routes().get(str(b["need_id"]), {}).get("routes", [])
    ids = [pid for r in routes if r["route"] == "program" for pid in r["programs"]]
    return {"need_id": b["need_id"], "programs": [judge_program(pid, fam) for pid in dict.fromkeys(ids)]}


REVIEW_FIELDS = {  # 재점검에서 바꿀 수 있는 상황(기획안 15쪽: 소득·지출·금리·자산이 바뀌면 지난 합의와의 차이를 다시 계산)
    "income_delta": ("매달 들어오는 돈", -2000.0, 2000.0),
    "expense_delta": ("매달 나가는 돈", -2000.0, 2000.0),
    "lump": ("한 번에 생긴(나간) 돈", -100000.0, 100000.0),
    "return_delta": ("예금·투자 수익률", -5.0, 5.0),
    "loan_rate_delta": ("대출 금리", -5.0, 5.0),
}


def r_review_compare(b, _ctx):
    """재점검: 상황 변화(소득·지출·큰돈·수익률·대출 금리)를 넣으면 지난 합의와의 차이를 엔진이 다시 계산한다(AI 없음)."""
    fam = _family(b)
    goal = _goal(fam, b)
    spec = _specs(fam, goal, [b.get("spec")])[0]
    ch = b.get("changes")
    if not isinstance(ch, dict):  # 예전 형식: 수익률만
        ch = {"return_delta": b.get("return_delta", -0.5)}
    vals = {}
    for k, (label, lo, hi) in REVIEW_FIELDS.items():
        v = ch.get(k)
        if v in (None, "", 0):
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ApiError("bad_request", f"{label} 변화는 {lo:g}~{hi:g} 사이 숫자여야 해요")
        vals[k] = float(v)
    if not vals:
        raise ApiError("bad_request", "바뀐 상황을 하나 이상 넣어 주세요")
    req = build_request(fam, goal, [spec])
    before = simulate(req)
    opt = req["options"][0]
    if "income_delta" in vals:
        opt["cashflows"].append({"label": "수입 변화(재점검)", "amount": vals["income_delta"], "category": "income"})
    if "expense_delta" in vals:
        opt["cashflows"].append({"label": "지출 변화(재점검)", "amount": -vals["expense_delta"], "category": "expense"})
    if "lump" in vals:
        req["start"]["goal_pool"] = round(req["start"]["goal_pool"] + vals["lump"], 1)
    if "return_delta" in vals:
        opt["expected_return"] = max(0.0, min(12.0, opt["expected_return"] + vals["return_delta"]))
    if "loan_rate_delta" in vals:
        for l in req["start"]["loans"]:
            l["rate"] = max(0.0, l["rate"] + vals["loan_rate_delta"])
    after = simulate(req)
    if "error" in after:
        reason = after["error"].get("reason", "")
        raise ApiError("bad_input", "바뀐 조건으로는 계산할 수 없어요: " + reason)
    rb, ra = before["results"][0], after["results"][0]
    cmp_ = compare(before, after)
    d = cmp_["diffs"][0]["hit_month_delta"]
    w = goal.get("within_months")
    ok_before = ra_ok = None
    if goal["type"] == "reach_target" and w:
        ok_before = bool(rb["goal_hit_month"] and rb["goal_hit_month"] <= w)
        ra_ok = bool(ra["goal_hit_month"] and ra["goal_hit_month"] <= w)
    return {"before": rb["goal_hit_display"], "after": ra["goal_hit_display"], "hit_month_delta": d,
            "flow_before": rb["monthly_flow"], "flow_after": ra["monthly_flow"],
            "within_before": ok_before, "within_after": ra_ok, "changes": vals,
            "change_labels": {k: REVIEW_FIELDS[k][0] for k in vals},
            "return_before": rb["basis"][2]["value"], "return_after": ra["basis"][2]["value"], "compare": cmp_}


ROUTES = {
    ("GET", "/api/health"): r_health,
    ("POST", "/api/access"): r_access,
    ("POST", "/api/config"): r_config,
    ("POST", "/api/preset"): r_preset,
    ("POST", "/api/family/check"): r_family_check,
    ("POST", "/api/goal/check"): r_goal_check,
    ("POST", "/api/story/understand"): r_story,
    ("POST", "/api/interview/review"): r_review,
    ("POST", "/api/interview/resolve"): r_resolve,
    ("POST", "/api/goal/analyze"): r_goal_analyze,
    ("POST", "/api/goal/revise"): r_goal_revise,
    ("POST", "/api/goal/stuck"): r_goal_stuck,
    ("POST", "/api/goal/criterion"): r_goal_criterion,
    ("POST", "/api/options/design"): r_options_design,
    ("POST", "/api/simulate"): r_simulate,
    ("POST", "/api/agreement/check"): r_agreement_check,
    ("POST", "/api/agreement/revise"): r_agreement_revise,
    ("POST", "/api/agreement/draft"): r_agreement_draft,
    ("POST", "/api/recommend"): r_recommend,
    ("POST", "/api/review/compare"): r_review_compare,
    ("POST", "/api/products/fit"): r_products_fit,
    ("POST", "/api/programs/judge"): r_programs_judge,
    ("POST", "/api/rag/search"): r_rag_search,
    ("POST", "/api/graph/stats"): r_graph_stats,
    ("POST", "/api/graph/node"): r_graph_node,
    ("POST", "/api/graph/search"): r_graph_search,
}


def dispatch(method: str, path: str, raw_body: bytes, headers: dict | None = None, ip: str = "local") -> tuple[int, dict]:
    path = path.split("?")[0].rstrip("/")
    fn = ROUTES.get((method, path))
    if fn is None:
        return 404, {"error": {"code": "not_found", "message": "없는 API예요"}}
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        if len(raw_body or b"") > MAX_BODY:
            raise ApiError("too_large", "보낸 내용이 너무 커요", 413)
        body = json.loads(raw_body or b"{}") if method == "POST" else {}
        if not isinstance(body, dict):
            raise ApiError("bad_json", "JSON 객체여야 해요")
        ctx = {"code_key": "local"}
        if path not in ("/api/health", "/api/access", "/api/config", "/api/preset") and not path.startswith("/api/graph/"):  # 그래프 보기는 읽기만, AI 없음
            guard.check_rate(ip)
        if getattr(fn, "uses_llm", False):
            ctx["code_key"] = guard.check_code(headers.get("x-access-code"))
            guard.check_budget(ctx["code_key"])
        return 200, fn(body, ctx)
    except ApiError as e:
        return e.status, {"error": {"code": e.code, "message": e.message}}
    except guard.GuardError as e:
        return e.status, {"error": {"code": e.code, "message": e.message}}
    except json.JSONDecodeError:
        return 400, {"error": {"code": "bad_json", "message": "JSON 형식이 아니에요"}}
    except Exception as e:  # noqa: BLE001 - 화면에는 짧게, 서버 로그에는 자세히
        import traceback
        traceback.print_exc()
        return 500, {"error": {"code": "server_error", "message": f"서버에서 처리하지 못했어요({type(e).__name__})"}}
