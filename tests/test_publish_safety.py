"""공개 repo 게시 안전 — 실행 자료 git 무시(FR-02) · 녹화·픽스처 비밀 검사(FR-03) · 외부 주소 차단 픽스처(NFR-05) ·
런타임 송신 호스트 허용 목록(NFR-10)."""
import glob
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import secret_scan as S  # noqa: E402


# ── FR-02 meta-plan 실행 자료는 git 추적에서 빠진다 ──
@pytest.mark.parametrize("rel", ["docs/prd/.doctor.json", "docs/prd/x/prd.md", "docs/prd/x/.gitignore", "docs/prd/x/e2e/judge.json"])
def test_meta_plan_run_files_are_ignored(rel):
    assert subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", rel]).returncode == 0


def test_no_tracked_files_under_docs_prd():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "docs/prd"], capture_output=True, text=True).stdout
    assert out.strip() == ""


# ── FR-03 녹화·픽스처·답 파일 비밀·개인정보 형식 검사 ──
def test_recordings_and_fixtures_have_no_secret_patterns():
    t0 = time.time()
    hits = S.scan(S.default_targets(ROOT))
    assert hits == [], "\n".join("%s: %s" % h for h in hits)  # (경로, 패턴 이름)만 — 값은 담지 않는다
    assert time.time() - t0 < 1.0


FAKE = {
    "oc": "https://www.law.go.kr/DRF/lawSearch.do?OC=realkey1&target=law",
    "authorization": '{"Authorization": "Bearer abcdef123456"}',
    "access_token": '{"accessToken": "eyJhbGciOi.payload"}',
    "refresh_token": '{"refreshToken": "r1a2b3c4d5"}',
    "cookie": "Set-Cookie: sid=abc123def; Path=/",
    "mobile": "연락처 010-1234-5678",
    "email": "보낸 사람 someone@lawoffice.kr",
}


@pytest.mark.parametrize("name", sorted(FAKE))
def test_each_pattern_catches_its_fake(tmp_path, name):
    (tmp_path / "x.json").write_text(FAKE[name], encoding="utf-8")
    hits = S.scan([str(tmp_path)])
    assert [n for _, n in hits] == [name]
    assert all("abc" not in "%s %s" % h and "1234" not in "%s %s" % h for h in hits)  # 값은 출력하지 않는다


@pytest.mark.parametrize("text", [
    "OC=***&target=law",  # 가린 키
    '{"Authorization": "Bearer ***"}',
    '{"accessToken": ""}', '{"refreshToken": "***"}',
    "법령ID 00170012345 · 01012345678",  # 하이픈 없는 숫자열은 잡지 않는다(법령 ID 오탐)
    "예시 user@example.com",
])
def test_masked_or_benign_values_pass(tmp_path, text):
    (tmp_path / "x.md").write_text(text, encoding="utf-8")
    assert S.scan([str(tmp_path)]) == []


# ── NFR-05 기본 검사는 외부 주소로 나가지 않는다(conftest 의 차단 픽스처) ──
def test_external_connect_is_blocked():
    with pytest.raises(OSError, match="외부 주소"):
        socket.getaddrinfo("www.law.go.kr", 443)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="외부 주소"):
            s.connect(("203.0.113.5", 443))
    finally:
        s.close()
    with pytest.raises(OSError):
        urllib.request.urlopen("https://www.law.go.kr/", timeout=2)


def test_loopback_is_allowed():
    socket.getaddrinfo("127.0.0.1", 80)
    socket.getaddrinfo("localhost", 80)


# ── NFR-10 런타임 소스의 https 호스트 리터럴 허용 목록 ──
# 범위: skills/*/scripts/*.py · hooks/. 실제 송신 범위(모델 제공자 · site-api discover.py 가 받는 사용자 지정 URL)는
# 리터럴이 아니라 이 목록이 대표하지 않는다. 목록 밖 호스트가 생기면 README 의 전송 고지(FR-15 ②)를 다시 본다.
HOSTS = {"www.law.go.kr", "open.law.go.kr", "www.courtlistener.com", "bigcase.ai", "de.openlegaldata.io", "github.com"}
_HOST = re.compile(r"https://([a-zA-Z0-9.-]+)")


def runtime_hosts(root):
    found = set()
    files = glob.glob(os.path.join(root, "skills", "*", "scripts", "*.py")) + glob.glob(os.path.join(root, "hooks", "**", "*"), recursive=True)
    for f in files:
        if os.path.isfile(f):
            found |= set(_HOST.findall(open(f, encoding="utf-8", errors="ignore").read()))
    return found


def test_runtime_https_hosts_are_allowlisted():
    assert runtime_hosts(ROOT) == HOSTS


def test_new_host_fails_allowlist(tmp_path):
    d = tmp_path / "skills" / "x" / "scripts"
    d.mkdir(parents=True)
    (d / "y.py").write_text('URL = "https://new-sink.example.net/api"', encoding="utf-8")
    assert runtime_hosts(str(tmp_path)) - HOSTS == {"new-sink.example.net"}
