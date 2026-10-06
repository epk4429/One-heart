"""LLM 공급자 어댑터(docs/09_시스템구성.md 4절).

프롬프트·스키마·검증은 공급자와 무관하게 같고, 이 파일만 공급자별로 다르다.
HF는 표준 라이브러리(urllib)로, Anthropic은 공식 SDK(anthropic)로 호출한다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path = ROOT / ".env") -> None:
    """.env를 os.environ에 채운다(이미 있는 값은 덮지 않음). 값은 절대 출력하지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""
    latency_s: float = 0.0
    raw_message: dict = field(default_factory=dict)  # 다음 턴에 그대로 되돌려 줄 assistant 메시지


class LLMError(RuntimeError):
    pass


def _post(url: str, headers: dict, body: dict, timeout: int = 180) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"HTTP {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise LLMError(f"연결 실패: {e}") from None


class HFProvider:
    """Hugging Face Inference Providers(OpenAI 호환 chat completions)."""

    URL = "https://router.huggingface.co/v1/chat/completions"

    def __init__(self, model: str, token: str | None = None):
        self.model = model
        self.token = token or os.environ.get("HF_TOKEN", "")
        if not self.token:
            raise LLMError("HF_TOKEN이 없어요(.env 확인)")
        self._json_mode_ok = True

    def complete(self, system: str, messages: list[dict], *, tools: list[dict] | None = None,
                 json_mode: bool = True, max_tokens: int = 2000, temperature: float = 0.1,
                 role_key: str | None = None, **_kw) -> LLMResult:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, *messages],
                "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                               "parameters": t["input_schema"]}} for t in tools]
        elif json_mode and self._json_mode_ok:
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        try:
            out = _post(self.URL, {"Authorization": f"Bearer {self.token}"}, body)
        except LLMError as e:
            if "response_format" in body and ("400" in str(e) or "422" in str(e)):
                self._json_mode_ok = False  # 제공자가 JSON 모드를 거부하면 프롬프트 지시로만
                body.pop("response_format")
                out = _post(self.URL, {"Authorization": f"Bearer {self.token}"}, body)
            else:
                raise
        msg = out["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {"_unparsed": args}
            calls.append(ToolCall(tc.get("id", ""), tc["function"]["name"], parsed))
        return LLMResult(text=msg.get("content") or "", tool_calls=calls, usage=out.get("usage", {}),
                         model=out.get("model", self.model), latency_s=round(time.time() - t0, 2),
                         raw_message={k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})

    def tool_result_message(self, call: ToolCall, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call.id, "content": content}


# 백만 토큰당 달러(입력, 출력). 캐시 쓰기는 입력의 1.25배, 캐시 읽기는 0.1배로 셈한다(실제보다 조금 크게 잡힐 수 있음).
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0),
          "claude-haiku-4-5": (1.0, 5.0), "claude-opus-5": (5.0, 25.0), "claude-fable-5-1": (10.0, 50.0)}


def anthropic_cost(model: str, u) -> float:
    pin, pout = PRICES.get(model, (10.0, 50.0))  # 모르는 모델은 비싸게 잡는다
    tin = (u.input_tokens or 0) + 1.25 * (u.cache_creation_input_tokens or 0) + 0.1 * (u.cache_read_input_tokens or 0)
    return (tin * pin + (u.output_tokens or 0) * pout) / 1_000_000


