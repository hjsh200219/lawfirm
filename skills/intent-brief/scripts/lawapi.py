"""법제처 Open API(DRF) 직접 호출 — 법령·조문·판례·법령용어. 키(OC)는 변호사에게 받아 작업 폴더에 저장한다.

MCP 를 거치지 않는다. 표준 라이브러리만 쓴다.
키 찾는 순서: 환경변수 INTENT_BRIEF_LAW_OC → LAW_API_OC → 작업 폴더 config.json 의 law_oc.
키 값은 어떤 출력에도 쓰지 않는다(URL 이 오류에 섞이면 OC=*** 로 가린다).

사용:
  lawapi.py key status                       키 등록 여부·출처(값은 출력하지 않음)
  lawapi.py key set (<OC> | --stdin) [--no-check]   키 저장(기본: 키 오류 검사를 통과해야 저장 — 판례 1건 조회)
  lawapi.py key clear
  lawapi.py law <법령명> [--article 288 | 266-2]
  lawapi.py prec-search <검색어> [--nb | --fulltext] [--court 대법원] [--display 20] [--page 1]
  lawapi.py prec <판례일련번호>
  lawapi.py term <법령용어>
  lawapi.py search <target> <검색어> [--display 20] [--page 1] [--fulltext]   expc(법령해석례)·detc(헌재결정) 등
  lawapi.py form-search <검색어> [--admin] [--kind 별표|서식] [--law]   법령(--admin 이면 행정규칙) 별표·서식 목록
  lawapi.py form-get <파일번호> --out <폴더>                             서식 파일(hwp·pdf) 내려받기 — 키 불필요
  lawapi.py detail <target> <ID>
"""
import argparse
import getpass
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

BASE_URL = "https://www.law.go.kr/DRF"
TIMEOUT = 20.0
MIN_INTERVAL = 1.0  # 요청 간 최소 간격(초) — 짧으면 빈 응답(요청 제한)이 온다
RETRIES = 2
KEY_GUIDE = ("법제처 Open API 키(OC)가 필요합니다. https://open.law.go.kr 에서 회원가입 → OPEN API 사용 신청"
             "(법령·판례) 후 받은 OC 값을 `/lawfirm:law-key-setup` 의 입력 창에 넣으면 저장합니다(채팅에 적지 않습니다). "
             "신청 때 이 PC 의 IP 주소 등록을 요구할 수 있습니다.")


DIALOG_FAIL = "입력 창을 띄우지 못했습니다(%s) — Codex 샌드박스라면 권한 상승으로 다시 실행하거나, 자기 터미널에서 같은 명령을 직접 실행하십시오"


def _osascript_dialog(message, title, hidden):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = ('display dialog "%s" default answer "" %swith title "%s" '
              'buttons {"취소", "확인"} default button "확인" cancel button "취소"\n'
              "text returned of result") % (esc(message), "with hidden answer " if hidden else "", esc(title))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600, check=False)
    if r.returncode != 0:
        if "-128" in (r.stderr or ""):  # 사람이 「취소」를 누름
            raise P.BriefError("입력을 취소했습니다")
        raise P.BriefError(DIALOG_FAIL % ((r.stderr or "").strip()[:120] or "osascript 종료 %d" % r.returncode))
    return r.stdout.rstrip("\n")


def _windows_dialog(message, title, hidden):
    msg, ttl = message.replace("'", "''"), title.replace("'", "''")
    if hidden:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "$c=Get-Credential -UserName '%s' -Message '%s';"
              "if(-not $c){exit 3};[Console]::Out.Write($c.GetNetworkCredential().Password)") % (ttl, msg)
    else:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName Microsoft.VisualBasic;"
              "$v=[Microsoft.VisualBasic.Interaction]::InputBox('%s','%s');"
              "if(-not $v){exit 3};[Console]::Out.Write($v)") % (msg, ttl)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=600, check=False)
    if r.returncode == 3:  # 우리 스크립트의 취소 코드 — 다른 실패(창을 못 띄움)와 구별한다
        raise P.BriefError("입력을 취소했습니다")
    if r.returncode != 0:
        raise P.BriefError(DIALOG_FAIL % ((r.stderr or b"").decode("utf-8", "replace").strip()[:120] or "PowerShell 종료 %d" % r.returncode))
    return r.stdout.decode("utf-8", "replace")


