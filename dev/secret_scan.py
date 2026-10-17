"""개발 전용 비밀·개인정보 형식 검사 — 공개 repo 의 녹화·픽스처·답 파일에 실값이 섞이지 않게.

값은 출력하지 않는다 — (경로, 패턴 이름)만 낸다. 인명은 패턴으로 못 잡는다(가명 규칙이 맡는다).
하이픈 없는 숫자열은 잡지 않는다 — 법제처 녹화의 법령 ID 숫자열이 휴대전화 자리 수와 같다.

사용: python3 dev/secret_scan.py [경로 …]     (기본: tests/recorded·tests/fixtures·tests/e2e·빅케이스 로컬 녹화)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIGCASE_LOCAL = os.path.join("tests", "case_search", "recorded_local")  # 빅케이스 실녹화(git 무시 · 이 PC 에만)

_MASK = r"(?!\*\*\*)"
PATTERNS = [
    ("oc", re.compile(r"OC=" + _MASK + r"[^&\s\"'<>]+")),
    ("authorization", None),  # 스킴(Bearer·Token·Basic …)은 있든 없든 — 아래 _authorization
    ("access_token", re.compile(r"accessToken[\"']?\s*[:=]\s*[\"']" + _MASK + r"[^\"'\s]+")),
    ("refresh_token", re.compile(r"refreshToken[\"']?\s*[:=]\s*[\"']" + _MASK + r"[^\"'\s]+")),
    ("cookie", re.compile(r"(?i)(?:set-)?cookie[\"']?\s*[:=]\s*[\"']?" + _MASK + r"[^\s\"';=]+=[^\s\"';]+")),
    ("mobile", re.compile(r"(?<!\d)01[016789]-\d{3,4}-\d{4}(?!\d)")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]


def default_targets(root=ROOT):
    return [os.path.join(root, "tests", d) for d in ("recorded", "fixtures", "e2e")] + [os.path.join(root, BIGCASE_LOCAL)]


def _files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        for d, subdirs, files in os.walk(p):
            subdirs[:] = [s for s in subdirs if s != "__pycache__"]
            for f in files:
                yield os.path.join(d, f)


_AUTH = re.compile(r"(?i)authorization[\"']?\s*[:=]\s*[\"']?([^\"'\n]*)")


def _authorization(text):
    for m in _AUTH.finditer(text):
        parts = m.group(1).split()
        if parts and parts[-1] != "***" and len(parts[-1]) >= 4:
            return True
    return False


def scan_text(text):
    return [name for name, rx in PATTERNS if (rx.search(text) if rx else _authorization(text))]


def scan(paths):
    hits = []
    for f in sorted(set(_files(paths))):
        try:
            text = open(f, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue  # 바이너리(docx 등)는 텍스트 패턴 대상이 아니다
        hits += [(os.path.relpath(f, ROOT) if f.startswith(ROOT) else f, name) for name in scan_text(text)]
    return hits


def main(argv=None):
    hits = scan((argv if argv is not None else sys.argv[1:]) or default_targets())
    for path, name in hits:
        print("위반: %s — %s" % (path, name))
    print("secret_scan: 위반 %d" % len(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
