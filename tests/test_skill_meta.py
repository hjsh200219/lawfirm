"""스킬 머리말(FR-21)·uv inline 의존 상한(FR-11)."""
import os
import re

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
