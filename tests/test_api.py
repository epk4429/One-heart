"""API 전체 흐름(재생 공급자, 돈 안 듦): 예시 가족 두 개와 직접 만든 가족 하나를 처음부터 끝까지."""

import json
import os

import pytest

os.environ["LLM_PROVIDER"] = "replay"
os.environ.pop("ACCESS_CODES", None)

from server import app as A  # noqa: E402
from server import guard  # noqa: E402


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    monkeypatch.setenv("ACCESS_CODES", "")  # 빈 값으로 두면 .env를 읽어도 덮어쓰지 않는다(load_env는 setdefault)
    monkeypatch.setenv("RATE_PER_MIN", "1000")
    A._provider = None
    yield
    A._provider = None


def call(path, body=None, method="POST", headers=None):
    status, out = A.dispatch(method, path, json.dumps(body or {}).encode(), headers or {})
    assert status == 200, (path, out)
    return out


SINGLE_PARENT = {
    "today": "2026-10",
    "room": {"name": "우리 셋의 내일", "reason": "빚을 언제 다 갚을 수 있는지 아이들과 함께 보고 싶어요.", "host_member_id": "m0"},
    "members": [{"member_id": "m0", "name": "현주", "role": "엄마", "age": 41},
                {"member_id": "m1", "name": "도윤", "role": "아들", "age": 17},
                {"member_id": "m2", "name": "서아", "role": "딸", "age": 14}],
    "story": {"author_id": "m0", "text": "혼자 아이 둘을 키워요. 월세에 살고, 신용대출이 남아 있어요. 도윤이는 대학 갈 때 등록금이 걱정이에요."},
    "finance": [{"item_id": "f1", "owner_id": "m0", "kind": "income", "label": "월급", "amount": 320},
                {"item_id": "f2", "owner_id": "joint", "kind": "expense", "label": "생활비·월세", "amount": 230},
                {"item_id": "f3", "owner_id": "m0", "kind": "deposit", "label": "적금", "amount": 600},
                {"item_id": "f4", "owner_id": "m0", "kind": "loan", "loan_type": "credit", "label": "신용대출",
                 "amount": 1800, "rate": 7.5, "payment": 40}],
}
ANSWERS = {"m0": ["아이들이 하고 싶은 공부를 돈 걱정 없이 하는 거요.", "대출 이자가 계속 나가는 게 걱정이에요.", "외식은 줄일 수 있어요. 아이들 학원은 못 줄여요."],
           "m1": ["엄마가 덜 힘들었으면 좋겠어요.", "등록금이요.", "용돈은 줄여도 돼요."],
           "m2": ["지금처럼 셋이 같이 사는 거요.", "잘 모르겠어요.", "새 휴대폰은 나중에 사도 돼요."]}


