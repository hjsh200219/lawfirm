#!/usr/bin/env python3
"""기한·기일 D-day 점검 — 표준 라이브러리만, Python 3.9.

사건 출처: ① 등록한 사건 루트 폴더의 바로 아래 폴더(사건메모.md 가 있는 것) ② intent-brief 작업 폴더의 상태 파일(case_dir).
각 사건메모 「주요 일정」 절의 날짜 줄을 모아 오늘부터 N일(기본 14일) 안의 것을 알린다. 지운 부분(~~…~~)은 읽지 않고(「~~옛 날짜~~ 새 날짜」는 새 날짜),
완료 표시 줄은 뺀다. scan 은 등록한 사건을 모두 본다. 훅만 세션 시작을 늦추지 않도록 사건 수·시간 상한을 두고, 상한에 걸리면 그렇다고 알린다.
항소·상고·항고·이의·추후보완·재심·제소·시효·제척·불변 이 들어간 줄은 불변기간·시효로 강조한다.

  scan [--days N]            JSON
  hook                       세션 시작 훅용(Claude Code·Codex 공통 JSON). 환경마다 처음 한 번 첫 사용 고지를 사용자 화면(systemMessage)과
                             모델 문맥(additionalContext)에 내고 작업 폴더 notice.json 에 기록한다(문구 판이 바뀌면 다시).
                             다가오는 기한은 additionalContext. 둘 다 없으면 아무것도 출력하지 않는다. 어떤 오류에도 exit 0.
                             INTENT_BRIEF_NO_NOTICE=1 이면 고지 출력·기록을 하지 않는다(개발 재생 구동기)
  roots add|remove <폴더> · roots list
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "intent-brief", "scripts"))
import _paths as P  # noqa: E402
import memo as M  # noqa: E402
from deadline import IMMINENT_DAYS, WEEKDAYS  # noqa: E402

DATE = re.compile(r"(20\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
CRITICAL = re.compile(r"항소|상고|항고|이의|추후보완|재심|제소|소\s*제기|시효|제척|불변")
# 완료 「표시」만 — 「미완료」·「완료 예정」 줄을 빼면 있는 기한을 숨기게 된다
DONE = re.compile(r"\[[xX]\]|[(\[]\s*완료\s*[)\]]|(?<![미불])완료\s*$")
STRUCK = re.compile(r"~~.*?~~")
HOOK_MAX_DIRS = 500
HOOK_TIME_BUDGET = 4.0  # 훅 timeout(10초) 안에 끝내도록
MAX_LINES = 10


def config_path():
    return os.path.join(P.work_root(), "dday.json")


# ── 첫 사용 고지(README 첫머리 고지의 요약) ──
NOTICE_VERSION = "2026-10-18"  # 문구 판 — 문구를 바꾸면 올린다(환경마다 다시 고지)


def notice_text():
    return ("[lawfirm] 변호사 업무 보조용 플러그인입니다 — 초안·검토 결과는 참고 자료이고 결론은 변호사가 정합니다. "
            "사건 자료(파일·대화)는 쓰는 AI 도구의 모델 제공자에게 전송·처리됩니다. "
            "작업 폴더(macOS ~/.intent-brief, Windows %LOCALAPPDATA%\\intent-brief)에 남는 사건 자료는 state.py purge 로 지웁니다"
            "(README 「데이터 위치」). 이 안내는 이 환경에서 한 번만 보입니다.")


def _env_name():
    """Codex 는 플러그인 훅에 PLUGIN_ROOT·PLUGIN_DATA 를 준다(Claude Code 는 CLAUDE_PLUGIN_ROOT 만)."""
    return "codex" if (os.environ.get("PLUGIN_ROOT") or os.environ.get("PLUGIN_DATA")) else "claude"


def _notice_path():
    return os.path.join(P.work_root(), "notice.json")


def _read_notice_record():
    try:
        return P.load_json(_notice_path())
    except (OSError, ValueError):
        return {}


def _write_notice_record(rec):
    P.atomic_write_json(_notice_path(), rec)


def notice_due():
    if os.environ.get("INTENT_BRIEF_NO_NOTICE") == "1":
        return False
    return (_read_notice_record().get(_env_name()) or {}).get("version") != NOTICE_VERSION


def _load():
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return {"roots": [r for r in data.get("roots", []) if isinstance(r, str)]}
    except (OSError, ValueError):
        return {"roots": []}


def _save(cfg):
    os.makedirs(P.work_root(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def roots_add(folder):
    path = P.nfc(os.path.abspath(folder))
    if not os.path.isdir(path):
        raise ValueError("폴더가 없습니다: %s" % folder)
    cfg = _load()
    if path not in cfg["roots"]:
        cfg["roots"].append(path)
        _save(cfg)
    return {"ok": True, "roots": cfg["roots"]}


def roots_remove(folder):
    path = P.nfc(os.path.abspath(folder))
    cfg = _load()
    cfg["roots"] = [r for r in cfg["roots"] if r != path]
    _save(cfg)
    return {"ok": True, "roots": cfg["roots"]}


def roots_list():
    return {"ok": True, "roots": _load()["roots"]}


def case_dirs(max_dirs=None, budget=None):
    """(사건 폴더 목록, 상한에 걸려 다 못 봤는지). 상한은 훅만 준다."""
    seen, out, started, cut = set(), [], time.time(), False

    def over():
        return budget is not None and time.time() - started > budget

    def add(d):
        key = P.nfc(os.path.abspath(d))
        if key not in seen and P.find_memo(key):
            seen.add(key)
            out.append(key)

    for root in _load()["roots"]:
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        add(root)
        if max_dirs is not None and len(names) > max_dirs:
            names, cut = names[:max_dirs], True
        for n in names:
            if over():
                return out, True
            full = os.path.join(root, n)
            if os.path.isdir(full):
                add(full)
    for st in glob.glob(os.path.join(P.work_root(), "cases", "*", "*_state.json")):
        if over():
            return out, True
        try:
            with open(st, encoding="utf-8") as f:
                d = json.load(f).get("case_dir")
        except (OSError, ValueError):
            continue
        if isinstance(d, str) and os.path.isdir(d):
            add(d)
    return out, cut


def _kind(text):
    if re.search(r"기한|제출|마감", text):
        return "기한"
    if "기일" in text:
        return "기일"
    return "기타"


def schedule_items(case_dir, today):
    path = P.find_memo(case_dir)
    if not path:
        return []
    md = P.read_text(path)
    items = []
    for ln in M.section_text(md, M.SCHEDULE_TITLES).splitlines():
        ln = STRUCK.sub("", ln)  # 취소선 부분만 뺀다 — 줄 전체가 지워졌으면 날짜가 남지 않는다
        ms = list(DATE.finditer(ln))
        if not ms or DONE.search(ln):
            continue
        m = ms[0]
        if len(ms) > 1 and re.search(r"[~∼〜]|부터", ln[ms[0].end():ms[1].start()]):
            m = ms[1]  # 「시작~끝」 기간 줄은 끝 날짜가 기한이다(괄호 안 송달일 같은 참고 날짜는 무시)
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        text = (ln[:ms[0].start()] + ln[m.end():]).strip(" -*\t~∼〜")
        text = re.sub(r"^\d{1,2}:\d{2}\s*", "", text).strip()
        items.append({"case": os.path.basename(case_dir.rstrip("\\/")), "case_dir": case_dir, "date": d.isoformat(),
                      "d_day": (d - today).days, "text": text, "kind": _kind(text), "critical": bool(CRITICAL.search(text))})
    return items


def scan(days=IMMINENT_DAYS, today=None, hook=False):
    today = today or P.today()
    budget = HOOK_TIME_BUDGET if hook else None
    started = time.time()
    dirs, incomplete = case_dirs(HOOK_MAX_DIRS if hook else None, budget)
    items = []
    for d in dirs:
        if budget is not None and time.time() - started > budget:
            incomplete = True
            break
        items += [i for i in schedule_items(d, today) if 0 <= i["d_day"] <= days]
    items.sort(key=lambda i: (i["date"], not i["critical"], i["case"]))
    return {"ok": True, "today": today.isoformat(), "days": days, "items": items, "incomplete": incomplete}


def hook_text(result):
    items, lines = result["items"], []
    if result.get("incomplete"):
        lines.append("[lawfirm] 사건이 많아 세션 시작 점검에서 다 보지 못했습니다 — 전체는 `python3 \"%s\" scan` 으로 확인하십시오"
                     % os.path.abspath(__file__))
    if not items:
        return "\n".join(lines) + "\n" if lines else ""
    lines.append("[lawfirm] %d일 안에 다가오는 기한·기일 %d건 — 사건메모 「주요 일정」 기준" % (result["days"], len(items)))
    for i in items[:MAX_LINES]:
        d = date.fromisoformat(i["date"])
        tag = " [불변기간·시효 — 날짜 재확인]" if i["critical"] else ""
        dd = "D-day" if i["d_day"] == 0 else "D-%d" % i["d_day"]
        lines.append("- %s %s(%s) %s: %s%s" % (dd, i["date"], WEEKDAYS[d.weekday()], i["case"], i["text"], tag))
    if len(items) > MAX_LINES:
        lines.append("- … 외 %d건" % (len(items) - MAX_LINES))
    return "\n".join(lines) + "\n"


def _hook():
    """기한 알림(additionalContext) + 첫 사용 고지(systemMessage). 세션 시작을 막지 않는다 — 어떤 오류에도 exit 0."""
    out, notice, ctx = {}, None, []
    try:
        if notice_due():
            notice = notice_text()
    except Exception:  # noqa: BLE001 — 고지 실패가 기한 알림을 막지 않게
        notice = None
    try:
        text = hook_text(scan(hook=True))
    except Exception as e:  # noqa: BLE001 — 「기한 없음」과 구별되게 점검 실패를 알린다
        text = ("[lawfirm] 기한·기일을 점검하지 못했습니다(%s) — `python3 \"%s\" scan` 으로 직접 확인하십시오\n"
                % (type(e).__name__, os.path.abspath(__file__)))
    if notice:
        writable = _can_record()
        out["systemMessage"] = notice if writable else notice + " (작업 폴더에 이 고지를 기록하지 못했습니다 — 다음 세션에 다시 보입니다)"
        ctx.append(notice)
    if text:
        ctx.append(text)
    if not ctx:
        return 0
    out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": "\n".join(c.rstrip("\n") for c in ctx) + "\n"}
    # Claude Code·Codex 가 다 받는 형식(Codex 는 일반 텍스트를 실패로 버린다). ASCII(\\uXXXX) — Windows PowerShell 5.1 코드 페이지
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
    if notice and out["systemMessage"] == notice:  # 출력한 뒤에만 그 환경 키에 기록한다
        try:
            rec = _read_notice_record()
            rec[_env_name()] = {"version": NOTICE_VERSION, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            _write_notice_record(rec)
        except Exception:  # noqa: BLE001 — 기록 실패는 다음 세션에 다시 고지
            pass
    return 0


def _can_record():
    """고지 기록을 쓸 수 있는지 먼저 본다(Codex 샌드박스 쓰기 거부면 거부 안내를 붙이고 기록하지 않는다)."""
    try:
        _write_notice_record(_read_notice_record())
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="기한·기일 D-day 점검")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("--days", type=int, default=IMMINENT_DAYS)
    sub.add_parser("hook")
    r = sub.add_parser("roots")
    r.add_argument("action", choices=("add", "remove", "list"))
    r.add_argument("folder", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "hook":
        return _hook()
    try:
        if a.cmd == "scan":
            out = scan(days=a.days)
        elif a.action == "list":
            out = roots_list()
        else:
            if not a.folder:
                raise ValueError("폴더를 주십시오")
            out = roots_add(a.folder) if a.action == "add" else roots_remove(a.folder)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
