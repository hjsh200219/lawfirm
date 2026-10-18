"""개발 전용 계약 점검 — 녹화(또는 합성) 응답과 실서비스 응답의 구조를 비교한다(받는 PC 에는 쓰이지 않는다).

비교 대상은 런타임이 읽는 키 목록(`skills/intent-brief/references/response-keys.json`)의 존재·값 타입이다.
기준 응답에 있는 목록 안 키가 실서비스에 없거나 타입이 다르면 exit 1 과 차이 경로, 목록 밖 필드의 추가·삭제는 경고 수만 낸다.
응답 본문은 출력하지 않는다(차이 경로만). 키·토큰 값은 어떤 출력에도 쓰지 않는다.

사용:
  python3 dev/contract.py law                     법제처 — 녹화 11개 요청 + 빈 법령 검색 1요청(간격 1초)
  uv run --no-project --with "scrapling[fetchers]>=0.4.11,<0.5" --with "keyring>=25,<26" python dev/contract.py bigcase [--record]
                                                  빅케이스 — 로그인돼 있을 때만 데이터 명령 6개 1회씩(HTTP 10회 이하·간격 2초)
                                                  --record 면 비교 대신 계정 정보 검사를 거쳐 로컬 녹화(git 무시)로 남긴다
exit: 0 일치 · 1 구조 차이 · 3 키 없음 · 4 로그인 안 됨(건너뜀) · 5 장애 · 6 HTTP 예산 소진(미완료) · 7 네트워크 차단
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "intent-brief", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "skills", "case-search", "scripts"))  # bigcase 는 uv 실행에서만 import 한다
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402
import lawapi as L  # noqa: E402
import secret_scan  # noqa: E402

RECORDED = os.path.join(ROOT, "tests", "recorded")
BIGCASE_LOCAL = os.path.join(ROOT, secret_scan.BIGCASE_LOCAL)
BIGCASE_SYNTH = os.path.join(ROOT, "tests", "case_search", "synthetic")
EMPTY_LAW = "drf_law_search_empty.json"
EMPTY_LAW_QUERY = "계약점검용없는법령명"

# (녹화 파일, 경로, 요청 파라미터, 키 목록 종류) — 받는 PC 의 lawapi 가 보내는 요청과 같은 모양
LAW_CASES = [
    ("drf_law_search_민사소송법.json", "lawSearch.do", {"target": "law", "query": "민사소송법", "display": 100, "page": 1}, "law_search"),
    ("drf_law_search_소송촉진법.json", "lawSearch.do", {"target": "law", "query": "소송촉진법", "display": 100, "page": 1}, "law_search"),
    ("drf_article_001700_028800.json", "lawService.do", {"target": "law", "ID": "001700", "JO": "028800"}, "article"),
    ("drf_article_001700_045100.json", "lawService.do", {"target": "law", "ID": "001700", "JO": "045100"}, "article"),
    ("drf_article_003984_000100.json", "lawService.do", {"target": "law", "ID": "003984", "JO": "000100"}, "article"),
    ("drf_law_003984.json", "lawService.do", {"target": "law", "ID": "003984"}, "article"),
    ("drf_prec_nb_2016다225353.json", "lawSearch.do", {"target": "prec", "display": 20, "page": 1, "nb": "2016다225353"}, "prec_search"),
    ("drf_prec_nb_2018다248626.json", "lawSearch.do", {"target": "prec", "display": 20, "page": 1, "nb": "2018다248626"}, "prec_search"),
    ("drf_prec_nb_empty.json", "lawSearch.do", {"target": "prec", "display": 20, "page": 1, "nb": "2014다26187"}, "prec_search"),
    ("drf_prec_184487.json", "lawService.do", {"target": "prec", "ID": "184487"}, "prec"),
    ("drf_bad_key.json", "lawSearch.do", {"target": "prec", "display": 20, "page": 1, "nb": "2016다225353"}, "bad_key"),
    (EMPTY_LAW, "lawSearch.do", {"target": "law", "query": EMPTY_LAW_QUERY, "display": 100, "page": 1}, "law_search"),
]
FAKE_OC = "contract-fake-key"  # 키 오류 녹화는 형식만 맞춘 가짜 키로

# 단일 항목이면 dict 로 오는 목록 키 — 런타임 `_list` 와 같이 목록으로 본다
LISTISH = {"law", "prec", "조문단위", "항", "호", "목", "results", "datas", "attached", "history_cases", "body_infos"}


def _t(v):
    if isinstance(v, dict):
        return "obj"
    if isinstance(v, list):
        return "list"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num"
    return "null" if v is None else "str"


def shape(obj, keys=None, out=None, path=""):
    """{경로: 타입} — keys 가 None 이면 모든 키."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = path + "." + k if path else k
            if k in LISTISH and isinstance(v, dict):
                v = [v]
            if keys is None or k in keys:
                out[p] = _t(v)
            shape(v, keys, out, p)
    elif isinstance(obj, list):
        for it in obj:
            shape(it, keys, out, path + "[]")
    return out