def _ask(message, title, hidden):
    """사람에게 값을 받는다 — 터미널이면 프롬프트, 아니면 OS 입력 창(macOS·Windows). 채팅·명령행 인자는 쓰지 않는다."""
    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass(message + ": ") if hidden else input(message + ": ")
    if sys.platform == "darwin":
        return _osascript_dialog(message, title, hidden)
    if os.name == "nt":
        return _windows_dialog(message, title, hidden)
    raise P.BriefError("입력 창을 띄울 수 없습니다 — 자기 터미널에서 같은 명령을 직접 실행하십시오")


def ask(message, title):
    """법제처 키(OC)는 비밀번호가 아니라 가입 아이디라 보이게 받는다."""
    return _ask(message, title, hidden=False)


class NoKey(Exception):
    """키가 없다 — 변호사에게 받아야 한다."""


class KeyInvalid(Exception):
    """법제처가 사용자 검증 실패를 돌려줬다(키 오류 또는 IP·도메인 미등록)."""


class Unavailable(Exception):
    """연결 실패·타임아웃·5xx·빈 응답."""


class NetworkBlocked(Unavailable):
    """Codex 샌드박스가 네트워크를 막았다 — 법제처 장애가 아니다(막히면 DNS 실패로 보여 장애와 구별되지 않는다)."""


NETWORK_BLOCKED = ("Codex 샌드박스가 네트워크를 막았습니다(법제처 장애가 아닙니다). 네트워크 허용(권한 상승)으로 같은 명령을 다시 "
                   "실행하거나, config.toml 의 [sandbox_workspace_write] network_access = true 로 켜 두십시오.")


def sandbox_network_blocked():
    return os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1"


class FormatChanged(Exception):
    """응답 형식이 바뀌었다 — 「미확인」으로 넘기지 않고 드러낸다."""


class NotJson(FormatChanged):
    """JSON 이 아닌 응답(점검 화면 HTML 등) — 사용자 검증 전이라 키가 맞는지 모른다."""


# ── 키 ────────────────────────────────────────────────────────
def config_path():
    return os.path.join(P.work_root(), "config.json")


def _load_config():
    p = config_path()
    return P.load_json(p) if os.path.exists(p) else {}


def find_key():
    """(키, 출처) — 없으면 (None, None)."""
    for env in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v, "env:%s" % env
    v = (_load_config().get("law_oc") or "").strip()
    return (v, "config") if v else (None, None)


def save_key(oc):
    oc = (oc or "").strip()
    if not oc or re.search(r"\s", oc):
        raise P.BriefError("키(OC) 형식이 올바르지 않습니다")
    cfg = _load_config()
    cfg["law_oc"] = oc
    path = config_path()
    P.atomic_write_json(path, cfg)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def clear_key():
    cfg = _load_config()
    had = cfg.pop("law_oc", None) is not None
    if had:
        P.atomic_write_json(config_path(), cfg)
    return had


# ── HTTP ──────────────────────────────────────────────────────
def base_url():
    return os.environ.get("INTENT_BRIEF_LAW_URL") or BASE_URL  # 개발·테스트 전용(가짜 서버)


def _mask(s):
    return re.sub(r"OC=[^&\s\"']+", "OC=***", str(s))