def run_flow(fam, answers, replies=None, goal_override=None):
    qs = call("/api/config")["questions"]
    fam = call("/api/family/check", {"family": fam})["family"]
    su = call("/api/story/understand", {"family": fam})["result"]
    summaries, clars = {}, []
    for m in fam["members"]:
        mid = m["member_id"]
        qa = [[q["text"], a] for q, a in zip(qs, answers[mid])]
        r = call("/api/interview/review", {"family": fam, "member_id": mid, "qa": qa})["result"]
        if r["ambiguous"]:
            res = call("/api/interview/resolve", {"family": fam, "member_id": mid, "detect": r,
                                                  "answer": r["choices"][0]})["result"]
            assert res["resolved"]
            c = {"word": r["ambiguous"][0]["word"], "meaning": res["meaning"]}
            clars.append({"member_id": mid, **c})
            r = call("/api/interview/review", {"family": fam, "member_id": mid, "qa": qa, "clarification": c})["result"]
            assert not r["ambiguous"]
        summaries[mid] = {k: r[k] for k in ("keep", "flexible", "worry")}
    g = call("/api/goal/analyze", {"family": fam, "summaries": summaries, "story_understanding": su,
                                    "clarifications": clars})["result"]
    replies = replies or {m["member_id"]: "좋아요." for m in fam["members"]}
    cr = call("/api/goal/criterion", {"family": fam, "proposal": g["proposal"]["text"], "replies": replies,
                                       "summaries": summaries})["result"]
    goal = {**cr["goal"], **(goal_override or {})}
    goal = call("/api/goal/check", {"family": fam, "goal": goal})["goal"]
    d = call("/api/options/design", {"family": fam, "goal": goal, "criterion": cr["criterion"], "summaries": summaries})
    assert len(d["specs"]) == 3 and d["verification"]["status"] != "fail", d["verification"]
    specs = d["specs"]
    sim = call("/api/simulate", {"family": fam, "goal": goal, "specs": specs})
    assert [r["goal_hit_display"] for r in sim["results"]] == [r["goal_hit_display"] for r in d["simulation"]["results"]]
    call("/api/simulate", {"family": fam, "goal": goal, "specs": specs[:1], "override": {"monthly_delta": 30}})
    call("/api/agreement/check", {"family": fam, "goal": goal, "specs": specs, "summaries": summaries})
    first = fam["members"][0]["member_id"]
    stances = {m["member_id"]: {s["option_id"]: {"v": "no", "text": "어려워요"} if m["member_id"] == first else {"v": "good"}
                                for s in specs} for m in fam["members"]}
    rv = call("/api/agreement/revise", {"family": fam, "goal": goal, "specs": specs, "stances": stances,
                                         "summaries": summaries})["result"]
    conds = [{"member_id": first, "text": "6개월마다 꼭 같이 다시 봐요."}]
    a = call("/api/agreement/draft", {"family": fam, "goal": goal, "criterion": cr["criterion"], "spec": rv["spec"],
                                       "method_label": rv["label"], "conditions": conds, "summaries": summaries,
                                       "revision": rv})
    assert a["verification"]["status"] != "fail", a["verification"]
    agreement = a["result"]
    assert any(c["source"].get("type") == "condition" for c in agreement["commitments"])
    rec = call("/api/recommend", {"family": fam, "agreement": agreement})["result"]
    cmp_ = call("/api/review/compare", {"family": fam, "goal": goal, "spec": rv["spec"], "return_delta": -0.5})
    return {"goal": goal, "design": d, "agreement": agreement, "rec": rec, "compare": cmp_}


@pytest.mark.parametrize("pid", ["newly", "elder"])
def test_preset_full_flow(pid):
    p = call("/api/preset", {"preset_id": pid})
    goal = {"type": "reach_target", "target_amount": 30000, "within_months": 60} if pid == "newly" else None
    out = run_flow(p, p["scripts"]["answers"], p["scripts"]["replies"], goal)
    assert out["goal"]["type"] == ("reach_target" if pid == "newly" else "runway")


def test_custom_family_debt_free():
    out = run_flow(SINGLE_PARENT, ANSWERS, goal_override={"type": "debt_free"})
    assert out["goal"]["type"] == "debt_free"
    hits = [r["goal_hit_display"] for r in out["design"]["simulation"]["results"]]
    assert all(h for h in hits)


def test_bad_family_rejected():
    st, out = A.dispatch("POST", "/api/family/check", json.dumps({"family": {"members": []}}).encode())
    assert st == 400 and out["error"]["code"] == "bad_family"


def test_option_with_invented_big_inflow_rejected():
    fam = call("/api/family/check", {"family": SINGLE_PARENT})["family"]
    goal = call("/api/goal/check", {"family": fam, "goal": {"type": "runway"}})["goal"]
    bad = {"option_id": "A", "label": "x", "return_id": "safe",
           "lump_sums": [{"label": "복권", "month": 3, "amount": 50000, "reason": "?"}]}
    st, out = A.dispatch("POST", "/api/simulate", json.dumps({"family": fam, "goal": goal, "specs": [bad]}).encode())
    assert st == 400 and out["error"]["code"] == "bad_option"


