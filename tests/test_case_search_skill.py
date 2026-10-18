"""case-search 스킬 — 법제처(공식 원문)와 빅케이스 두 원천을 안내하고, 안내한 명령이 실제로 있는지."""
import os
import re

from conftest import ROOT

SKILL = os.path.join(ROOT, "skills", "case-search", "SKILL.md")
LAWAPI = os.path.join(ROOT, "skills", "intent-brief", "scripts", "lawapi.py")
BIGCASE = os.path.join(ROOT, "skills", "case-search", "scripts", "bigcase.py")
FOREIGN = os.path.join(ROOT, "skills", "case-search", "scripts", "foreigncase.py")


def read(p):
    return open(p, encoding="utf-8").read()


def _subs(path):
    return set(re.findall(r'add_parser\("([a-z-]+)"\)', read(path)))


def _front(text):
    return text.split("---")[1]


def test_lawapi_path_in_skill_resolves():
    text = read(SKILL)
    paths = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.py)", text)
    assert "skills/intent-brief/scripts/lawapi.py" in paths
    for p in paths:
        assert os.path.isfile(os.path.join(ROOT, p)), p


def test_documents_core_lawapi_commands():
    """법령·조문·판례·헌재·법령해석례·용어·키 — 법제처 쪽 핵심 명령을 모두 안내한다."""
    used = set(re.findall(r"`LAW ([a-z-]+)", read(SKILL)))
    assert {"law", "prec-search", "prec", "search", "detail", "term", "key"} <= used


def test_documented_commands_exist():
    text = read(SKILL)
    law, bc, fx = _subs(LAWAPI), _subs(BIGCASE) | {"get", "post"}, _subs(FOREIGN)
    for sub in re.findall(r"`LAW ([a-z-]+)", text):
        assert sub in law, ("lawapi.py", sub)
    for sub in re.findall(r"`BC ([a-z-]+)", text):
        assert sub in bc, ("bigcase.py", sub)
    for sub in re.findall(r"`FX ([a-z-]+)", text):
        assert sub in fx, ("foreigncase.py", sub)


def test_search_targets_exist():
    targets = set(re.search(r"TARGETS = \{([^}]+)\}", read(LAWAPI)).group(1).replace('"', "").replace(" ", "").split(","))
    for t in re.findall(r"`LAW (?:search|detail) ([a-z]+)", read(SKILL)):
        assert t in targets, t


def test_frontmatter_allows_python_and_triggers_law():
    head = _front(read(SKILL))
    allowed = re.search(r"(?m)^allowed-tools:(.*)$", head).group(1)
    assert "uv run" in allowed and "python" in allowed
    desc = re.search(r"(?m)^description:(.*)$", head).group(1)
    for word in ("법제처", "법령", "조문", "헌재"):
        assert word in desc, word


def test_description_catches_us_opinion_questions():
    """「미국 연방대법원 ○○ 판결문 본문 인용」 질문에서 자동 선택 0/12(QUALITY.md FR-26) — 그런 질문의 낱말과
    해외 판결문을 웹·curl 보다 이 스킬로 확인하라는 문장이 description 에 있어야 한다."""
    desc = re.search(r"(?m)^description:(.*)$", _front(read(SKILL))).group(1)
    for word in ("연방대법원", "Supreme Court", "SCOTUS", "판결문 원문", "영어 원문", "opinion", "citation"):
        assert word in desc, word
    assert re.search(r"웹 검색·curl 보다 이 스킬", desc)


def test_keys_come_from_input_window_not_chat():
    """키는 입력 창(`key set --prompt`)으로 받는다 — 명령행 인자(`key set <값>`)나 채팅으로 받으라는 안내가 없어야 한다."""
    text = read(SKILL)
    assert "LAW key set --prompt" in text and "FX key set us --prompt" in text
    assert not re.search(r"key set (?:us |de )?['\"<]", text)
    assert "law-key-setup" in text and os.path.isfile(os.path.join(ROOT, "commands", "law-key-setup.md"))


def test_without_bigcase_account_law_only():
    """빅케이스 계정이 없으면 setup 으로 끌고 가지 않고 법제처(·해외 판례)만 조회한다."""
    text = read(SKILL)
    assert "빅케이스 없이 진행한다" in text
    assert "그 자리에서 setup" not in text


def test_foreign_commands_documented():
    used = set(re.findall(r"`FX ([a-z-]+)", read(SKILL)))
    assert {"us-search", "us-opinion", "de-search", "de-case", "key"} <= used


def test_us_citation_rule_line():
    """FR-26 — 미국 판례 본문은 검색 결과의 식별자로만(측정은 D-02 승인 범위 밖이라 미실행)."""
    t = open(os.path.join(ROOT, "skills", "case-search", "SKILL.md"), encoding="utf-8").read()
    assert "`us-opinion` 은 같은 대화의 `us-search` 결과에 나온 `opinion_id` 로만 부른다" in t