class Client:
    def __init__(self, oc=None, timeout=TIMEOUT, interval=MIN_INTERVAL, backoff=1.5):
        if oc is None:
            oc, _ = find_key()
        if not oc:
            raise NoKey(KEY_GUIDE)
        self.oc = oc
        self.timeout = timeout
        self.interval = interval
        self.backoff = backoff
        self._last = 0.0
        self.calls = 0

    def get(self, path, **params):
        q = dict(params, OC=self.oc, type="JSON")
        url = "%s/%s?%s" % (base_url(), path, urllib.parse.urlencode(q))
        err = None
        for attempt in range(RETRIES + 1):
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8")
                self.calls += 1
            except UnicodeDecodeError:
                raise Unavailable("응답을 UTF-8 로 읽지 못했습니다")
            except urllib.error.HTTPError as e:
                err = Unavailable("HTTP %s" % e.code)
                if e.code >= 500 or e.code == 429:
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                raise err
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, socket.timeout, OSError) as e:
                if sandbox_network_blocked():
                    raise NetworkBlocked(NETWORK_BLOCKED)  # 다시 해도 같다 — 기다리지 않는다
                err = Unavailable("연결 실패 또는 타임아웃: %s" % _mask(e))
                time.sleep(self.backoff * (attempt + 1))
                continue
            if not body.strip():
                err = Unavailable("빈 응답(요청 제한일 수 있음)")
                time.sleep(self.backoff * (attempt + 1))
                continue
            try:
                obj = json.loads(body)
            except ValueError:
                raise NotJson("JSON 이 아닌 응답: %s" % _mask(body[:120]))
            if isinstance(obj, dict) and "사용자 정보 검증" in str(obj.get("result", "")):
                raise KeyInvalid("법제처 사용자 검증 실패 — 키(OC)가 틀렸거나 이 PC 의 IP·도메인이 등록되지 않았습니다")
            return obj
        raise err


def _list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


_KEYS = P.load_response_keys()["law"]


def check_search(root, kind, page=1, matched=True):
    """검색 응답 형식 검사(받는 PC — 추가 호출 0). kind 는 law·prec.

    ① 항목이 1개 이상인데 모든 항목이 필수 키 중 하나 이상을 갖추지 못함 ② 1쪽에서 총건수 1 이상인데 항목 0(목록 키 변경)
    ③ 일치 항목이 없어 총건수를 읽는 자리에서 총건수 키가 없음. 결과 0건(총건수 0·목록 키 없음)은 정상이다.
    """
    spec = _KEYS["law_search" if kind == "law" else "prec_search"]
    items = [it for it in _list(root.get(spec["list"])) if isinstance(it, dict)]
    if items and all(any(k not in it for k in spec["required"]) for it in items):
        raise FormatChanged("응답 형식 변경 — %s 항목에 필수 키(%s)가 없음" % (spec["container"], "·".join(spec["required"])))
    try:
        total = int(root.get(spec["count"]) or 0)
    except (TypeError, ValueError):
        total = 0
    if page == 1 and total >= 1 and not items:
        raise FormatChanged("응답 형식 변경 — %s 총건수 %d 인데 목록(%s)이 없음" % (spec["container"], total, spec["list"]))
    if not matched and spec["count"] not in root:
        raise FormatChanged("응답 형식 변경 — %s 에 %s 없음" % (spec["container"], spec["count"]))


# ── 법령·조문 ─────────────────────────────────────────────────
LAW_DISPLAY = 100
LAW_PAGES = 5


def search_law(client, name, strict=False):
    """법령명(또는 약칭) 정확 일치 → {law_id, name, mst, effective} 또는 None. strict 면 응답 형식을 검사한다(호출 지점이 켠다)."""
    # 짧은 이름(「상법」)은 결과가 많아 첫 쪽 밖에 있다(2026-10-15 실측 56건 중 34번째) — 쪽을 넘겨 본다(최대 LAW_PAGES 쪽)
    want = P.nows(name)
    for page in range(1, LAW_PAGES + 1):
        obj = client.get("lawSearch.do", target="law", query=name, display=LAW_DISPLAY, page=page)
        root = obj.get("LawSearch")
        if not isinstance(root, dict):
            raise FormatChanged("LawSearch 없음")
        if strict:
            check_search(root, "law", page)
        items = _list(root.get("law"))
        for it in items:
            if want in (P.nows(it.get("법령명한글")), P.nows(it.get("법령약칭명"))) and it.get("현행연혁코드", "현행") == "현행":
                return {"law_id": it.get("법령ID"), "name": it.get("법령명한글"), "mst": it.get("법령일련번호"),
                        "effective": it.get("시행일자")}
        if strict:
            check_search(root, "law", page, matched=False)
        try:
            total = int(root.get("totalCnt") or 0)
        except ValueError:
            total = 0
        if not items or page * LAW_DISPLAY >= total:
            break
    return None


