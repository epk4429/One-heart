"""가족방 저장소(server/rooms.py)와 방 API: 방장이 만들고, 구성원이 열쇠 링크로 같은 방에 들어와 저장한다(2026-11-17)."""

import json

import pytest

from server import guard, rooms
from server.app import dispatch


@pytest.fixture(autouse=True)
def _tmp_rooms(tmp_path, monkeypatch):
    monkeypatch.setattr(rooms, "DIR", tmp_path)
    monkeypatch.setattr(guard, "backend", lambda: "file")
    monkeypatch.delenv("ACCESS_CODES", raising=False)


def call(path, body, headers=None):
    st, out = dispatch("POST", path, json.dumps(body).encode(), headers or {}, "t")
    return st, out


def make(state=None, ids=("m0", "m1", "m2")):
    st, out = call("/api/room/create", {"state": state or {"fam": {"x": 1}}, "member_ids": list(ids)})
    assert st == 200, out
    return out


def test_create_gives_each_member_their_own_token():
    r = make()
    assert r["version"] == 1 and set(r["tokens"]) == {"m0", "m1", "m2"} and len(set(r["tokens"].values())) == 3


def test_get_identifies_member_by_token_and_hides_others():
    r = make()
    st, g = call("/api/room/get", {"room_id": r["room_id"], "token": r["tokens"]["m1"]})
    assert st == 200 and g["member_id"] == "m1" and g["is_host"] is False and g["state"] == {"fam": {"x": 1}}
    st, g0 = call("/api/room/get", {"room_id": r["room_id"], "token": r["tokens"]["m0"]})
    assert g0["is_host"] is True
    st, same = call("/api/room/get", {"room_id": r["room_id"], "token": r["tokens"]["m1"], "since": 1})
    assert "state" not in same and same["version"] == 1  # 바뀐 게 없으면 상태를 다시 보내지 않는다
    st, bad = call("/api/room/get", {"room_id": r["room_id"], "token": "nope"})
    assert st == 403 and bad["error"]["code"] == "bad_token"
    st, none = call("/api/room/get", {"room_id": "abcdef0123456789", "token": "x"})
    assert st == 404


def test_save_requires_latest_version_else_conflict_with_latest_state():
    r = make()
    rid, t1, t2 = r["room_id"], r["tokens"]["m1"], r["tokens"]["m2"]
    st, a = call("/api/room/save", {"room_id": rid, "token": t1, "base_version": 1, "state": {"v": "철수"}})
    assert st == 200 and a["conflict"] is False and a["version"] == 2
    st, b = call("/api/room/save", {"room_id": rid, "token": t2, "base_version": 1, "state": {"v": "영희"}})  # 영희는 옛 버전 기준
    assert st == 200 and b["conflict"] is True and b["version"] == 2 and b["state"] == {"v": "철수"}
    st, c = call("/api/room/save", {"room_id": rid, "token": t2, "base_version": 2, "state": {"v": "합침"}})
    assert c["conflict"] is False and c["version"] == 3


def test_only_host_can_see_all_tokens():
    r = make()
    st, ok = call("/api/room/tokens", {"room_id": r["room_id"], "token": r["tokens"]["m0"]})
    assert st == 200 and ok["tokens"] == r["tokens"]
    st, no = call("/api/room/tokens", {"room_id": r["room_id"], "token": r["tokens"]["m1"]})
    assert st == 403 and no["error"]["code"] == "host_only"


def test_bad_inputs():
    assert call("/api/room/create", {"state": "x", "member_ids": ["m0"]})[0] == 400
    assert call("/api/room/create", {"state": {}, "member_ids": ["m0", "m0"]})[0] == 400
    assert call("/api/room/create", {"state": {}, "member_ids": []})[0] == 400
    assert call("/api/room/create", {"state": {"big": "x" * (rooms.MAX_STATE_BYTES + 10)}, "member_ids": ["m0"]})[0] == 413


def test_room_is_created_with_access_code_and_members_use_it_for_ai(monkeypatch):
    monkeypatch.setenv("ACCESS_CODES", "FAMILY1:3.0")
    st, no = call("/api/room/create", {"state": {}, "member_ids": ["m0", "m1"]})
    assert st == 401  # 체험 코드 없이는 방을 못 만든다
    st, r = call("/api/room/create", {"state": {}, "member_ids": ["m0", "m1"]}, {"X-Access-Code": "FAMILY1"})
    assert st == 200
    # 구성원은 체험 코드 없이 방 열쇠만으로 가족 정보를 쓰는 요청(여기서는 계산만 하는 /api/family/check)을 보낼 수 있다
    from llm import family as F
    body = {"family": F.preset("newly")}
    st, _ = call("/api/family/check", body)
    assert st == 401
    st, out = call("/api/family/check", body, {"X-Room-Id": r["room_id"], "X-Room-Token": r["tokens"]["m1"]})
    assert st == 200, out
    st, _ = call("/api/family/check", body, {"X-Room-Id": r["room_id"], "X-Room-Token": "wrong"})
    assert st == 403


def test_tokens_report_who_has_joined():
    r = make()
    h = r["tokens"]["m0"]
    assert call("/api/room/tokens", {"room_id": r["room_id"], "token": h})[1]["seen"] == ["m0"]  # 방장은 만든 때부터
    call("/api/room/get", {"room_id": r["room_id"], "token": r["tokens"]["m1"]})
    assert call("/api/room/tokens", {"room_id": r["room_id"], "token": h})[1]["seen"] == ["m0", "m1"]
    # 저장해도 들어온 기록은 남는다
    call("/api/room/save", {"room_id": r["room_id"], "token": h, "base_version": 1, "state": {"a": 1}})
    assert call("/api/room/tokens", {"room_id": r["room_id"], "token": h})[1]["seen"] == ["m0", "m1"]


def test_rooms_available_only_with_shared_storage(monkeypatch):
    monkeypatch.setattr(guard, "backend", lambda: "memory")
    assert rooms.available() is False  # Vercel에서 Upstash 없이는 방을 만들지 않는다
    monkeypatch.setattr(guard, "backend", lambda: "upstash")
    assert rooms.available() is True


def test_room_save_and_get_are_not_ip_rate_limited(monkeypatch):
    """입력할 때마다 저장하고 몇 초마다 읽으므로 IP당 분당 호출 제한(20회)에 걸리면 안 된다. 방 만들기는 제한한다."""
    monkeypatch.setenv("RATE_PER_MIN", "3")
    guard._hits.clear()
    r = make()
    h = r["tokens"]["m0"]
    for i in range(10):
        st, _ = call("/api/room/get", {"room_id": r["room_id"], "token": h})
        assert st == 200
    v = 1
    for i in range(6):
        st, out = call("/api/room/save", {"room_id": r["room_id"], "token": h, "base_version": v, "state": {"i": i}})
        assert st == 200 and out["conflict"] is False
        v = out["version"]
    guard._hits.clear()
