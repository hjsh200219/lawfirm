"""내장 스킬 산출물 끝 안내(D-11 (c)+(d) — FR-14·FR-33·FR-34) · README 고지(FR-15·FR-16) · Node·docx 확인(FR-12).

D-11(2026-10-18 사용자 결정): 상담 안내는 기본으로 없고, 사용 변호사가 자기 사무소 정보를 넣었을 때만 붙는다.
원저작 출처는 README 에만 남긴다. 유의사항·책임 문장은 1종.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from conftest import ROOT

EMBEDDED = ["certified-letter", "complaint-drafter", "criminal-procedure-simulator", "criminal-settlement",
            "fact-confirmation", "sentencing-predictor"]
NOTICE = "본 문서는 AI가 작성한 초안입니다. AI는 실수할 수 있으며, 최종 검토와 제출 판단은 사용 변호사의 책임입니다."
RESP = "최종 검토와 제출 판단은 사용 변호사의 책임입니다"
CTA = os.path.join(ROOT, "references", "cta-config.md")
GEN_DIR = os.path.join(ROOT, "skills", "criminal-settlement", "scripts")


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def tracked(*pathspec):
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "--"] + list(pathspec), capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if p and os.path.exists(os.path.join(ROOT, p))]


# ── FR-33 유의사항 문장 1종(출처 cta-config.md) ──
def test_notice_sentence_lives_in_cta_config():
    assert NOTICE in open(CTA, encoding="utf-8").read()


@pytest.mark.parametrize("skill", EMBEDDED)
def test_embedded_skill_refers_to_cta_config(skill):
    t = read("skills/%s/SKILL.md" % skill)
    assert "references/cta-config.md" in t and "유의사항" in t


def test_notice_variants_only_in_cta_config():
    files = tracked("skills", "references", "README.md")
    hits = [f for f in files if f != "references/cta-config.md" and "AI가 작성한" in open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore").read()]
    assert hits == []


# ── FR-14 연락처 출처 · D-11 (c) 기본 없음 ──
_PHONE = re.compile(r"(?<!\d)01[016789]-\d{3,4}-\d{4}(?!\d)")
_MAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def test_no_contact_values_in_skills_references_or_manifests():
    files = tracked("skills", "references", "README.md", ".claude-plugin", ".codex-plugin", "hooks", "commands")
    bad = [f for f in files if _PHONE.search(open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore").read())
           or _MAIL.search(open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore").read())]
    assert bad == []


def test_cta_config_is_template_with_office_file():
    t = open(CTA, encoding="utf-8").read()
    assert "office.json" in t and "없으면" in t and "[상담 안내]" in t
    assert "생략하지 않는다" not in t.split("## 서식")[0] or "유의사항은 생략하지 않는다" in t
    assert "CTA는 생략하지 않는다" not in t


def test_readme_attribution_matches():
    t = read("README.md")
    assert "references/cta-config.md" in t and "사무소 정보를 넣었을 때만" in t
    assert "산출물 끝의 변호사 안내(CTA)는 `references/cta-config.md` 를 따릅니다" not in t


# ── FR-34 책임 문장 1종 ──
def test_responsibility_sentence_single_form():
    out = subprocess.run(["git", "-C", ROOT, "grep", "-h", "-o", "-E", '(최종 검토[^.。"]{0,25}책임[^.。"]{0,6}|책임지지 않습니다)',
                          "--", ".", ":!docs/prd", ":!tests/test_cta.py"], capture_output=True, text=True).stdout.splitlines()
    assert out and {o.rstrip(" .") for o in out} == {RESP}


@pytest.mark.parametrize("path,field", [(".claude-plugin/plugin.json", "description"), (".claude-plugin/marketplace.json", "description")])
def test_manifest_responsibility_sentence(path, field):
    assert RESP in json.load(open(os.path.join(ROOT, path), encoding="utf-8"))[field]


def test_codex_manifest_responsibility_sentence():
    ui = json.load(open(os.path.join(ROOT, ".codex-plugin", "plugin.json"), encoding="utf-8"))["interface"]
    assert RESP in ui["longDescription"]


# ── generate.js 설정 읽기(Node 만, docx 없이) ──
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="node 없음 — generate.js 설정 읽기 시험은 Node 가 있는 PC 에서")
def test_generate_js_reads_office_file_and_notice(tmp_path):
    js = ("const c=require(%r); process.stdout.write(JSON.stringify({notice:c.notice(), office:c.loadOffice(), "
          "none:c.loadOffice(%r)}))") % (os.path.join(GEN_DIR, "cta.js"), str(tmp_path / "none.json"))
    office = tmp_path / "office.json"
    office.write_text(json.dumps({"name": "가나다", "title": "변호사", "phone": "02-000-0000"}, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, LAWFIRM_OFFICE_FILE=str(office))
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, env=env, check=True).stdout)
    assert out["notice"] == NOTICE and out["office"]["name"] == "가나다" and out["none"] is None


@pytest.mark.skipif(not NODE, reason="node 없음")
def test_generate_js_has_no_contact_constants():
    src = open(os.path.join(GEN_DIR, "generate.js"), encoding="utf-8").read()
    assert "require('./cta')" in src or "require('./cta.js')" in src
    assert not _PHONE.search(src) and not _MAIL.search(src)


def _docx_path():
    if not NODE:
        return None
    root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
    env = dict(os.environ, NODE_PATH=os.pathsep.join(x for x in (os.environ.get("NODE_PATH"), root) if x))
    ok = subprocess.run([NODE, "-e", "require('docx')"], capture_output=True, env=env, cwd=GEN_DIR).returncode == 0
    return env if ok else None


@pytest.mark.skipif(_docx_path() is None, reason="node 또는 docx 없음 — docs/QUALITY.md 판 올림 절차 2번으로 개발 PC 에 설치")
@pytest.mark.parametrize("with_office", [False, True])
def test_generate_js_runs(tmp_path, with_office):
    env = _docx_path()
    data = tmp_path / "합의서_데이터.json"
    data.write_text(json.dumps({"피해자": {"name": "김가명"}, "가해자": {"name": "이가명"}}, ensure_ascii=False), encoding="utf-8")
    if with_office:
        office = tmp_path / "office.json"
        office.write_text(json.dumps({"name": "가나다", "title": "변호사"}, ensure_ascii=False), encoding="utf-8")
        env["LAWFIRM_OFFICE_FILE"] = str(office)
    else:
        env["LAWFIRM_OFFICE_FILE"] = str(tmp_path / "없음.json")
    out = tmp_path / "합의서.docx"
    p = subprocess.run([NODE, os.path.join(GEN_DIR, "generate.js"), "--data", str(data), "--output", str(out)],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    import zipfile
    xml = zipfile.ZipFile(str(out)).read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml)
    assert "AI가 작성한 초안" in text and "최종 검토와 제출 판단은 사용 변호사의 책임" in text
    assert ("[상담 안내]" in text) is with_office and ("가나다" in text) is with_office


# ── FR-12 Node·docx 확인 1줄 ──
CHECK = "node -e \"require('docx')\""


@pytest.mark.parametrize("skill", ["complaint-drafter", "certified-letter", "fact-confirmation", "criminal-settlement"])
def test_node_docx_check_line(skill):
    t = read("skills/%s/SKILL.md" % skill)
    assert CHECK in t and "npm install --prefix ~ docx" in t
    assert "npm install -g docx" not in t
    if skill == "criminal-settlement":
        assert "scripts/" in t.split(CHECK)[0][-200:] or "generate.js 가 있는" in t


@pytest.mark.skipif(not NODE, reason="node 없음")
def test_check_command_fails_without_docx(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "NODE_PATH"}
    assert subprocess.run([NODE, "-e", "require('docx')"], cwd=str(tmp_path), env=env, capture_output=True).returncode != 0


def test_check_command_fails_without_node(tmp_path):
    p = subprocess.run(["/bin/sh", "-c", CHECK], cwd=str(tmp_path), env={"PATH": str(tmp_path)}, capture_output=True)
    assert p.returncode != 0


# ── FR-15 README 고지 · FR-16 키 보관 ──
def test_readme_notices():
    t = read("README.md")
    assert "변호사 업무 보조용" in t and "결론은 변호사가 정합니다" in t  # ①
    assert "모델 제공자에게 전송" in t  # ②
    assert "state.py purge" in t and "작업 폴더" in t  # ③


def test_architecture_no_unqualified_local_only_claim():
    t = read("ARCHITECTURE.md")
    assert "작업 폴더와 사건 폴더에만 남는다" not in t or "모델 제공자" in t.split("작업 폴더와 사건 폴더에만 남는다")[1][:200]


KEY_STORE = "키는 작업 폴더의 config.json 에 저장합니다(macOS `~/.intent-brief/config.json` 은 이 PC 사용자만 읽게 권한 0600"


def test_key_storage_sentence_same_in_readme_and_command():
    assert KEY_STORE in read("README.md") and KEY_STORE in read("commands/law-key-setup.md")
    for rel in ("README.md", "commands/law-key-setup.md"):
        for line in read(rel).splitlines():
            if "0600" in line or "본인만 읽기" in line:
                assert "macOS" in line, (rel, line)