def _txt(v):
    if isinstance(v, list):
        return " ".join(_txt(x) for x in v)
    return (v or "").strip() if isinstance(v, str) else ""


def _items(node):
    """호(1. 2. …)와 그 아래 목(가. 나. …)을 줄 단위로 — 응답은 항 → 호 → 목으로 중첩된다."""
    lines = []
    for ho in _list(node.get("호")) if isinstance(node, dict) else []:
        if not isinstance(ho, dict):
            continue
        if _txt(ho.get("호내용")):
            lines.append(_txt(ho.get("호내용")))
        for mok in _list(ho.get("목")):
            if isinstance(mok, dict) and _txt(mok.get("목내용")):
                lines.append(_txt(mok.get("목내용")))
    return "\n".join(lines)


def _para(h):
    if not isinstance(h, dict):
        return ""
    return "\n".join(x for x in (_txt(h.get("항내용")), _items(h)) if x)


def get_article(client, law_id, article, sub=0):
    """조문 본문 — 제목 줄(편·장)이 아니라 조문여부 「조문」인 항목. 없으면 None."""
    jo = "%04d%02d" % (int(article), int(sub))
    obj = client.get("lawService.do", target="law", ID=law_id, JO=jo)
    law = obj.get("법령")
    if not isinstance(law, dict):
        raise FormatChanged("법령 없음")
    units = _list((law.get("조문") or {}).get("조문단위"))
    head = "제%d조%s" % (int(article), "의%d" % int(sub) if sub else "")
    for u in units:
        text = (u.get("조문내용") or "").strip()
        if u.get("조문여부") == "조문" and re.match(re.escape(head) + r"\s*\(", text):
            paras = [p for p in (_para(h) for h in _list(u.get("항"))) if p]
            items = _items(u)  # 항 없이 조문 바로 아래 호가 오는 경우
            if items:
                paras.append(items)
            return {"head": head, "title": u.get("조문제목"), "text": text, "paragraphs": paras,
                    "full_text": "\n".join([text] + paras), "effective": u.get("조문시행일자")}
    if int(article) == 1 and not int(sub) and not units:
        return _single_provision(client, law_id)
    return None


def _single_provision(client, law_id):
    """조 번호 없이 한 문장뿐인 법령(예: 소송촉진법 법정이율 규정 — 조문번호 0, 조문여부 「전문」)은 그 본문을 제1조로 준다."""
    law = client.get("lawService.do", target="law", ID=law_id).get("법령")
    if not isinstance(law, dict):
        raise FormatChanged("법령 없음")
    units = [u for u in _list((law.get("조문") or {}).get("조문단위")) if isinstance(u, dict)]
    if len(units) == 1 and units[0].get("조문여부") == "전문" and str(units[0].get("조문번호")) in ("0", ""):
        text = (units[0].get("조문내용") or "").strip()
        return {"head": "본문", "title": None, "text": text, "paragraphs": [], "full_text": text,
                "effective": units[0].get("조문시행일자"), "single_provision": True}
    return None


# ── 판례 ──────────────────────────────────────────────────────
def _prec_item(it):
    return {"prec_id": it.get("판례일련번호"), "number": it.get("사건번호"), "court": it.get("법원명"),
            "date": (it.get("선고일자") or "").replace(".", ""), "title": it.get("사건명"),
            "kind": it.get("판결유형"), "type": it.get("사건종류명")}


def _prec_root(client, query=None, nb=None, display=20, page=1, fulltext=False, court=None):
    params = {"target": "prec", "display": display, "page": page}
    if nb:
        params["nb"] = nb
    else:
        params["query"] = query
        if fulltext:
            params["search"] = 2
    if court:
        params["curt"] = court
    obj = client.get("lawSearch.do", **params)
    root = obj.get("PrecSearch")
    if not isinstance(root, dict):
        raise FormatChanged("PrecSearch 없음")
    return root


