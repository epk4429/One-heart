"""가족방 저장소(2026-11-17 형님 결정: 가족이 각자 자기 화면·링크로 같은 가족방에 참여).

한 사람(방장)이 가족방을 만들면 서버가 방 번호와 구성원마다 열쇠(token)를 만들어 준다. 구성원은 `?r=방번호&k=열쇠` 링크로 들어온다.
- 저장하는 것: 화면 상태 한 덩어리(state, JSON) + 버전 + 구성원별 열쇠 + 방을 만든 체험 코드. 계산·AI는 예전처럼 요청마다 다시 검사한다.
- 저장소: Upstash Redis(Vercel), 로컬은 파일(data/rooms/<번호>.json), 파일을 못 쓰는 환경은 메모리.
- 동시에 고치면: 저장할 때 '내가 받은 버전'(base_version)을 같이 보낸다. 서버 버전이 더 새로우면 저장하지 않고(409) 서버의 최신 상태를
  돌려준다. 화면이 내 변경과 합쳐서(web/js/app.js mergeState) 다시 보낸다. 서버는 합치지 않는다.
- 방은 만든 날부터 30일 뒤에 지운다(Redis는 만료, 파일·메모리는 읽을 때 검사).
- 열쇠는 방 안에서만 의미가 있다. 방장 열쇠로만 구성원 열쇠를 다시 볼 수 있다.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

from . import guard

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data/rooms"
TTL_SECONDS = 30 * 24 * 3600
MAX_STATE_BYTES = 900 * 1024  # Upstash 요청 한도(1MB) 안
_lock = threading.Lock()
# Redis 안에서 '내가 받은 버전 == 지금 버전'일 때만 쓴다(같은 방을 두 사람이 동시에 저장해도 한쪽만 들어감). 성공하면 "OK", 아니면 지금 값을 돌려준다.
_CAS = "local v = redis.call('GET', KEYS[1]); if not v then return v end; local d = cjson.decode(v); if d.version ~= tonumber(ARGV[1]) then return v end; redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3]); return 'OK'"
_mem: dict[str, dict] = {}


def available() -> bool:
    """가족방을 쓸 수 있는지. Vercel에서 Upstash가 없으면 인스턴스마다 기억이 달라 방이 사라지므로 쓰지 않는다(로컬 파일·Upstash만)."""
    return guard.backend() in ("upstash", "file")


class RoomError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _key(room_id: str) -> str:
    return f"oneheart:room:{room_id}"


def _valid_id(room_id: str) -> bool:
    return isinstance(room_id, str) and 8 <= len(room_id) <= 32 and room_id.isalnum()


def _read(room_id: str) -> dict | None:
    if not _valid_id(room_id):
        return None
    b = guard.backend()
    if b == "upstash":
        raw = guard._upstash(["GET", _key(room_id)])
        return json.loads(raw) if raw else None
    if b == "file":
        p = DIR / f"{room_id}.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    else:
        d = _mem.get(room_id)
    if d and time.time() - d.get("created", 0) > TTL_SECONDS:
        return None
    return d


def _write(room_id: str, d: dict) -> None:
    b = guard.backend()
    if b == "upstash":
        guard._upstash(["SET", _key(room_id), json.dumps(d, ensure_ascii=False), "EX", str(TTL_SECONDS)])
    elif b == "file":
        DIR.mkdir(parents=True, exist_ok=True)
        (DIR / f"{room_id}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    else:
        _mem[room_id] = d


def _check_state(state) -> None:
    if not isinstance(state, dict):
        raise RoomError("bad_state", "가족방 상태가 올바르지 않아요")
    if len(json.dumps(state, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
        raise RoomError("too_large", "가족방 상태가 너무 커요", 413)


# 구성원 몫(구성원 id로 칸이 나뉜 값). 저장하는 사람은 자기 칸만 새로 쓰거나 고칠 수 있다. 남의 칸을 바꾸거나 새로 넣은 부분은 서버 값으로 되돌린다(지우는 것은 '다시 이야기 나누기' 같은 되돌리기라 허용).
MEMBER_MAPS = ("iv", "approvals", "r1", "sub1", "signed", "rd")


def _strip_foreign(old: dict, new: dict, mid: str) -> list[str]:
    """new에서 mid가 아닌 구성원의 칸이 old와 다르면 old 값으로 되돌린다(없던 칸이면 지운다). 되돌린 위치 이름을 돌려준다.
    거절하지 않고 되돌리는 이유: 화면이 읽다가 빈 칸을 만들어 두는 일 같은 무해한 차이로 정상 저장까지 막히면 가족 화면이 서로 안 맞는다."""
    fixed: list[str] = []

    def fix(o, n, label):
        if not isinstance(n, dict):
            return
        o = o if isinstance(o, dict) else {}
        for k in list(n):
            if k != mid and (k not in o or o[k] != n[k]):
                if k in o:
                    n[k] = o[k]
                else:
                    del n[k]
                fixed.append(label)
    for key in MEMBER_MAPS:
        fix(old.get(key), new.get(key), key)
    op, np_ = old.get("pg"), new.get("pg")
    if isinstance(np_, list):
        for i, page in enumerate(np_):
            if isinstance(page, dict):
                o = op[i] if isinstance(op, list) and i < len(op) and isinstance(op[i], dict) else {}
                fix(o.get("replies"), page.get("replies"), "pg.replies")
    return fixed


def create(state: dict, member_ids: list[str], code_key: str) -> dict:
    """방을 만든다. 첫 번째 구성원(member_ids[0])이 방장이다. {room_id, version, tokens{member_id: 열쇠}}."""
    _check_state(state)
    ids = [str(m) for m in member_ids if str(m)]
    if not 1 <= len(ids) <= 12 or len(set(ids)) != len(ids):
        raise RoomError("bad_members", "구성원이 올바르지 않아요")
    room_id = secrets.token_hex(8)
    tokens = {m: secrets.token_urlsafe(12).replace("-", "a").replace("_", "b") for m in ids}
    d = {"room_id": room_id, "created": time.time(), "version": 1, "host": ids[0], "tokens": tokens, "code_key": code_key, "state": state,
         "seen": {ids[0]: time.time()}}  # 링크로 처음 들어온 시각(방장은 만든 때)
    with _lock:
        _write(room_id, d)
    return {"room_id": room_id, "version": 1, "tokens": tokens}


def member_of(room_id: str, token: str) -> tuple[dict, str]:
    """열쇠가 맞으면 (방, 구성원 id). 아니면 RoomError."""
    d = _read(room_id)
    if not d:
        raise RoomError("room_not_found", "가족방을 찾지 못했어요(없거나 30일이 지났어요)", 404)
    for mid, tok in d["tokens"].items():
        if token and secrets.compare_digest(tok, str(token)):
            return d, mid
    raise RoomError("bad_token", "이 링크의 열쇠가 맞지 않아요", 403)


def get(room_id: str, token: str, since: int | None = None) -> dict:
    d, mid = member_of(room_id, token)
    if mid not in d.get("seen", {}):  # 처음 들어온 구성원만 기록한다(몇 초마다 부르는 읽기에서 쓰기가 생기지 않게)
        with _lock:
            d2 = _read(room_id)
            if d2 and mid not in d2.setdefault("seen", {}):
                d2["seen"][mid] = time.time()
                if guard.backend() == "upstash":  # 상태 저장과 겹쳐도 버전 검사로 안전하게: 같은 버전으로 다시 쓰되 seen만 바꾼다
                    guard._upstash(["EVAL", _CAS, "1", _key(room_id), str(d2["version"]), json.dumps(d2, ensure_ascii=False), str(TTL_SECONDS)])
                else:
                    _write(room_id, d2)
    out = {"room_id": room_id, "version": d["version"], "member_id": mid, "host": d["host"], "is_host": mid == d["host"]}
    if since is None or since != d["version"]:
        out["state"] = d["state"]
    return out


def save(room_id: str, token: str, base_version: int, state: dict) -> dict:
    """저장. base_version이 서버 버전과 같을 때만 저장한다. 다르면 {conflict: True, version, state}."""
    _check_state(state)
    with _lock:
        d, mid = member_of(room_id, token)
        if int(base_version) != d["version"]:
            return {"conflict": True, "version": d["version"], "state": d["state"], "member_id": mid}
        _strip_foreign(d.get("state") or {}, state, mid)  # 남의 칸을 바꾼 부분은 서버 값으로 되돌린다
        nd = {**d, "state": state, "version": d["version"] + 1}
        if guard.backend() == "upstash":  # 서버리스 인스턴스가 여럿이라 프로세스 잠금으로는 부족 → Redis 안에서 버전을 검사하고 쓴다
            res = guard._upstash(["EVAL", _CAS, "1", _key(room_id), str(int(base_version)), json.dumps(nd, ensure_ascii=False), str(TTL_SECONDS)])
            if res != "OK":
                cur = json.loads(res)
                return {"conflict": True, "version": cur["version"], "state": cur["state"], "member_id": mid}
        else:
            _write(room_id, nd)
        return {"conflict": False, "version": nd["version"], "member_id": mid}


def tokens(room_id: str, token: str) -> dict:
    """방장만: 구성원마다 열쇠(링크를 다시 보여 줄 때)."""
    d, mid = member_of(room_id, token)
    if mid != d["host"]:
        raise RoomError("host_only", "방장만 볼 수 있어요", 403)
    return {"tokens": d["tokens"], "host": d["host"], "seen": sorted(d.get("seen", {}))}


def code_of(room_id: str, token: str) -> str:
    """방을 만든 체험 코드(참가 구성원이 AI를 쓸 때 이 코드의 예산으로 센다)."""
    d, _ = member_of(room_id, token)
    return d.get("code_key") or "local"


def delete(room_id: str, token: str) -> dict:
    """방장만: 가족방을 서버에서 지운다('모두 지우고 새로 시작'). 다른 가족의 링크도 함께 못 쓰게 된다."""
    d, mid = member_of(room_id, token)
    if mid != d["host"]:
        raise RoomError("host_only", "방장만 지울 수 있어요", 403)
    b = guard.backend()
    if b == "upstash":
        guard._upstash(["DEL", _key(room_id)])
    elif b == "file":
        try:
            (DIR / f"{room_id}.json").unlink()
        except OSError:
            pass
    else:
        _mem.pop(room_id, None)
    return {"deleted": True}