def law_keys(kind):
    spec = P.load_response_keys()["law"][kind]
    return set(spec.get("keys", [])) | {spec[k] for k in ("container", "list", "count") if spec.get(k)}


def bigcase_keys(kind):
    spec = P.load_response_keys()["bigcase"][kind]
    return set(spec.get("keys", [])) | {spec[k] for k in ("list", "count") if spec.get(k)}


def compare(ref, live, keys):
    """(차이 경로, 목록 밖 경고 수) — 기준에 있는 목록 안 키가 실서비스에 없거나 타입이 다르면 차이."""
    r, lv = shape(ref, keys), shape(live, keys)
    diffs = sorted(p for p, t in r.items() if p not in lv or (t != lv[p] and "null" not in (t, lv[p])))
    ra, la = set(shape(ref)) - set(r), set(shape(live)) - set(lv)
    return diffs, len(ra ^ la)


def _load(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def _emit(obj, code):
    print(L._mask(json.dumps(obj, ensure_ascii=False, indent=1)))
    return code


# ── 법제처 ──
def run_law(client_factory=None, sleep=time.sleep):
    oc, _ = L.find_key()
    if not oc:
        return _emit({"ok": False, "error": "no_key", "guide": L.KEY_GUIDE}, 3)
    make = client_factory or (lambda key: L.Client(oc=key, interval=1.0))
    real, fake = make(oc), make(FAKE_OC)
    diffs, warnings, done = [], 0, 0
    for fname, path, params, kind in LAW_CASES:
        ref = _load(os.path.join(RECORDED, fname))
        try:
            if kind == "bad_key":
                try:
                    fake.get(path, **params)
                    diffs.append("%s: 키 오류 응답이 사용자 검증 실패로 읽히지 않음" % fname)
                except L.KeyInvalid:
                    pass
                done += 1
                continue
            live = real.get(path, **params)
            done += 1
        except L.NetworkBlocked as e:
            return _emit({"ok": False, "error": "network_blocked", "detail": str(e), "done": done}, 7)
        except L.Unavailable as e:
            return _emit({"ok": False, "error": "outage", "detail": str(e), "done": done}, 5)
        except L.FormatChanged as e:
            diffs.append("%s: %s" % (fname, str(e)[:120]))
            continue
        if ref is None:  # 빈 법령 검색 — 녹화가 없으면 1회 실측을 녹화로 남긴다(키는 가림)
            P.atomic_write_text(os.path.join(RECORDED, fname), L._mask(json.dumps(live, ensure_ascii=False, indent=1)))
            continue
        d, w = compare(ref, live, law_keys(kind))
        diffs += ["%s: %s" % (fname, p) for p in d]
        warnings += w
    return _emit({"ok": not diffs, "service": "law", "requests": done, "diffs": diffs, "warnings_outside_list": warnings}, 1 if diffs else 0)


# ── 빅케이스 ──
class BudgetExceeded(Exception):
    pass


class NotSent(Exception):
    """앞 명령 결과가 없어 보내지 않음 — 그 앞 명령의 구조 차이로 남는다."""


class Budget:
    """빅케이스 HTTP 예산(NFR-03) — 데이터 6 · 인증(갱신·로그인) 2 · 401 재시도 2 · 전체 10, 모든 HTTP 사이 2초 이상.
    다음 요청이 예산을 넘으면 보내지 않는다."""
    LIMITS = {"data": 6, "auth": 2, "retry": 2}
    TOTAL, GAP = 10, 2.0

    def __init__(self, http, clock=time.monotonic, sleep=time.sleep):
        self.http, self.clock, self.sleep = http, clock, sleep
        self.used = {"data": 0, "auth": 0, "retry": 0}
        self.seen, self.times, self.last = [], [], None

    @property
    def total(self):
        return sum(self.used.values())

    def _call(self, method, url, **kw):
        kind = "auth" if "/auth/" in url else ("retry" if (method, url) in self.seen else "data")
        if self.used[kind] + 1 > self.LIMITS[kind] or self.total + 1 > self.TOTAL:
            raise BudgetExceeded("%s 예산 초과(사용 %s)" % (kind, self.used))
        if self.last is not None:
            wait = self.GAP - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        self.used[kind] += 1
        self.seen.append((method, url))
        self.last = self.clock()
        self.times.append(self.last)
        return getattr(self.http, method)(url, **kw)

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, **kw):
        return self._call("post", url, **kw)


