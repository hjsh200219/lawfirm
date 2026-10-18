"""스킬 머리말(FR-21)·uv inline 의존 상한(FR-11)."""
import os
import re

import pytest

from conftest import ROOT

SKILLS = os.path.join(ROOT, "skills")


def _front(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    assert m, path
    return dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))


def test_every_skill_has_matching_name_and_description():
    dirs = sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))
    assert len(dirs) == 14
    for d in dirs:
        fm = _front(os.path.join(SKILLS, d, "SKILL.md"))
        assert fm.get("name") == d, d
        assert fm.get("description", "").strip(' "'), d


def test_agents_md_skill_count_matches():
    n = len([d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d))])
    assert "스킬 %d개" % n in open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()


DEP_FILES = ["skills/case-search/scripts/bigcase.py", "skills/site-api/scripts/discover.py", "skills/site-api/templates/client.py.tmpl"]


def test_uv_inline_dependencies_have_upper_bounds():
    deps = []
    for f in DEP_FILES:
        m = re.search(r"^# dependencies = \[(.*)\]$", open(os.path.join(ROOT, f), encoding="utf-8").read(), re.M)
        deps += re.findall(r'"([^"]+)"', m.group(1))
    assert len(deps) == 5
    assert all("<" in d for d in deps), deps  # 상한을 올릴 때는 Health Stack 셋째 줄을 돌린다(docs/QUALITY.md)


def test_new_skill_review_rule_in_agents():
    """FR-28 — 모델이 새로 만든 SKILL.md 는 변호사 검토·짝지은 평가 기록 뒤에만 main 에."""
    t = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    assert "모델이 처음부터 만든 새 스킬" in t and "짝지은 평가" in t
    assert sum(1 for _ in open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8")) <= 120


# ── FR-23 실패 3종(외부 장애·키 없음·입력 없음) 처리 문장 — 2026-10-18 14×3 점검표의 빈 칸 ──
FAILURE_LINES = [
    ("references/law-lookup.md", "`network_blocked`"),
    ("skills/case-search/SKILL.md", "`network_blocked`"),
    ("skills/case-search/SKILL.md", "무엇을 찾을지 한 번 묻는다"),
    ("skills/brainstorming-lawfirm/SKILL.md", "`LAW key status`"),
    ("skills/brainstorming-lawfirm/SKILL.md", "자료가 없으면 먼저 달라고"),
    ("skills/independent-review/SKILL.md", "받지 못했으면"),
    ("skills/review-contract/SKILL.md", "references/law-lookup.md"),
    ("skills/triage-nda/SKILL.md", "references/law-lookup.md"),
    ("skills/triage-nda/SKILL.md", "NDA 를 받지 못했으면"),
    ("skills/sentencing-predictor/SKILL.md", "[확인 필요: 양형위원회 조회 실패]"),
    ("skills/site-api/SKILL.md", "URL 이 없으면"),
    ("skills/site-api/SKILL.md", "타임아웃"),
]


@pytest.mark.parametrize("rel,phrase", FAILURE_LINES)
def test_skill_failure_handling_lines(rel, phrase):
    assert phrase in open(os.path.join(ROOT, rel), encoding="utf-8").read()
