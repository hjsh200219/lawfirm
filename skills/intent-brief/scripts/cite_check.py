"""초안 인용(조문·판례)이 법제처 Open API 원문에 존재하는지 대조한다(법령명·사건번호 정확 일치).

모델이 검색 결과를 옮겨 적지 않는다 — 이 스크립트가 lawapi.py 로 법제처 DRF 를 직접 부른다(MCP 없음).
판례는 사건번호 검색(nb) 결과의 사건번호가 정확히 같은 항목만 「확인됨」으로 본다. 「확인됨」은 그 조문·판례가
존재한다는 뜻이며 인용의 적합성은 보증하지 않는다. 키(OC)가 없으면 대조하지 않고 멈춘다(태그도 붙이지 않는다).
법제처에 원문이 없는 판례는 case-search(빅케이스)가 설치·로그인돼 있으면 한 건당 한 번 찾아 「external」로 표시한다 —
「확인됨」(법제처 원문 정확 일치)과 섞지 않는다. 초안에 선고일이 있으면 원문 선고일이 있고 같을 때만 「확인됨」이다.
법제처·빅케이스 응답 형식이 바뀌면 「미확인」으로 넘기지 않고 「응답 형식 변경」으로 드러낸다(추가 호출 0).

사용:
  cite_check.py ping
  cite_check.py extract <draft.md>
  cite_check.py run <draft.md> [--max-seconds 540]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402
import casesearch as CS  # noqa: E402
import lawapi as L  # noqa: E402


# ── 추출 ──────────────────────────────────────────────────────
LAW_NAMES = ["민사소송법", "민사조정법", "민사집행법", "민법", "상법", "이자제한법", "소송촉진 등에 관한 특례법",
             "가사소송법", "행정소송법", "헌법", "주택임대차보호법", "상가건물 임대차보호법", "근로기준법"]
_LAW_STOP = {"방법", "증거방법", "위법", "적법", "불법", "편법", "입법", "사법", "해석법", "문법", "수법", "필법", "기법", "작법"}
_TOKEN = re.compile(r"(?P<law>%s|같은 법|동법|[가-힣]{2,15}법)|(?P<art>제\s*(?P<n>\d+)\s*조(?:\s*의\s*(?P<m>\d+))?)"
                    % "|".join(re.escape(x) for x in LAW_NAMES))
_CASE_FULL = re.compile(r"(?P<court>대법원|[가-힣]+(?:고등|지방)법원)\s*(?P<y>\d{4})\.\s*(?P<mo>\d{1,2})\.\s*(?P<d>\d{1,2})\.\s*"
                        r"(?:선고|자)\s*(?P<nums>\d{2,4}[가-힣]{1,4}\d+(?:\s*,\s*\d+)*)\s*(?:전원합의체\s*)?(?:판결|결정)")
_CASE_BARE = re.compile(r"(?P<nums>\d{4}[가-힣]{1,4}\d{1,7})\s*(?:전원합의체\s*)?(?:판결|결정)")


def _strip_header(md):
    """사건 표시(sec.header) 구간의 우리 사건번호는 대조 대상이 아니다."""
    m = re.search(r"^##\s*\[sec:sec\.header\].*?(?=^##\s|\Z)", md, re.M | re.S)
    if not m:
        return md
    return md[:m.start()] + " " * (m.end() - m.start()) + md[m.end():]


def extract(md):
    text = _strip_header(md)
    laws, cases, seen = [], [], set()
    cur, last_end = None, -999
    for m in _TOKEN.finditer(text):
        if m.group("law"):
            name = m.group("law")
            if name in ("같은 법", "동법"):
                last_end = m.end()
                continue
            if name in _LAW_STOP or name.endswith("방법"):
                cur = None
                continue
            cur, last_end = name, m.end()
        elif m.group("art") and cur and m.start() - last_end <= 25:
            n, sub = int(m.group("n")), int(m.group("m")) if m.group("m") else 0
            key = ("law", cur, n, sub)
            if key not in seen:
                seen.add(key)
                laws.append({"kind": "law", "law": cur, "article": n, "sub": sub, "text": "%s 제%d조%s" % (cur, n, "의%d" % sub if sub else ""),
                             "pos": m.start()})
            last_end = m.end()
    covered = []
    for m in _CASE_FULL.finditer(text):
        covered.append((m.start(), m.end()))
        first = m.group("nums").split(",")[0].strip()
        prefix = re.match(r"(\d{2,4}[가-힣]{1,4})", first).group(1)
        date = "%04d%02d%02d" % (int(m.group("y")), int(m.group("mo")), int(m.group("d")))
        for i, part in enumerate(m.group("nums").split(",")):
            part = part.strip()
            num = part if i == 0 else prefix + part
            key = ("case", num, date)  # 선고일이 다르면 따로 대조 — 틀린 날짜 인용이 묻히지 않게
            if key not in seen:
                seen.add(key)
                cases.append({"kind": "case", "number": num, "court": m.group("court"), "date": date, "text": m.group(0), "pos": m.start()})
    for m in _CASE_BARE.finditer(text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        num = m.group("nums")
        key = ("case", num, None)
        if key not in seen and not any(k[:2] == ("case", num) for k in seen):
            seen.add(key)
            cases.append({"kind": "case", "number": num, "court": None, "date": None, "text": m.group(0), "pos": m.start()})
    return laws + cases


# ── 대조 ──────────────────────────────────────────────────────
class CachedClient:
    """같은 요청은 작업 폴더 캐시에서 — 다시 실행하면 이어 간다. 캐시에는 키(OC)를 남기지 않는다."""

    def __init__(self, inner, cache_dir, deadline=None):
        self.inner = inner
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.deadline = deadline
        self.calls = 0
        self.written = []  # 이번 인용 대조에서 새로 쓴 캐시 — 형식 오류면 지운다
        self.read = []  # 이번 인용 대조에서 읽은 캐시 — 형식 오류면 같이 지운다(이전 실행의 잘못된 응답)

    def get(self, path, **params):
        key = hashlib.sha256(json.dumps([path, params], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        fp = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(fp):
            self.read += [fp, fp[:-5] + ".req.json"]
            return P.load_json(fp)
        if self.deadline and time.time() > self.deadline:
            raise TimeoutError("시간 상한")
        obj = self.inner.get(path, **params)
        self.calls += 1
        P.atomic_write_text(fp, L._mask(json.dumps(obj, ensure_ascii=False)))
        P.atomic_write_json(fp[:-5] + ".req.json", {"path": path, "params": params})
        self.written += [fp, fp[:-5] + ".req.json"]
        return obj

    def mark(self):
        return len(self.written), len(self.read)

    def forget(self, since=(0, 0)):
        """since 뒤에 쓰거나 읽은 캐시를 지운다 — 그 인용(또는 보조 조회)의 요청 파일만, 사건 폴더·다른 인용 캐시는 그대로."""
        for f in self.written[since[0]:] + self.read[since[1]:]:
            try:
                os.remove(f)
            except OSError:
                pass
        self.written, self.read = self.written[:since[0]], self.read[:since[1]]


SOURCE = "https://www.law.go.kr"  # 법제처 공개 조회 화면 — 「확인됨」 행의 원문 위치(키 없이 열린다)


def law_url(name, article, sub=0):
    return "%s/법령/%s/제%d조%s" % (SOURCE, P.nows(name), article, "의%d" % sub if sub else "")


def prec_url(number):
    return "%s/판례/(%s)" % (SOURCE, P.nows(number))


CHECK_VERSION = 1  # 빅케이스 「없음」 캐시의 검사 판 — 검사 규칙을 바꾸면 올린다(옛 판 「없음」만 1회 다시 조회)


def _excerpt_case(d):
    out = []
    for label, k in (("판시사항", "holdings"), ("판결요지", "summary")):
        if d.get(k):
            out.append("%s: %s" % (label, re.sub(r"\s+", " ", d[k]).strip()[:300]))
    return " / ".join(out)


class Checker:
    def __init__(self, cache_dir, client=None, deadline=None, external=None):
        self.client = CachedClient(client or L.Client(), cache_dir, deadline)
        self.external = external
        self.ext_cache = os.path.join(cache_dir, "external")

    @property
    def calls(self):
        return self.client.calls

    def check_law(self, c):
        law = L.search_law(self.client, c["law"], strict=True)
        if not law:
            return {"status": "unverified", "detail": "법령명 정확 일치 없음"}
        art = L.get_article(self.client, law["law_id"], c["article"], c["sub"])
        if not art:
            return {"status": "unverified", "detail": "조문 본문 없음", "law_id": law["law_id"]}
        body = " ".join([art["text"]] + art["paragraphs"][:1])
        return {"status": "confirmed", "law_id": law["law_id"], "excerpt": re.sub(r"\s+", " ", body)[:200],
                "source_url": law_url(law.get("name") or c["law"], c["article"], c["sub"])}

    def check_case(self, c):
        hits = L.find_prec_exact(self.client, c["number"], strict=True)
        if c.get("court"):
            same = [h for h in hits if P.nows(h["court"]) == P.nows(c["court"])]
            hits = same or hits
        if hits:
            hit = next((h for h in hits if c.get("date") and h["date"] == c["date"]), hits[0])
            if c.get("date") and not hit["date"]:
                return {"status": "unverified", "detail": "원문 선고일 없음 — 선고일 대조 못 함", "prec_id": hit["prec_id"]}
            if c.get("date") and hit["date"] != c["date"]:
                return {"status": "unverified", "detail": "선고일 불일치(원문 %s)" % hit["date"], "prec_id": hit["prec_id"]}
            d = L.get_prec(self.client, hit["prec_id"])
            return {"status": "confirmed", "prec_id": hit["prec_id"], "title": hit["title"], "date": hit["date"],
                    "excerpt": _excerpt_case(d) if d else "", "source_url": prec_url(hit["number"] or c["number"])}
        detail = "사건번호 정확 일치 없음(법제처 원문 없음)"
        res = {"status": "unverified", "cited_by": None}
        mark = self.client.mark()
        try:  # 인용 수 셈은 보조 정보 — 실패해도 주 판정과 빅케이스 대조를 덮지 않는다
            cited_by, _ = L.search_prec(self.client, query=c["number"], fulltext=True, display=1)
            res["cited_by"] = cited_by
            if cited_by:
                detail += " · 이 번호를 인용한 다른 판결 %d건 검색됨 — 원문은 변호사가 확인" % cited_by
        except (L.FormatChanged, L.Unavailable) as e:
            if isinstance(e, L.NetworkBlocked):
                raise
            self.client.forget(mark)
            detail += " · 인용 수 조회 실패"
            res["note"] = "인용 수 조회 실패"
        res["detail"] = detail
        return self._external(c, res) if self.external else res

    def _external(self, c, res):
        """법제처에 없을 때만 빅케이스 1회(캐시) — 있으면 external, 선고일이 다르면 unverified."""
        key = hashlib.sha256(json.dumps([c["number"], c.get("court")], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        fp = os.path.join(self.ext_cache, key + ".json")
        got = P.load_json(fp) if os.path.exists(fp) else None
        if got is not None and got.get("hit") is None and got.get("v") != CHECK_VERSION:
            got = None  # 옛 검사 판의 「없음」 — 1회 다시 조회(찾음 캐시는 그대로 쓴다)
        if got is None:
            dl = self.client.deadline
            if dl and dl - time.time() < CS.CALL_TIMEOUT:
                return {"status": "pending", "detail": "시간 상한 — 빅케이스 조회는 다시 실행하면 이어 갑니다"}
            try:
                got = {"hit": self.external.find_exact(c["number"], c.get("court")), "v": CHECK_VERSION}
            except CS.FormatChanged:  # 이름표는 「미확인」 그대로 — 설명과 신고 안내만(캐시하지 않는다)
                return dict(res, detail=res["detail"] + " · 빅케이스 응답 형식 변경 · " + P.FORMAT_GUIDE)
            except CS.SearchError as e:
                return dict(res, detail=res["detail"] + " · 빅케이스 조회 실패(%s)" % str(e)[:80])
            os.makedirs(self.ext_cache, exist_ok=True)
            P.atomic_write_json(fp, got)
        hit = got.get("hit")
        if not hit:
            return dict(res, detail=res["detail"] + " · 빅케이스에도 없음")
        where = "%s %s 선고%s" % (hit.get("court") or "", hit.get("date") or "", (", " + hit["outcome"]) if hit.get("outcome") else "")
        if c.get("date") and not hit.get("date"):
            return dict(res, detail="법제처 원문 없음 · 빅케이스 원문 선고일 없음 — 선고일 대조 못 함", external=hit)
        if c.get("date") and hit["date"] != c["date"]:
            return dict(res, detail="법제처 원문 없음 · 빅케이스 원문과 선고일 불일치(빅케이스 %s)" % hit["date"], external=hit)
        return {"status": "external", "detail": "법제처 원문 없음 — 빅케이스에서 존재 확인(%s)" % where.strip(),
                "external": hit, "cited_by": res.get("cited_by"), "note": res.get("note")}

    def check(self, c):
        self.client.written, self.client.read = [], []
        try:
            return self.check_law(c) if c["kind"] == "law" else self.check_case(c)
        except L.KeyInvalid as e:
            return {"status": "key_invalid", "detail": str(e)[:200]}
        except L.NetworkBlocked:
            raise  # 인용마다 「장애」 태그를 붙이지 않고 대조 전체를 멈춘다 — 네트워크를 허용하고 다시 실행하면 된다
        except L.Unavailable as e:
            return {"status": "outage", "detail": str(e)[:200]}
        except L.FormatChanged as e:
            self.client.forget()  # 틀린 응답이 캐시에 남아 서비스가 돌아온 뒤에도 같은 실패가 되풀이되지 않게
            return {"status": "format_changed", "detail": str(e)[:200] + " · " + P.FORMAT_GUIDE}
        except TimeoutError:
            return {"status": "pending", "detail": "시간 상한 — 다시 실행하면 캐시에서 이어 갑니다"}


TAG_FOR = {"unverified": "unverified", "outage": "outage", "format_changed": "format_changed", "key_invalid": "key_invalid",
           "external": "external"}


def tag_draft(md, results, phrases):
    """확인되지 않은 인용 뒤에 태그를 한 번 붙인다(이미 붙어 있으면 그대로)."""
    for r in sorted(results, key=lambda x: -x["pos"]):
        key = TAG_FOR.get(r["status"])
        if not key:
            continue
        tag = phrases["tag"][key]
        idx = md.find(r["text"])
        if idx < 0:
            continue
        end = idx + len(r["text"])
        if md[end:end + len(tag) + 1].strip().startswith(tag):
            continue
        md = md[:end] + " " + tag + md[end:]
    return md


def run(draft_path, max_seconds=540, client=None, external="auto"):
    deadline = time.time() + max_seconds  # case-search 상태 확인 시간까지 상한에 넣는다
    md = P.read_text(draft_path)
    work = os.path.dirname(os.path.abspath(draft_path))
    cites = extract(md)
    if external == "auto":
        external = CS.client() if any(c["kind"] == "case" for c in cites) else None
    chk = Checker(os.path.join(work, "cite"), client=client, deadline=deadline, external=external)
    results = []
    for c in cites:
        r = dict(c)
        r.update(chk.check(c))
        results.append(r)
    complete = all(r["status"] != "pending" for r in results)
    if complete:
        P.atomic_write_text(draft_path, tag_draft(md, results, P.load_phrases()))
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    out = {"complete": complete, "calls": chk.calls, "summary": summary, "results": results, "casesearch": bool(external)}
    P.atomic_write_json(os.path.join(work, "cite_results.json"), out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    s = sub.add_parser("extract"); s.add_argument("draft")
    s = sub.add_parser("run"); s.add_argument("draft"); s.add_argument("--max-seconds", type=float, default=540)
    a = ap.parse_args(argv)
    if a.cmd == "ping":
        oc, src = L.find_key()
        if not oc:
            return P.emit({"ok": False, "error": "no_key", "guide": L.KEY_GUIDE}, 4)
        try:
            L.verify_key(L.Client(oc=oc))
            return P.emit({"ok": True, "key_source": src})
        except (L.KeyInvalid, L.Unavailable, L.FormatChanged) as e:
            out, code = L.error_result(e)
            if out["error"] in ("outage", "format_changed"):
                out["note"] = "인용 대조만 해당 태그로 표시하고 계속합니다"
            return P.emit(out, code)
    if a.cmd == "extract":
        return P.emit({"ok": True, "citations": extract(P.read_text(a.draft))})
    if a.cmd == "run":
        try:
            return P.emit(dict(ok=True, **run(a.draft, a.max_seconds)))
        except L.NoKey as e:
            return P.emit({"ok": False, "error": "no_key", "guide": str(e)}, 4)
        except L.NetworkBlocked as e:
            return P.emit({"ok": False, "error": "network_blocked", "detail": str(e)}, 7)


if __name__ == "__main__":
    sys.exit(main())
