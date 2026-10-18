import os
import shutil
import subprocess
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import verify_docs  # noqa: E402

# check() 가 가드 없이 여는 파일 — 임시 repo 에 최소로 복사한다
_REQUIRED = [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", ".codex-plugin/plugin.json", "AGENTS.md"]


def test_docs_links_paths_versions():
    errors, _ = verify_docs.check()
    assert errors == []


def _tmp_repo(tmp_path, monkeypatch, ignore):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel in _REQUIRED:
        os.makedirs(os.path.dirname(os.path.join(str(tmp_path), rel)) or str(tmp_path), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(str(tmp_path), rel))
    (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    monkeypatch.setattr(verify_docs, "ROOT", str(tmp_path))
    monkeypatch.setattr(verify_docs, "DOCS", [])


def _orphans():
    errors, _ = verify_docs.check()
    return [e for e in errors if e.startswith("고아 문서")]


def test_orphan_check_skips_git_ignored_run_folder(tmp_path, monkeypatch):
    # meta-plan 실행 폴더(.gitignore 로 빠진 docs/ 문서)는 고아로 잡지 않는다
    _tmp_repo(tmp_path, monkeypatch, "docs/prd/*\n")
    run = tmp_path / "docs" / "prd" / "x"
    run.mkdir(parents=True)
    (run / "00-brief.md").write_text("x", encoding="utf-8")
    (run / "prd.md").write_text("x", encoding="utf-8")
    assert _orphans() == []


def test_orphan_check_still_reports_tracked_orphan(tmp_path, monkeypatch):
    _tmp_repo(tmp_path, monkeypatch, "docs/prd/*\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("x", encoding="utf-8")
    assert _orphans() == ["고아 문서(어느 검사 대상 문서도 링크하지 않음): docs/x.md"]


def test_orphan_check_without_git_reports_orphan(tmp_path, monkeypatch):
    # git 실행 파일이 없으면 무시 여부를 모른다 — 고아를 그대로 오류로 낸다
    _tmp_repo(tmp_path, monkeypatch, "docs/prd/*\n")
    run = tmp_path / "docs" / "prd" / "x"
    run.mkdir(parents=True)
    (run / "prd.md").write_text("x", encoding="utf-8")

    def no_git(*a, **k):
        raise OSError("git 없음")

    monkeypatch.setattr(verify_docs.subprocess, "run", no_git)
    assert _orphans() == ["고아 문서(어느 검사 대상 문서도 링크하지 않음): docs/prd/x/prd.md"]


# ── FR-19 검사 대상 31개 · FR-36 .py 머리말 경로 · FR-32 계약 점검 기록 나이 ──
NEW_DOCS = ["skills/intent-brief/SKILL.md", "skills/certified-letter/SKILL.md", "skills/complaint-drafter/SKILL.md",
            "skills/criminal-procedure-simulator/SKILL.md", "skills/criminal-settlement/SKILL.md",
            "skills/fact-confirmation/SKILL.md", "skills/sentencing-predictor/SKILL.md", "references/law-lookup.md",
            "references/cta-config.md"]


def test_docs_list_has_31_including_skill_docs():
    assert len(verify_docs.DOCS) == 31 and set(NEW_DOCS) <= set(verify_docs.DOCS)


def test_bad_path_in_new_doc_is_error(tmp_path, monkeypatch):
    _tmp_repo(tmp_path, monkeypatch, "")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "cta-config.md").write_text("설정은 `skills/nope/x.py` 를 본다", encoding="utf-8")
    monkeypatch.setattr(verify_docs, "DOCS", ["references/cta-config.md"])
    errors, _ = verify_docs.check()
    assert errors == ["references/cta-config.md: 없는 경로 `skills/nope/x.py`"]


def test_py_docstring_path_checked(tmp_path, monkeypatch):
    _tmp_repo(tmp_path, monkeypatch, "")
    d = tmp_path / "skills" / "x" / "scripts"
    d.mkdir(parents=True)
    (d / "y.py").write_text('"""사용: `skills/x/scripts/gone.py` 를 부른다."""\n', encoding="utf-8")
    errors, _ = verify_docs.check()
    assert errors == ["skills/x/scripts/y.py: 머리말의 없는 경로 `skills/x/scripts/gone.py`"]


RECORD = """## 판 올림 기록

| 날짜 | 판 | Health Stack | 법제처 점검 exit | 빅케이스 점검 exit | 비고 |
|---|---|---|---|---|---|
%s
"""


def _quality(tmp_path, monkeypatch, rows):
    _tmp_repo(tmp_path, monkeypatch, "")
    (tmp_path / "docs").mkdir(exist_ok=True)
    if rows is not None:
        (tmp_path / "docs" / "QUALITY.md").write_text(RECORD % "\n".join(rows), encoding="utf-8")
    monkeypatch.setattr(verify_docs, "DOCS", [])
    import datetime
    return datetime.date(2026, 10, 18)


def test_contract_age_warning(tmp_path, monkeypatch):
    import datetime
    today = _quality(tmp_path, monkeypatch, ["| %s | 0.8.0 | 5/5 | 0 | 4 | |" % (datetime.date(2026, 10, 18) - datetime.timedelta(days=91))])
    assert "91일 전" in verify_docs.contract_age_warning(today)
    monkeypatch.setenv("VERIFY_DOCS_TODAY", "2026-10-18")
    errors, warnings = verify_docs.check()
    # 임시 repo 의 QUALITY.md 는 링크하는 문서가 없어 고아로 잡힌다(픽스처 구성) — 그 밖의 오류는 0
    assert [e for e in errors if "docs/QUALITY.md" not in e] == [] and len(warnings) == 1 and "91일 전" in warnings[0]


def test_contract_age_ok_within_90(tmp_path, monkeypatch):
    import datetime
    today = _quality(tmp_path, monkeypatch, ["| %s | 0.8.0 | 5/5 | 1 | - | |" % (datetime.date(2026, 10, 18) - datetime.timedelta(days=89))])
    assert verify_docs.contract_age_warning(today) is None


def test_contract_age_skipped_rows_only(tmp_path, monkeypatch):
    today = _quality(tmp_path, monkeypatch, ["| 2026-10-18 | 0.8.0 | 5/5 | - | - | 발동 조건 아님 |", "| 2026-10-17 | 0.7.1 | 5/5 | - | 4 | |"])
    assert "실제로 대조한 행" in verify_docs.contract_age_warning(today)


def test_contract_age_no_table(tmp_path, monkeypatch):
    today = _quality(tmp_path, monkeypatch, None)
    assert "표가 없음" in verify_docs.contract_age_warning(today)


def test_contract_age_today_env(tmp_path, monkeypatch):
    _quality(tmp_path, monkeypatch, ["| 2026-01-01 | 0.8.0 | 5/5 | 0 | 0 | |"])
    monkeypatch.setenv("VERIFY_DOCS_TODAY", "2026-03-01")
    assert verify_docs.contract_age_warning() is None