def test_access_code_and_budget(monkeypatch):
    monkeypatch.setenv("ACCESS_CODES", "hello:0.5")
    fam = call("/api/preset", {"preset_id": "newly"})
    st, out = A.dispatch("POST", "/api/story/understand", json.dumps({"family": fam}).encode(), {})
    assert st == 401
    st, out = A.dispatch("POST", "/api/story/understand", json.dumps({"family": fam}).encode(), {"X-Access-Code": "hello"})
    assert st == 200
    guard.charge("hello", 0.6)  # 예산을 넘겼다고 치면
    st, out = A.dispatch("POST", "/api/story/understand", json.dumps({"family": fam}).encode(), {"X-Access-Code": "hello"})
    assert st == 402 and out["error"]["code"] == "budget_exhausted"
    # 엔진만 쓰는 요청은 막지 않는다
    st, _ = A.dispatch("POST", "/api/family/check", json.dumps({"family": fam}).encode())
    assert st == 200


def test_rate_limit(monkeypatch):
    monkeypatch.setenv("RATE_PER_MIN", "2")
    guard._hits.clear()
    fam = call("/api/preset", {"preset_id": "newly"})
    codes = [A.dispatch("POST", "/api/family/check", json.dumps({"family": fam}).encode(), {}, "9.9.9.9")[0]
             for _ in range(3)]
    assert codes == [200, 200, 429]


def test_review_with_several_changes():
    fam = call("/api/family/check", {"family": SINGLE_PARENT})["family"]
    goal = call("/api/goal/check", {"family": fam, "goal": {"type": "debt_free"}})["goal"]
    spec = {"option_id": "A", "label": "빚 먼저", "return_id": "safe",
            "policies": [{"policy": "extra_repayment", "item_id": "f4", "amount": 30}]}
    out = call("/api/review/compare", {"family": fam, "goal": goal, "spec": spec,
                                       "changes": {"income_delta": -50, "loan_rate_delta": 2, "lump": -100}})
    assert set(out["changes"]) == {"income_delta", "loan_rate_delta", "lump"}
    assert out["flow_after"] < out["flow_before"]
    assert out["hit_month_delta"] is not None and out["hit_month_delta"] >= 0  # 금리가 오르면 늦어지거나 같다
    st, err = A.dispatch("POST", "/api/review/compare", json.dumps({"family": fam, "goal": goal, "spec": spec, "changes": {}}).encode())
    assert st == 400


def test_call_ledger_records_tokens(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(guard, "CALLS_FILE", tmp_path / "calls.jsonl")
    usage = {"uncached_input_tokens": 100, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0,
             "output_tokens": 30, "cost_usd": 0.001}
    inner = SimpleNamespace(model="m", complete=lambda *a, **k: SimpleNamespace(usage=usage, model="m", latency_s=1.0,
                                                                                    tool_calls=[]))
    guard.MeteredProvider(inner, "local").complete("sys", [], role_key="7")
    rec = json.loads((tmp_path / "calls.jsonl").read_text(encoding="utf-8"))
    assert rec["role"] == "7" and rec["output_tokens"] == 30 and rec["cost_usd"] == 0.001


@pytest.mark.parametrize("pid, kept", [("newly", False), ("elder", True)])
def test_conditional_need_needs_home_and_age(pid, kept):
    fam = call("/api/preset", {"preset_id": pid})
    agreement = {"goal": "생활비 마련", "commitments": [{"commitment_id": "c1", "text": "주택연금으로 생활비를 받아요."}]}
    out = call("/api/recommend", {"family": fam, "agreement": agreement})["result"]
    needs = {r["need_id"] for r in out["recommendations"]}
    assert ("N_living_income_at_home" in needs) is kept
    assert bool(out["dropped_needs"]) is (not kept)


def test_must_keep_money_gets_principal_protected_products_only():
    fam = call("/api/preset", {"preset_id": "newly"})
    agreement = {"goal": "집", "commitments": [{"commitment_id": "c1", "text": "휴직 준비금을 따로 모아요."},
                                               {"commitment_id": "c2", "text": "대출 이자를 꼭 내요."}]}
    recs = call("/api/recommend", {"family": fam, "agreement": agreement})["result"]["recommendations"]
    leave = [r for r in recs if r["need_id"] == "N_leave_fund" and r.get("product_type_id")]
    assert leave and all(r["attributes"]["risk"] == "원금보장" for r in leave)
    assert not any(r["need_id"] == "N_debt_repayment" for r in recs)  # 전세대출만 있으면 '빨리 갚기' 아님