BRIEF_TEXT = "원고가 피고에게 5천만원을 빌려주었으나 변제기가 지나도 갚지 않아 대여금 반환을 청구한 사건"  # 손으로 쓴 합성 서술문
CASE = ("대법원", "2014다26187")  # 공개 판례 번호


def bigcase_commands(bc):
    """데이터 명령 6개 — (이름, 호출). decision 은 decisions 결과의 첫 id 로."""
    state = {}

    def decisions():
        d = bc.decisions("결정례", "대여금")
        state["id"] = ((d or {}).get("datas") or [{}])[0].get("id")
        return d

    def decision():
        if not state.get("id"):
            raise NotSent("decisions 결과에 id 가 없어 보내지 않음")
        d = bc.decision("결정례", str(state["id"]))
        return d.get("data", d) if isinstance(d, dict) else d

    return [("search", lambda: bc.search(CASE[1])), ("similar", lambda: bc.similar(*CASE)),
            ("brief", lambda: bc.brief(BRIEF_TEXT, 1, "cases")), ("decisions", decisions), ("decision", decision),
            ("case", lambda: bc.case(*CASE))]


def run_bigcase_with(bc, record=False, refs=None):
    """bc 는 http 가 Budget 으로 감싸진 Bigcase. 반환 (출력, exit)."""
    import bigcase as B
    diffs, warnings, done, recorded, case_keys = [], 0, [], [], None
    for name, call in bigcase_commands(bc):
        try:
            live = call()
        except BudgetExceeded as e:
            return {"ok": False, "error": "incomplete", "detail": str(e), "done": done, "http": bc.http.used}, 6
        except NotSent as e:
            diffs.append("%s: %s" % (name, e))
            continue
        except B.BigcaseError as e:
            diffs.append("%s: %s" % (name, str(e)[:120]))
            done.append(name)
            continue
        done.append(name)
        if name == "case" and isinstance(live, dict):
            case_keys = sorted(live)  # 최상위 키 이름만(값 0) — case --raw 필수 키 결정에 쓴다
        if record:
            text = json.dumps(live, ensure_ascii=False, indent=1)
            hits = secret_scan.scan_text(text)
            if hits:
                diffs.append("%s: 녹화 안 함 — 계정·비밀 형식 %s" % (name, ",".join(hits)))
                continue
            os.makedirs(BIGCASE_LOCAL, exist_ok=True)
            P.atomic_write_text(os.path.join(BIGCASE_LOCAL, name + ".json"), text)
            recorded.append(name)
            continue
        ref = (refs or {}).get(name)
        if ref is None:
            ref = _load(os.path.join(BIGCASE_LOCAL, name + ".json")) or _load(os.path.join(BIGCASE_SYNTH, name + ".json"))
        d, w = compare(ref, live, bigcase_keys(name))
        diffs += ["%s: %s" % (name, p) for p in d]
        warnings += w
    out = {"ok": not diffs, "service": "bigcase", "done": done, "http": bc.http.used, "diffs": diffs,
           "warnings_outside_list": warnings, "case_top_keys": case_keys}
    if record:
        out["recorded"] = recorded
    return out, 1 if diffs else 0


def run_bigcase(record=False):
    import bigcase as B
    email, _ = B.configured_email()
    try:
        logged = bool(email and B.stored_password(email)[0])
    except B.BigcaseError:
        logged = False
    if not logged:
        return _emit({"ok": False, "error": "skipped", "detail": "빅케이스 로그인 정보 없음 — 건너뜀"}, 4)
    with B.Bigcase() as bc:
        bc.http = Budget(bc.http)
        out, code = run_bigcase_with(bc, record=record)
    out.pop("email", None)
    return _emit(out, code)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["law"]:
        return run_law()
    if argv[:1] == ["bigcase"]:
        return run_bigcase(record="--record" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
