"""개발 전용 문서 검사 — 상대 링크·백틱 경로·파일명 실존, docs/ 고아 문서, 매니페스트(Claude 둘·Codex) 버전 일치, AGENTS.md 줄 수.

사용: python3 dev/verify_docs.py      (문제 있으면 종료 코드 1)
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["AGENTS.md", "ARCHITECTURE.md", "README.md", "docs/QUALITY.md", "docs/exec-plans/tech-debt-tracker.md",
        "docs/harness/principles.md", "docs/harness/maturity-framework.md", "docs/harness/fix-catalog.md",
        "docs/harness/harness-setup.md", "docs/harness/gc-history.md", "docs/case-search/lbox/README.md",
        "docs/case-search/bigcase-api.md", "skills/case-search/SKILL.md", "commands/case-search-setup.md",
        "commands/law-key-setup.md", "skills/litigation-calc/SKILL.md", "skills/brainstorming-lawfirm/SKILL.md",
        "skills/review-contract/SKILL.md", "skills/triage-nda/SKILL.md", "skills/independent-review/SKILL.md",
        "skills/site-api/SKILL.md", "references/outline-approval.md"]
ENTRY_MAX = 120
_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
# 백틱 안의 repo 경로 — 디렉터리 접두사로 시작하는 것만 본다(명령·예시 문자열 제외).
_PATH = re.compile(r"`((?:skills|tests|dev|docs|\.claude-plugin|\.claude)/[^`*<>\s]*|ARCHITECTURE\.md|README\.md)`")
# 백틱 안의 접두사 없는 파일명(`_paths.py`, `phrases.json`) — repo 어딘가에 같은 이름이 있어야 한다.
_NAME = re.compile(r"`([\w.-]+\.(?:py|md|json))`")
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "_out"}


def _repo_files():
    names, rels = set(), set()
    for d, subdirs, files in os.walk(ROOT):
        subdirs[:] = [s for s in subdirs if s not in _SKIP_DIRS]
        for f in files:
            names.add(f)
            rels.add(os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/"))
    return names, rels


def _git_ignored(rel):
    # 작업 산출물(meta-plan 실행 폴더 등)은 .gitignore 로 빠진다 — 고아 검사 대상이 아니다
    try:
        return subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", rel]).returncode == 0
    except OSError:
        return False


def check():
    errors, warnings = [], []
    names, rels = _repo_files()
    linked = set()
    for doc in DOCS:
        p = os.path.join(ROOT, doc)
        if not os.path.exists(p):
            errors.append("문서 없음: %s" % doc)
            continue
        text = open(p, encoding="utf-8").read()
        base = os.path.dirname(p)
        for target in _LINK.findall(text):
            if re.match(r"[a-z]+:", target):
                continue
            full = os.path.normpath(os.path.join(base, target))
            linked.add(os.path.relpath(full, ROOT).replace(os.sep, "/"))
            if not os.path.exists(full):
                errors.append("%s: 깨진 링크 %s" % (doc, target))
        for target in _PATH.findall(text):
            if not os.path.exists(os.path.join(ROOT, target.rstrip("/"))):
                errors.append("%s: 없는 경로 `%s`" % (doc, target))
        for name in _NAME.findall(text):
            if "/" not in name and name not in names:
                errors.append("%s: 없는 파일 `%s`" % (doc, name))
    for rel in sorted(r for r in rels if r.startswith("docs/") and r.endswith(".md")):
        if rel not in linked and not _git_ignored(rel):
            errors.append("고아 문서(어느 검사 대상 문서도 링크하지 않음): %s" % rel)
    plugin = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
    market = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
    mv = [x.get("version") for x in market.get("plugins", []) if x.get("name") == plugin["name"]]
    if mv != [plugin["version"]]:
        errors.append("버전 불일치: plugin.json %s / marketplace.json %s" % (plugin["version"], mv))
    codex = json.load(open(os.path.join(ROOT, ".codex-plugin", "plugin.json"), encoding="utf-8"))
    if (codex.get("name"), codex.get("version")) != (plugin["name"], plugin["version"]):
        errors.append("Codex 매니페스트 불일치: .codex-plugin/plugin.json %s %s / .claude-plugin %s %s"
                      % (codex.get("name"), codex.get("version"), plugin["name"], plugin["version"]))
    n = sum(1 for _ in open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8"))
    if n > ENTRY_MAX:
        errors.append("AGENTS.md %d줄 — 상한 %d줄(지도만 두고 상세는 docs/ 로)" % (n, ENTRY_MAX))
    return errors, warnings


def main():
    errors, warnings = check()
    for w in warnings:
        print("경고:", w)
    for e in errors:
        print("오류:", e)
    print("verify_docs: 오류 %d · 경고 %d" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
