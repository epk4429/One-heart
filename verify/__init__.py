"""검증 구조(docs/07_검증구조.md).

LLM 출력이 화면에 나가기 전에 네 겹으로 검사한다.
  1. 자리표시 해석: {{fact:ID}}, {{quote:ID}}만 숫자로 바꾼다
  2. 숫자 스캔: 자리표시 밖에 직접 쓴 숫자를 찾는다
  3. 근거 대조: 참조 id가 실제로 있는지
  4. 산술 일관성: 합의안 숫자끼리 맞는지
"""

from .core import (
    VerificationRecord,
    check_agreement,
    check_refs,
    find_numbers,
    render,
    scan_numbers,
    verify_texts,
)

__all__ = [
    "VerificationRecord",
    "check_agreement",
    "check_refs",
    "find_numbers",
    "render",
    "scan_numbers",
    "verify_texts",
]
