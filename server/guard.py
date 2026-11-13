"""체험 코드·호출 제한·예산 보호(공개 체험판용).

- 체험 코드: 환경변수 ACCESS_CODES="코드1,코드2:3.0"(콜론 뒤는 그 코드의 예산 달러, 없으면 CODE_BUDGET_USD).
  ACCESS_CODES가 비어 있으면 코드 없이 쓸 수 있다(로컬 개발).
- 예산: AI 호출마다 실제 토큰 사용량으로 비용을 계산해 코드별·전체 합계에 더한다. 합계가 예산(BUDGET_USD)을 넘으면
  AI 호출을 막는다(계산엔진만 쓰는 요청은 막지 않는다). 마지막 호출 하나만큼은 넘칠 수 있으니, Anthropic 콘솔의
  월 사용 한도도 함께 걸어 두는 것을 권한다.
- 호출 제한: IP마다 1분에 RATE_PER_MIN번(메모리 기준).
- 저장: UPSTASH_REDIS_REST_URL·TOKEN이 있으면 Upstash Redis(서버리스 여러 인스턴스가 같은 합계를 봄),
  없으면 로컬 파일(data/usage/usage.json), 파일을 못 쓰는 환경이면 메모리.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE_FILE = ROOT / "data/usage/usage.json"
CALLS_FILE = ROOT / "data/usage/calls.jsonl"  # 호출 한 번마다 한 줄(토큰·비용). 파일 저장소일 때만
_lock = threading.Lock()
_mem: dict[str, float] = {}
_hits: dict[str, list[float]] = {}


class GuardError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _env_float(k: str, default: float) -> float:
    try:
        return float(os.environ.get(k) or default)
    except ValueError:
        return default


def codes() -> dict[str, float]:
    out = {}
    for part in (os.environ.get("ACCESS_CODES") or "").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, usd = part.partition(":")
        try:
            out[code.strip()] = float(usd) if usd else _env_float("CODE_BUDGET_USD", 1.5)
        except ValueError:
            out[code.strip()] = _env_float("CODE_BUDGET_USD", 1.5)
    return out


def access_required() -> bool:
    return bool(codes())


def total_budget() -> float:
    return _env_float("BUDGET_USD", 5.0)


# ---------- 저장소 ----------
def _redis_env() -> tuple[str, str]:
    """Upstash Redis REST 주소·토큰. Vercel 마켓플레이스로 연결하면 KV_REST_API_* 이름으로 들어오기도 한다."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL") or ""
    tok = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN") or ""
    return url, tok


def _upstash(cmd: list) -> object:
    url, tok = _redis_env()
    req = urllib.request.Request(url, data=json.dumps(cmd).encode(), headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["result"]


def backend() -> str:
    if all(_redis_env()):
        return "upstash"
    if os.environ.get("VERCEL"):
        return "memory"  # 서버리스 파일시스템은 인스턴스마다 따로라서 쓰지 않는다
    return "file"


def _file_read() -> dict:
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def spent(key: str) -> float:
    b = backend()
    if b == "upstash":
        try:
            return float(_upstash(["GET", f"oneheart:spent:{key}"]) or 0)
        except Exception:  # noqa: BLE001 - 저장소가 안 되면 보수적으로 막는다
            return float("inf")
    if b == "file":
        return float(_file_read().get(key, 0))
    return _mem.get(key, 0.0)


def _add(key: str, usd: float) -> None:
    b = backend()
    if b == "upstash":
        try:
            _upstash(["INCRBYFLOAT", f"oneheart:spent:{key}", str(usd)])
        except Exception:  # noqa: BLE001
            pass
        return
    with _lock:
        if b == "file":
            d = _file_read()
            d[key] = round(d.get(key, 0) + usd, 6)
            d["_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            USAGE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            _mem[key] = _mem.get(key, 0.0) + usd


# ---------- 검사 ----------
def check_code(code: str | None) -> str:
    """체험 코드를 확인하고 정규화된 코드(예산 키)를 돌려준다."""
    cs = codes()
    if not cs:
        return "local"
    code = (code or "").strip()
    if code not in cs:
        raise GuardError("access_denied", "체험 코드가 맞지 않아요", 401)
    return code


def check_rate(ip: str) -> None:
    limit = int(_env_float("RATE_PER_MIN", 20))
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(q) >= limit:
            _hits[ip] = q
            raise GuardError("rate_limited", "요청이 너무 잦아요. 1분 뒤에 다시 해 주세요", 429)
        q.append(now)
        _hits[ip] = q


def check_budget(code_key: str) -> None:
    if (os.environ.get("LLM_PROVIDER") or "").lower() == "replay":
        return  # 재생 공급자(개발용·mock)는 실제 AI를 안 불러 비용이 0이라 예산으로 막지 않는다
    if spent("total") >= total_budget():
        raise GuardError("budget_exhausted", "체험판 전체 AI 예산을 다 썼어요. 운영자에게 알려 주세요", 402)
    cs = codes()
    if code_key in cs and spent(f"code:{code_key}") >= cs[code_key]:
        raise GuardError("budget_exhausted", "이 체험 코드로 쓸 수 있는 AI 사용량을 다 썼어요", 402)


def charge(code_key: str, usd: float) -> None:
    if usd <= 0:
        return
    _add("total", usd)
    _add(f"code:{code_key}", usd)


def status(code_key: str | None = None) -> dict:
    out = {"backend": backend(), "access_required": access_required(),
           "total_spent_usd": round(spent("total"), 4), "total_budget_usd": total_budget()}
    if code_key and code_key in codes():
        out["code_spent_usd"] = round(spent(f"code:{code_key}"), 4)
        out["code_budget_usd"] = codes()[code_key]
    return out


class MeteredProvider:
    """요청 하나 동안 쓰는 공급자 래퍼: 호출마다 비용을 체험 코드와 전체 합계에 더하고, 예산을 넘으면 다음 호출을 막는다."""

    def __init__(self, inner, code_key: str):
        self.inner, self.code_key = inner, code_key
        self.model = getattr(inner, "model", "")
        self.cost_usd = 0.0

    def complete(self, *a, **kw):
        check_budget(self.code_key)
        res = self.inner.complete(*a, **kw)
        u = res.usage or {}
        usd = float(u.get("cost_usd", 0) or 0)
        self.cost_usd += usd
        charge(self.code_key, usd)
        if backend() == "file" and usd > 0:
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "code": self.code_key, "role": kw.get("role_key"),
                   "model": res.model, "latency_s": res.latency_s, "tool_calls": len(res.tool_calls),
                   **{k: u.get(k, 0) for k in ("uncached_input_tokens", "cache_read_input_tokens",
                                               "cache_creation_input_tokens", "output_tokens", "cost_usd")}}
            with _lock:
                CALLS_FILE.parent.mkdir(parents=True, exist_ok=True)
                with CALLS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return res

    def tool_result_message(self, *a, **kw):
        return self.inner.tool_result_message(*a, **kw)
