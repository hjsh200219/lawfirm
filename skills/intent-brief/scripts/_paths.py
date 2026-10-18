"""intent-brief 공용 — 경로·작업 폴더·원자 저장·금액 표기.

런타임 스크립트는 Python 3.9+ 표준 라이브러리만 쓴다(받는 변호사 PC 에 설치를 요구하지 않기 위해).
작업 폴더(상태·design.json·draft.md·인용 응답·사건메모 사본)는 사건 폴더 밖 OS 기본 경로에 둔다.
- 사건 폴더 안 숨김 폴더는 하네스 scan_cases.list_case_dirs 가 사건 후보로 잡는다.
- CLAUDE_PLUGIN_DATA 는 `claude plugin uninstall` 이 지우므로 쓰지 않는다.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
REFS_DIR = os.path.join(SKILL_DIR, "references")
PLUGIN_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
MEMO_NAME = "사건메모.md"


class BriefError(Exception):
    """사용자에게 그대로 보여 줄 오류."""


def nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_params():
    return load_json(os.path.join(REFS_DIR, "intent-params.json"))


def load_phrases():
    return load_json(os.path.join(REFS_DIR, "phrases.json"))


def load_response_keys():
    """법제처·빅케이스 응답 키 목록 — 받는 PC 형식 검사와 개발 PC 계약 점검이 같은 파일을 읽는다."""
    return load_json(os.path.join(REFS_DIR, "response-keys.json"))


# 응답 형식이 바뀌었을 때 설명 끝에 붙이는 안내 — 유지보수자에게 닿는 길은 이 신고뿐이다(통계는 PC 밖으로 나가지 않는다)
FORMAT_GUIDE = "플러그인을 최신 판으로 업데이트하고, 계속되면 repo 이슈로 알려 주십시오(사건 내용·의뢰인 정보는 적지 마십시오)"


def nows(s):
    """번호·이름 비교용 — 공백을 모두 지운다(사건번호 「2016다 225353」·법령명 띄어쓰기)."""
    return re.sub(r"\s+", "", s or "")


def today():
    """오늘 날짜. INTENT_BRIEF_TODAY 는 개발·테스트 전용(픽스처 기일이 지난 날짜라 고정이 필요)."""
    v = os.environ.get("INTENT_BRIEF_TODAY")
    if v:
        return datetime.date.fromisoformat(v)
    return datetime.date.today()


def work_root():
    """작업 폴더 루트 — macOS·Linux ~/.intent-brief, Windows %LOCALAPPDATA%\\intent-brief."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "intent-brief")
    return os.path.join(os.path.expanduser("~"), ".intent-brief")


_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')


def case_key(case_dir):
    """사건 폴더명(파일명 안전 문자) + NFC 정규화 절대경로 sha256 앞 8자.
    macOS 는 한글 경로를 NFD 로 돌려줄 때가 있어 정규화하지 않으면 같은 사건이 다른 키가 된다."""
    absdir = nfc(os.path.abspath(case_dir))
    if os.name == "nt":
        absdir = absdir.lower()
    name = _UNSAFE.sub("_", nfc(os.path.basename(absdir.rstrip("\\/")))).strip("_")[:40] or "case"
    return "%s-%s" % (name, hashlib.sha256(absdir.encode("utf-8")).hexdigest()[:8])


def case_work_dir(case_dir, create=True):
    d = os.path.join(work_root(), "cases", case_key(case_dir))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def find_memo(case_dir):
    """사건 폴더의 사건메모.md(NFC·NFD 이름 모두)."""
    try:
        names = os.listdir(case_dir)
    except OSError:
        return None
    for n in names:
        if nfc(n) == MEMO_NAME:
            return os.path.join(case_dir, n)
    return None


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(path, data):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def atomic_write_text(path, text):
    """줄바꿈을 바꾸지 않고(newline='') UTF-8 로 원자 저장."""
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def fmt_won(n):
    """정수 원 → 「1,000만원」「1억 2,000만원」「12,345,678원」."""
    if n is None:
        return None
    n = int(n)
    if n != 0 and n % 10000 == 0:
        man = n // 10000
        if man >= 10000:
            eok, rem = divmod(man, 10000)
            return "%s억 %s만원" % ("{:,}".format(eok), "{:,}".format(rem)) if rem else "%s억원" % "{:,}".format(eok)
        return "{:,}만원".format(man)
    return "{:,}원".format(n)


_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원")


def parse_won(text):
    """「5,000만원」「1억 2,000만원」「12,345,678원」 → 정수. 첫 금액만, 없으면 None."""
    if not text:
        return None
    t = nfc(text)
    m = re.search(r"(\d[\d,]*)\s*억(?:\s*(\d[\d,]*)\s*만)?\s*원", t)
    if m:
        eok = int(m.group(1).replace(",", ""))
        man = int(m.group(2).replace(",", "")) if m.group(2) else 0
        return eok * 100000000 + man * 10000
    m = _AMOUNT.search(t)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = {"억": 100000000, "천만": 10000000, "백만": 1000000, "만": 10000}.get(m.group(2), 1)
    return int(round(num * unit))


def intent_signature(intent):
    """의도 유불리 검토가 어떤 선택에 대한 것인지 — 주 의도|부 의도(순서 유지)."""
    return "%s|%s" % (intent.get("primary") or "", ",".join(intent.get("secondaries") or []))


def review_current(st):
    """지금 의도에 대해 유불리 검토를 마치고 변호사가 「진행」을 골랐는가."""
    r = st.get("intent_review") or {}
    return r.get("decision") == "진행" and r.get("for") == intent_signature(st["intent"])


def emit(obj, code=0):
    """결과 JSON 을 UTF-8 바이트로 표준출력에 — Windows 콘솔 코드페이지(cp949)에서 인코딩 오류가 나지 않게
    텍스트 계층을 거치지 않는다."""
    data = (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    sys.stdout.flush()
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return code


SANDBOX_WRITE_GUIDE = ("Codex 샌드박스가 작업 폴더(macOS ~/.intent-brief, Windows %LOCALAPPDATA%\\intent-brief) 쓰기를 막았습니다. "
                       "권한 상승으로 같은 명령을 다시 실행하거나, config.toml 의 [sandbox_workspace_write] writable_roots 에 그 폴더를 넣으십시오.")


def _excepthook(kind, exc, tb):
    """Codex 샌드박스의 쓰기 거부는 트레이스백 대신 사람이 알아볼 JSON 으로 — 그 밖의 예외는 원래대로."""
    if issubclass(kind, PermissionError) and os.environ.get("CODEX_SANDBOX"):
        emit({"ok": False, "error": "sandbox_write_blocked", "path": getattr(exc, "filename", None), "guide": SANDBOX_WRITE_GUIDE})
        return  # 종료 코드는 파이썬이 정한다(처리 안 된 예외 = 1)
    sys.__excepthook__(kind, exc, tb)


sys.excepthook = _excepthook


def fail(msg, code=2, **extra):
    obj = {"ok": False, "error": msg}
    obj.update(extra)
    emit(obj)
    return code