class AnthropicProvider:
    """Anthropic Messages API(공식 SDK). 시나리오 통합 테스트부터 쓴다.

    Claude Opus 5.5 기준 주의점:
    - 생각(thinking)은 항상 켜져 있고 끌 수 없다. 깊이는 output_config.effort로만 조절한다(역할마다 low/medium).
    - temperature 등 샘플링 값은 보내면 400이다(재현성은 엔진 시드와 출력 검사로 지킨다).
    - 생각 토큰도 max_tokens에 들어가므로 상한을 넉넉히 둔다.
    - 도구 왕복·재요청 때는 응답 content(생각 블록 포함)를 고치지 않고 그대로 되돌려 준다.
    - 안전 분류기가 거절하면(stop_reason=refusal) 서버 쪽 대체 모델로 다시 돌린다(fallbacks="default").
    """

    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    MIN_MAX_TOKENS = 16000

    def __init__(self, model: str, api_key: str | None = None, effort: str | None = None):
        try:
            import anthropic
        except ImportError:
            raise LLMError("anthropic 패키지가 없어요(pip install -r requirements.txt)") from None
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY가 없어요(.env 확인)")
        self._anthropic = anthropic
        # 일부 환경(예: 오래된 brotli가 깔린 anaconda)에서 응답 압축 해제가 깨져서 gzip만 받는다.
        self.client = anthropic.Anthropic(api_key=key, timeout=170.0, max_retries=2,
                                          default_headers={"Accept-Encoding": "gzip, deflate"})
        self.model = model
        # LLM_EFFORT를 정하면 모든 역할에 같은 깊이를 쓰고, 비우면 역할마다 정한 깊이(low/medium)를 쓴다.
        self.effort_override = effort or os.environ.get("LLM_EFFORT") or None

    def complete(self, system: str, messages: list[dict], *, tools: list[dict] | None = None,
                 json_mode: bool = True, max_tokens: int = 2000, temperature: float = 0.1,
                 role_key: str | None = None, effort: str | None = None, **_kw) -> LLMResult:
        a = self._anthropic
        kwargs = dict(model=self.model, system=system, messages=messages,
                      max_tokens=max(max_tokens, self.MIN_MAX_TOKENS),
                      output_config={"effort": self.effort_override or effort or "medium"},
                      betas=[self.FALLBACK_BETA], fallbacks="default")
        if tools:
            kwargs["tools"] = tools
        if tools or len(messages) > 1:
            # 같은 내용을 다시 읽는 호출(도구 왕복·재요청)에만 캐시를 건다. 한 번만 쓰는 호출에 걸면 쓰기 비용(1.25배)만 든다.
            kwargs["cache_control"] = {"type": "ephemeral"}
        t0 = time.time()
        try:
            resp = self.client.beta.messages.create(**kwargs)
        except a.APIConnectionError as e:
            raise LLMError(f"연결 실패: {e}") from None
        except a.APIStatusError as e:
            raise LLMError(f"HTTP {e.status_code}: {str(e.message)[:500]}") from None
        if resp.stop_reason == "refusal":
            cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
            raise LLMError(f"모델이 응답을 거절했어요(분류: {cat})")
        content = resp.to_dict()["content"]
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        if resp.stop_reason == "max_tokens" and not text:
            raise LLMError("응답이 max_tokens에서 잘렸어요")
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in content if b.get("type") == "tool_use"]
        u = resp.usage
        usage = {"input_tokens": (u.input_tokens or 0) + (u.cache_read_input_tokens or 0)
                 + (u.cache_creation_input_tokens or 0), "output_tokens": u.output_tokens or 0,
                 "uncached_input_tokens": u.input_tokens or 0, "cache_read_input_tokens": u.cache_read_input_tokens or 0,
                 "cache_creation_input_tokens": u.cache_creation_input_tokens or 0,
                 "cost_usd": round(anthropic_cost(resp.model or self.model, u), 6)}
        return LLMResult(text=text, tool_calls=calls, usage=usage, model=resp.model,
                         latency_s=round(time.time() - t0, 2),
                         raw_message={"role": "assistant", "content": content})

    def tool_result_message(self, call: ToolCall, content: str) -> dict:
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id, "content": content}]}


DEFAULT_MODELS = {"hf": "openai/gpt-oss-120b", "anthropic": "claude-sonnet-5-5"}  # 2026-10-06 사용자 결정: 비용 1/3


def get_provider(name: str | None = None, model: str | None = None):
    load_env()
    name = (name or os.environ.get("LLM_PROVIDER") or "hf").lower()
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(name, "")
    if name == "hf":
        return HFProvider(model)
    if name == "anthropic":
        return AnthropicProvider(model)
    if name == "replay":
        from .replay import ReplayProvider
        return ReplayProvider()
    raise LLMError(f"모르는 공급자: {name}")
