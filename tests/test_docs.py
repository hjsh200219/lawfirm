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
