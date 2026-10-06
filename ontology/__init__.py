"""온톨로지(docs/08_온톨로지.md). 어휘·상품 유형·규칙은 JSON, 탐색은 search.py."""

from .search import load, recommend, vocab_ids

__all__ = ["load", "recommend", "vocab_ids"]
