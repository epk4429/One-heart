"""공동 목표 2단계 '통계 기준'(llm/world_size.py): 원문 인용·집값·API."""

import copy

from llm import family as F
from llm import world_size as W
from tests.test_goal_flow import call


def test_quotes_are_in_the_official_text():
    assert W.check_quotes() == []


def test_regions_split_gwangju_into_sub_areas():
    names = [r["name"] for r in W.regions()]
    assert names[:3] == ["전국", "수도권", "지방권"]
    assert "서울" in names and "전남권역" in names and "광주권역" in names and "광주" not in names


def test_home_lines_come_from_the_snapshot():
    h = W.home("11000", "apt")  # 서울 아파트 중위 10억 8,600만원(2026.9)
    by = {l["label"]: l["display"] for l in h["lines"]}
    assert by["서울 아파트 중간 가격"] == "10억 8,600만원"
    assert by["그 비율이면 직접 마련할 돈"] == "약 3억 2,580만원"   # 30%
    assert "3%" in by["집 살 때 내는 취득세(1주택)"]
    assert "1%" in W.home("00001", "apt")["lines"][3]["display"]  # 수도권 아파트 중위 5억 7,500만원 → 6억 이하 1%
    assert "1~3%" in W.home("11000", "all")["lines"][3]["display"]  # 서울 주택 전체 중위 8억 1,673만원 → 6~9억 구간
    assert W.home("nope", "x")["region"] == "00000"


def test_size_api_returns_world_only_for_home():
    raw = F.preset("newly")
    st, out = call("/api/goal/size", {"family": raw, "world": {"region": "41000", "type": "row"}})
    assert st == 200 and out["world"]["region"] == "41000" and out["world"]["lines"][0]["label"].startswith("경기 연립")
    other = copy.deepcopy(raw)
    other["goal_input"] = {"category": "lump", "fields": {"purpose": "결혼"}}
    st, out = call("/api/goal/size", {"family": other})
    assert st == 200 and out["world"] is None