def search_prec(client, query=None, nb=None, display=20, page=1, fulltext=False, court=None):
    """판례 목록. nb 는 사건번호 검색(정확 일치 후보), query 는 사건명(기본)·본문(fulltext) 검색. 형식 검사는 하지 않는다."""
    root = _prec_root(client, query, nb, display, page, fulltext, court)
    try:
        total = int(root.get("totalCnt") or 0)
    except ValueError:
        raise FormatChanged("totalCnt 해석 실패")
    return total, [_prec_item(it) for it in _list(root.get("prec"))]


_BR = re.compile(r"<br\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def clean(s):
    return re.sub(r"[ \t]+", " ", _TAGS.sub("", _BR.sub("\n", s or ""))).strip()


def get_prec(client, prec_id):
    obj = client.get("lawService.do", target="prec", ID=prec_id)
    ps = obj.get("PrecService")
    if not isinstance(ps, dict):
        return None  # 법제처가 본문을 주지 않는 판례(목록에만 있음)
    return {"prec_id": str(prec_id), "number": ps.get("사건번호"), "court": ps.get("법원명"),
            "date": (ps.get("선고일자") or "").replace(".", ""), "title": ps.get("사건명"), "kind": ps.get("판결유형"),
            "holdings": clean(ps.get("판시사항")), "summary": clean(ps.get("판결요지")),
            "ref_articles": clean(ps.get("참조조문")), "ref_cases": clean(ps.get("참조판례")),
            "body": clean(ps.get("판례내용"))}


def find_prec_exact(client, number, strict=False):
    """사건번호 정확 일치 판례 목록(같은 번호의 여러 판결이 있을 수 있다). strict 면 응답 형식을 검사한다."""
    want = P.nows(number)
    root = _prec_root(client, nb=number, display=20)
    if strict:
        check_search(root, "prec")
    hits = [it for it in (_prec_item(x) for x in _list(root.get("prec"))) if P.nows(it["number"]) == want]
    if strict and not hits:
        check_search(root, "prec", matched=False)
    return hits


# ── 키 검증·오류 매핑(키 등록·cite_check ping 이 같이 쓴다) ──
KEY_CHECK_CASE = "2016다225353"  # 공개 대법원 판례 — 키·IP 검증용 조회 1건


def verify_key(client):
    """판례 1건 조회로 키·IP 를 검증한다(응답 형식 검사는 켜지 않는다)."""
    find_prec_exact(client, KEY_CHECK_CASE)


def error_result(e):
    """법제처 예외 → (출력 JSON, 종료 코드). CLI·ping 공용."""
    if isinstance(e, NoKey):
        return {"ok": False, "error": "no_key", "guide": str(e)}, 4
    if isinstance(e, KeyInvalid):
        return {"ok": False, "error": "key_invalid", "detail": str(e), "guide": KEY_GUIDE}, 4
    if isinstance(e, NetworkBlocked):
        return {"ok": False, "error": "network_blocked", "detail": str(e)}, 7
    if isinstance(e, Unavailable):
        return {"ok": False, "error": "outage", "detail": str(e)}, 5
    if isinstance(e, FormatChanged):
        return {"ok": False, "error": "format_changed", "detail": str(e), "guide": P.FORMAT_GUIDE}, 5
    raise e


# ── 법령용어 ──────────────────────────────────────────────────
def search_term(client, term):
    obj = client.get("lawSearch.do", target="lstrm", query=term, display=10)
    root = obj.get("LsTrmSearch") or obj.get("lstrmSearch") or {}
    items = _list(root.get("lstrm"))
    return [{"term": it.get("법령용어명"), "id": it.get("법령용어ID") or it.get("법령용어 일련번호"),
             "link": _mask(it.get("법령용어상세링크") or "")} for it in items]


# ── 그 밖의 목록 — 법령해석례(expc)·헌재결정(detc)·행정규칙(admrul) 등 ─────────
TARGETS = {"law", "prec", "expc", "detc", "admrul", "lstrm", "ordin", "trty"}


def _target(t):
    if t not in TARGETS:
        raise P.BriefError("target 은 %s 중 하나입니다" % "·".join(sorted(TARGETS)))
    return t


def search(client, target, query, display=20, page=1, fulltext=False):
    """원 응답(JSON) 그대로 — 목록 키는 target 마다 다르다(예: expc → Expc, detc → Detc)."""
    params = {"target": _target(target), "query": query, "display": display, "page": page}
    if fulltext:
        params["search"] = 2
    return client.get("lawSearch.do", **params)


def detail(client, target, item_id):
    return client.get("lawService.do", target=_target(target), ID=item_id)


# ── 별표·서식 ─────────────────────────────────────────────────
# 법령(licbyl)·행정규칙(admbyl)의 별표·서식 목록과 파일 내려받기. 파일은 키 없이 law.go.kr 에서 받는다(2026-10-15 실측).
FORM_URL = "https://www.law.go.kr/LSW/flDownload.do?flSeq="
FORM_KIND = {"별표": 1, "서식": 2}
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _form_number(code, kind):
    m = re.fullmatch(r"(\d{4})(\d{2})", code or "")
    if not m:
        return None
    n, sub = int(m.group(1)), int(m.group(2))
    if kind == "서식":
        return "별지 제%d호%s" % (n, "의%d" % sub if sub else "")
    return "별표 %d%s" % (n, "의%d" % sub if sub else "")


def _file_seq(link):
    m = re.search(r"flSeq=(\d+)", link or "")
    return m.group(1) if m else None


def search_forms(client, query, admin=False, kind=None, by_law=False, display=20, page=1):
    """별표·서식 목록. admin=True 면 행정규칙(고시·예규·훈령), by_law=True 면 query 를 법령명으로 찾는다."""
    params = {"target": "admbyl" if admin else "licbyl", "query": query, "display": display, "page": page}
    if by_law:
        params["search"] = 2
    if kind:
        if kind not in FORM_KIND:
            raise P.BriefError("--kind 는 별표 또는 서식입니다")
        params["knd"] = FORM_KIND[kind]
    obj = client.get("lawSearch.do", **params)
    root = obj.get("admRulBylSearch" if admin else "licBylSearch")
    if not isinstance(root, dict):
        raise FormatChanged("별표·서식 목록 없음")
    items = []
    for it in _list(root.get("admrulbyl" if admin else "licbyl")):
        k = it.get("별표종류")
        items.append({"id": it.get("별표일련번호"), "name": (it.get("별표명") or "").strip(), "kind": k,
                      "number": _form_number(it.get("별표번호"), k),
                      "source": it.get("관련행정규칙명") if admin else it.get("관련법령명"),
                      "ministry": it.get("소관부처명"), "date": it.get("발령일자") if admin else it.get("공포일자"),
                      "hwp": _file_seq(it.get("별표서식파일링크")), "pdf": _file_seq(it.get("별표서식PDF파일링크"))})
    try:
        total = int(root.get("totalCnt") or 0)
    except ValueError:
        total = len(items)
    return {"total": total, "page": page, "items": items}


def _download_form(seq):
    """(파일 이름, content-type, 내용). 고정 주소 FORM_URL 로만 받는다."""
    req = urllib.request.Request(FORM_URL + seq, headers={"User-Agent": "lawfirm-lawapi"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body, ctype = r.read(), (r.headers.get("Content-Type") or "").split(";")[0].strip()
            disp = r.headers.get("Content-Disposition") or ""
    except urllib.error.HTTPError as e:
        raise Unavailable("서식 파일 HTTP %d" % e.code)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        if sandbox_network_blocked():
            raise NetworkBlocked(NETWORK_BLOCKED)
        raise Unavailable("서식 파일 연결 실패: %s" % e.__class__.__name__)
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disp)
    name = urllib.parse.unquote(m.group(1)) if m else ""
    return name, ctype, body


FORM_MAGIC = (b"%PDF", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"PK\x03\x04", b"HWP Document File")  # PDF·HWP 5(OLE)·HWPX(ZIP)·HWP 3


def _check_form(ctype, body):
    """법제처는 없는 번호·점검 중에도 HTTP 200 으로 HTML 을 준다 — 그것을 서식 파일로 저장하지 않는다."""
    if not body or ctype.startswith("text/") or body[:512].lstrip()[:1] == b"<":
        raise Unavailable("서식 파일 대신 오류 페이지가 왔습니다 — 파일 번호(form-search 의 hwp·pdf 값)를 확인하거나 나중에 다시 시도")
    if not body.startswith(FORM_MAGIC):
        raise Unavailable("서식 파일 형식을 알 수 없습니다(PDF·HWP·HWPX 가 아님 — 저장하지 않음)")


def get_form(seq, out_dir):
    """서식 파일을 out_dir 에 저장 — 같은 이름이 있으면 _2, _3 … 을 붙인다(덮어쓰지 않음)."""
    seq = str(seq).strip()
    if not seq.isdigit():
        raise P.BriefError("파일 번호는 숫자입니다(form-search 결과의 hwp·pdf 값)")
    name, ctype, body = _download_form(seq)
    _check_form(ctype, body)
    ext = {"application/pdf": ".pdf", "application/hwp": ".hwp", "application/x-hwp": ".hwp"}.get(ctype, "")
    base = _BAD_NAME.sub("_", os.path.basename(name.replace("\\", "/"))).strip(" .") or "서식_%s%s" % (seq, ext)
    stem, suffix = os.path.splitext(base)
    suffix = suffix or ext
    os.makedirs(out_dir, exist_ok=True)
    path, n = os.path.join(out_dir, stem + suffix), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(out_dir, "%s_%d%s" % (stem, n, suffix))
    with open(path, "xb") as f:
        f.write(body)
    return {"path": path, "bytes": len(body), "content_type": ctype, "source": FORM_URL + seq}


# ── CLI ───────────────────────────────────────────────────────
def _art(s):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", s or "")
    if not m:
        raise P.BriefError("--article 은 288 또는 266-2 형식입니다")
    return int(m.group(1)), int(m.group(2) or 0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key"); ks = k.add_subparsers(dest="kcmd", required=True)
    ks.add_parser("status")
    s = ks.add_parser("set"); s.add_argument("--prompt", action="store_true"); s.add_argument("--stdin", action="store_true")
    s.add_argument("--no-check", action="store_true")
    ks.add_parser("clear")
    s = sub.add_parser("law"); s.add_argument("name"); s.add_argument("--article")
    s = sub.add_parser("prec-search"); s.add_argument("query"); s.add_argument("--nb", action="store_true")
    s.add_argument("--fulltext", action="store_true"); s.add_argument("--court")
    s.add_argument("--display", type=int, default=20); s.add_argument("--page", type=int, default=1)
    s = sub.add_parser("prec"); s.add_argument("prec_id")
    s = sub.add_parser("term"); s.add_argument("term")
    s = sub.add_parser("search"); s.add_argument("target"); s.add_argument("query")
    s.add_argument("--display", type=int, default=20); s.add_argument("--page", type=int, default=1)
    s.add_argument("--fulltext", action="store_true")
    s = sub.add_parser("detail"); s.add_argument("target"); s.add_argument("item_id")
    s = sub.add_parser("form-search"); s.add_argument("query"); s.add_argument("--admin", action="store_true")
    s.add_argument("--kind", choices=sorted(FORM_KIND)); s.add_argument("--law", action="store_true")
    s.add_argument("--display", type=int, default=20); s.add_argument("--page", type=int, default=1)
    s = sub.add_parser("form-get"); s.add_argument("file_seq"); s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "key":
            if a.kcmd == "status":
                oc, src = find_key()
                return P.emit({"ok": True, "configured": bool(oc), "source": src, "config": config_path(),
                               "guide": None if oc else KEY_GUIDE})
            if a.kcmd == "set":
                if a.prompt:
                    oc = ask("법제처 Open API 키(OC)를 입력하십시오. https://open.law.go.kr → OPEN API 사용 신청에서 받은 값입니다",
                             "법제처 Open API")
                elif a.stdin:
                    oc = sys.stdin.readline()
                else:
                    raise P.BriefError("키(OC)는 --prompt(입력 창) 또는 --stdin 으로만 받습니다 — 명령행에 남기지 않습니다")
                oc = (oc or "").strip()
                if not oc:
                    raise P.BriefError("빈 키는 저장하지 않습니다")
                if a.no_check:
                    return P.emit({"ok": True, "saved": save_key(oc), "checked": False})
                try:
                    verify_key(Client(oc=oc))  # 키 오류 검사를 통과해야 저장한다
                except NotJson:
                    out, _ = error_result(FormatChanged("응답 형식 변경으로 키를 검증하지 못했습니다 — `--no-check` 로 저장하고 "
                                                        "나중에 `cite_check.py ping` 으로 확인할 수 있습니다"))
                    return P.emit(out, 5)
                except (KeyInvalid, Unavailable) as e:
                    return P.emit(*error_result(e))
                except FormatChanged:
                    return P.emit({"ok": True, "saved": save_key(oc), "checked": False,
                                   "warning": "키 오류 검사는 통과해 저장했지만 판례 검색 응답 형식이 바뀌어 확인하지 못했습니다 — "
                                              "`cite_check.py ping` 으로 다시 확인하십시오"})
                return P.emit({"ok": True, "saved": save_key(oc), "checked": True})
            return P.emit({"ok": True, "cleared": clear_key()})
        if a.cmd == "form-get":  # 파일은 키 없이 받는다
            return P.emit(dict(get_form(a.file_seq, a.out), ok=True))
        c = Client()
        if a.cmd == "form-search":
            return P.emit(dict(search_forms(c, a.query, admin=a.admin, kind=a.kind, by_law=a.law,
                                            display=a.display, page=a.page), ok=True))
        if a.cmd == "law":
            law = search_law(c, a.name, strict=True)
            if not law:
                return P.emit({"ok": True, "found": False, "detail": "법령명 정확 일치 없음"})
            out = {"ok": True, "found": True, "law": law}
            if a.article:
                n, m = _art(a.article)
                out["article"] = get_article(c, law["law_id"], n, m)
            return P.emit(out)
        if a.cmd == "prec-search":
            if a.nb and a.page == 1:  # 사건번호 검색 1쪽은 형식을 검사한다(제목·본문 검색·2쪽 이상은 끔)
                root = _prec_root(c, nb=a.query, display=a.display, page=1, court=a.court)
                items = [_prec_item(x) for x in _list(root.get("prec"))]
                check_search(root, "prec", 1, matched=bool(items))
                total = int(root.get("totalCnt") or 0)
            else:
                total, items = search_prec(c, nb=a.query if a.nb else None, query=None if a.nb else a.query,
                                           display=a.display, page=a.page, fulltext=a.fulltext, court=a.court)
            return P.emit({"ok": True, "total": total, "page": a.page, "items": items})
        if a.cmd == "prec":
            d = get_prec(c, a.prec_id)
            return P.emit({"ok": True, "found": bool(d), "prec": d})
        if a.cmd == "term":
            return P.emit({"ok": True, "items": search_term(c, a.term)})
        if a.cmd == "search":
            return P.emit({"ok": True, "result": json.loads(_mask(json.dumps(
                search(c, a.target, a.query, a.display, a.page, a.fulltext), ensure_ascii=False)))})
        if a.cmd == "detail":
            return P.emit({"ok": True, "result": json.loads(_mask(json.dumps(detail(c, a.target, a.item_id), ensure_ascii=False)))})
    except (NoKey, KeyInvalid, Unavailable, FormatChanged) as e:
        return P.emit(*error_result(e))
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
