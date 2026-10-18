"""응답 형식 검사(FR-31 법제처 · FR-39 빅케이스) · 키 검증 일원화(FR-37) · 「확인됨」 범위(FR-09) · 정규화 일원화(FR-20).

형식 변경을 「미확인」으로 조용히 넘기지 않는다 — 추가 호출 0, 표준 라이브러리만.
"""
import json
import os
import re
import subprocess

import pytest

import _paths as P
import casesearch as CS
import cite_check as C
import lawapi as L
from conftest import RECORDED, ROOT, SCRIPTS
from test_cite import FakeExternal, FakeLaw, HIT, LAWS, LAW288, MISSING, C2014, P2016, chk, rec

GUIDE = "플러그인을 최신 판으로 업데이트하고, 계속되면 repo 이슈로 알려 주십시오(사건 내용·의뢰인 정보는 적지 마십시오)"


# ── FR-31 법제처 형식 검사: 가짜 응답 3종 ──
BAD_LAW = {
    "required": {"LawSearch": {"totalCnt": "1", "law": [{"법령명": "민사소송법", "ID": "001700"}]}},  # ① 필수 키 없음
    "list_key": {"LawSearch": {"totalCnt": "3", "laws": [{"법령명한글": "민사소송법", "법령ID": "001700"}]}},  # ② 목록 키 변경
    "count_key": {"LawSearch": {"law": [{"법령명한글": "민사집행법", "법령ID": "001701"}]}},  # ③ totalCnt 없음
}
BAD_PREC = {
    "required": {"PrecSearch": {"totalCnt": "1", "prec": [{"일련번호": "1", "번호": "2016다225353"}]}},
    "list_key": {"PrecSearch": {"totalCnt": "2", "precs": []}},
    "count_key": {"PrecSearch": {"prec": [{"판례일련번호": "9", "사건번호": "2016다999"}]}},
}


@pytest.mark.parametrize("kind", sorted(BAD_LAW))
def test_law_search_format_changes_surface(tmp_path, kind):
    r = chk(tmp_path, [({"query": "민사소송법"}, BAD_LAW[kind])]).check(LAW288)
    assert r["status"] == "format_changed" and r["detail"].endswith(GUIDE)
    assert "정확 일치 없음" not in r["detail"]


@pytest.mark.parametrize("kind", sorted(BAD_PREC))
def test_prec_search_format_changes_surface(tmp_path, kind):
    r = chk(tmp_path, [({"nb": "2016다225353"}, BAD_PREC[kind])]).check(
        {"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"})
    assert r["status"] == "format_changed" and r["detail"].endswith(GUIDE)
    assert "사건번호 정확 일치 없음" not in r["detail"]


def test_guide_is_outside_truncation(tmp_path):
    long = L.FormatChanged("x" * 500)
    r = chk(tmp_path, [({"query": "민법"}, long)]).check({"kind": "law", "law": "민법", "article": 1, "sub": 0})
    assert r["detail"].endswith(GUIDE) and len(r["detail"]) == 200 + len(" · ") + len(GUIDE)


def test_recordings_and_empty_results_are_not_format_changes(tmp_path):
    for name in os.listdir(RECORDED):
        if name.startswith(("drf_law_search", "drf_prec_nb")):
            obj = rec(name)
            if "LawSearch" in obj:
                L.check_search(obj["LawSearch"], "law", page=1, matched=False)
            else:
                L.check_search(obj["PrecSearch"], "prec", page=1, matched=False)
    # 녹화가 없는 빈 법령 검색(실측 모양 — totalCnt "0"·law 키 없음)
    L.check_search({"totalCnt": "0"}, "law", page=1, matched=False)


def test_strict_is_off_by_default_for_shared_functions():
    fake = FakeLaw([({"query": "x"}, BAD_PREC["list_key"])])
    assert L.search_prec(fake, query="x") == (2, [])  # 인용 수 셈·제목 검색 경로는 그대로


def test_aux_cited_by_failure_does_not_override_main_verdict(tmp_path):
    import casesearch  # noqa: F401
    for bad in (L.FormatChanged("PrecSearch 없음"), L.Unavailable("HTTP 500")):
        t = [MISSING[0], ({"query": "2014다26187", "search": 2}, bad)]
        ext = FakeExternal(HIT)
        c = C.Checker(str(tmp_path / type(bad).__name__), client=FakeLaw(t), external=ext)
        r = c.check(C2014)
        assert r["status"] == "external" and ext.calls == [("2014다26187", "대법원")]
        assert "인용 수 조회 실패" in r["detail"] or "인용 수 조회 실패" in (r.get("note") or "")


def test_aux_failure_cache_is_removed(tmp_path):
    t = [MISSING[0], ({"query": "2014다26187", "search": 2}, {"Other": {}})]
    c = C.Checker(str(tmp_path / "cite"), client=FakeLaw(t))
    r = c.check(C2014)
    assert r["status"] == "unverified" and "인용 수 조회 실패" in r["detail"]
    reqs = [json.load(open(os.path.join(tmp_path, "cite", n), encoding="utf-8")) for n in os.listdir(tmp_path / "cite") if n.endswith(".req.json")]
    assert [q["params"].get("search") for q in reqs] == [None]  # 주 조회 캐시만 남는다


def test_format_change_clears_read_cache_for_that_citation(tmp_path):
    """V15 — 이전 실행이 남긴 잘못된 응답 캐시도 그 인용에서 읽은 것은 지워, 서비스가 돌아오면 1회 다시 조회한다."""
    cdir = str(tmp_path / "cite")
    bad = C.Checker(cdir, client=FakeLaw([({"query": "민사소송법"}, rec("drf_law_search_민사소송법.json")),
                                          ({"ID": "001700", "JO": "028800"}, {"법령": "점검 중"})]))
    assert bad.check(LAW288)["status"] == "format_changed"
    assert [n for n in os.listdir(cdir) if n.endswith(".json")] == []  # 새로 쓴 것 + 그 인용이 읽은 것 모두
    ok = C.Checker(cdir, client=FakeLaw(LAWS))
    assert ok.check(LAW288)["status"] == "confirmed" and len(ok.client.inner.calls) == 2


def test_cli_strict_paths_exit_5(monkeypatch, capsys):
    for name, bad in (("law", BAD_LAW["list_key"]), ("prec-search", BAD_PREC["list_key"])):
        monkeypatch.setattr(L, "Client", lambda *a, **k: FakeLaw([({}, bad)]))
        argv = ["law", "민사소송법"] if name == "law" else ["prec-search", "2016다225353", "--nb"]
        assert L.main(argv) == 5
        out = json.loads(capsys.readouterr().out)
        assert out["error"] == "format_changed" and out["guide"] == GUIDE


def test_cli_title_search_stays_off(monkeypatch, capsys):
    monkeypatch.setattr(L, "Client", lambda *a, **k: FakeLaw([({}, BAD_PREC["list_key"])]))
    assert L.main(["prec-search", "대여금"]) == 0
    capsys.readouterr()


def test_format_detail_has_no_key(tmp_path):
    leak = L.FormatChanged(L._mask("JSON 이 아닌 응답: OC=realsecret&x"))
    r = chk(tmp_path, [({"query": "민법"}, leak)]).check({"kind": "law", "law": "민법", "article": 1, "sub": 0})
    assert "realsecret" not in json.dumps(r, ensure_ascii=False)


def test_confirmed_count_unchanged_on_recordings(tmp_path):
    assert chk(tmp_path, LAWS).check(LAW288)["status"] == "confirmed"
    assert chk(tmp_path / "b", P2016).check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"})["status"] == "confirmed"


# ── FR-37 키 검증·오류 매핑 일원화 ──
def test_key_check_case_literal_in_one_place():
    hits = subprocess.run(["git", "-C", ROOT, "grep", "-n", "2016다225353", "--", "skills/intent-brief/scripts"],
                          capture_output=True, text=True).stdout.strip().splitlines()
    assert [h.split(":")[0] for h in hits] == ["skills/intent-brief/scripts/lawapi.py"]


@pytest.mark.parametrize("exc,code,saved,checked,rc", [
    (None, None, True, True, 0),
    (L.NotJson("JSON 이 아닌 응답"), "format_changed", False, None, 5),
    (L.KeyInvalid("x"), "key_invalid", False, None, 4),
    (L.FormatChanged("PrecSearch 없음"), None, True, False, 0),
    (L.Unavailable("HTTP 500"), "outage", False, None, 5),
    (L.NetworkBlocked("x"), "network_blocked", False, None, 7),
])
def test_key_set_table(home, monkeypatch, capsys, exc, code, saved, checked, rc):
    import io
    for k in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        monkeypatch.delenv(k, raising=False)

    def verify(client):
        if exc:
            raise exc

    monkeypatch.setattr(L, "verify_key", verify)
    monkeypatch.setattr("sys.stdin", io.StringIO("k1\n"))
    assert L.main(["key", "set", "--stdin"]) == rc
    out = json.loads(capsys.readouterr().out)
    assert (L.find_key()[0] == "k1") is saved
    if code:
        assert out["error"] == code
    else:
        assert out["checked"] is checked
        if checked is False:
            assert "cite_check.py ping" in out["warning"]


def test_ping_goes_through_verify_key(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("INTENT_BRIEF_LAW_OC", "k")

    def verify(client):
        calls.append(client)
        raise L.FormatChanged("PrecSearch 없음")

    monkeypatch.setattr(L, "verify_key", verify)
    assert C.main(["ping"]) == 5
    assert json.loads(capsys.readouterr().out)["error"] == "format_changed" and len(calls) == 1


def test_not_json_is_format_changed_subclass():
    assert issubclass(L.NotJson, L.FormatChanged)


def test_key_setup_doc_has_save_table():
    t = open(os.path.join(ROOT, "commands", "law-key-setup.md"), encoding="utf-8").read()
    assert "키 오류 검사를 통과해야 저장한다" in t and "확인 안 됨" in t and "format_changed" in t


# ── FR-09 「확인됨」 = 존재 확인 ──
FIXED = [("README.md", "적합성은 보증하지 않습니다"), ("skills/intent-brief/SKILL.md", "적합성은 변호사가 본다"),
         ("skills/intent-brief/scripts/render_docx.py", "인용의 적합성은 보증하지 않습니다"),
         ("skills/intent-brief/scripts/render_docx.py", "적합성 미보증"),
         ("skills/intent-brief/scripts/cite_check.py", "인용의 적합성은 보증하지 않는다")]


@pytest.mark.parametrize("path,text", FIXED)
def test_confirmed_meaning_strings_fixed(path, text):
    assert text in open(os.path.join(ROOT, path), encoding="utf-8").read()


def test_only_confirmed_key_maps_to_confirmed_label():
    src = open(os.path.join(SCRIPTS, "render_docx.py"), encoding="utf-8").read()
    assert re.findall(r'"(\w+)": "확인됨"', src) == ["confirmed"]


def test_forbidden_meaning_phrases_absent():
    out = subprocess.run(["git", "-C", ROOT, "grep", "-n", "-E", "문구 (정확 )?일치|문구까지|인용 문구 (대조|비교|일치)",
                          "--", ".", ":!docs/prd", ":!tests/test_format_checks.py"], capture_output=True, text=True).stdout
    assert out == ""


EXIST = "조문·판례 존재 대조(법령명·사건번호 정확 일치)"


@pytest.mark.parametrize("path", ["README.md", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                                  "skills/intent-brief/SKILL.md"])
def test_exact_match_sentences_say_existence(path):
    t = open(os.path.join(ROOT, path), encoding="utf-8").read()
    assert EXIST in t
    assert "원문과 정확 일치로 대조" not in t and "조문·판례 정확 일치 대조" not in t


@pytest.mark.parametrize("prec,want", [
    ({"선고일자": "2017.02.21"}, "confirmed"),
    ({"선고일자": "2017.02.22"}, "선고일 불일치"),
    ({}, "원문 선고일 없음"),
    ({"선고일자": ""}, "원문 선고일 없음"),
])
def test_case_date_rule(tmp_path, prec, want):
    item = dict({"판례일련번호": "184487", "사건번호": "2016다225353", "법원명": "대법원"}, **prec)
    t = [({"nb": "2016다225353"}, {"PrecSearch": {"totalCnt": "1", "prec": [item]}}), P2016[1]]
    r = chk(tmp_path, t).check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"})
    assert (r["status"] == "confirmed") if want == "confirmed" else (r["status"] == "unverified" and want in r["detail"])


def test_external_without_date_is_not_external(tmp_path):
    ext = FakeExternal(dict(HIT, date=None))
    r = C.Checker(str(tmp_path / "cite"), client=FakeLaw(MISSING), external=ext).check(C2014)
    assert r["status"] == "unverified" and "빅케이스 원문 선고일 없음" in r["detail"]


def test_external_never_becomes_confirmed(tmp_path):
    r = C.Checker(str(tmp_path / "cite"), client=FakeLaw(MISSING), external=FakeExternal(HIT)).check(C2014)
    assert r["status"] == "external"


# ── FR-20 공백 제거 정규화는 _paths 1곳 ──
def test_whitespace_normalizer_defined_once():
    # check_draft.py 의 같은 식은 본문 글자 수 세기라 번호 비교 정규화가 아니다(대상 밖)
    out = subprocess.run(["git", "-C", ROOT, "grep", "-n", "-E", r're\.sub\(r"\\s\+", "",', "--", "skills/intent-brief/scripts",
                          ":!skills/intent-brief/scripts/check_draft.py"], capture_output=True, text=True).stdout.strip().splitlines()
    assert [o.split(":")[0] for o in out] == ["skills/intent-brief/scripts/_paths.py"]
    assert P.nows(" 2016 다 225353 ") == "2016다225353"


# ── FR-39 빅케이스 보조 대조 형식 검사(법원 없는 search) ──
class FakeCS(CS.Client):
    def __init__(self, search_out=None, case_out=None):
        self.search_out, self.case_out = search_out, case_out

    def search(self, query, page=1):
        return self.search_out

    def case(self, court, number):
        return self.case_out


@pytest.mark.parametrize("out", [
    {"total": 1, "results": [{"사건번호": "2014다26187", "법원": "대법원"}]},  # ① 필수 키 없음
    {"total": 3, "results": []},  # ② 건수는 있는데 목록 0
])
def test_bigcase_search_format_changed(tmp_path, out):
    with pytest.raises(CS.FormatChanged):
        FakeCS(search_out=out).find_exact("2014다26187")
    r = C.Checker(str(tmp_path / "cite"), client=FakeLaw(MISSING), external=FakeCS(search_out=out)).check(dict(C2014, court=None))
    assert r["status"] == "unverified" and "빅케이스 응답 형식 변경" in r["detail"] and r["detail"].endswith(GUIDE)
    assert "빅케이스에도 없음" not in r["detail"]
    assert not os.path.exists(tmp_path / "cite" / "external")  # 형식 변경은 캐시하지 않는다


def test_bigcase_search_normal_and_empty_pass():
    ok = {"total": 1, "results": [{"case_number": "2014다26187", "court": "대법원", "case_expression": "대법원 2014. 7. 10. 선고 2014다26187 판결"}]}
    assert FakeCS(search_out=ok).find_exact("2014다26187")["date"] == "20140710"
    assert FakeCS(search_out={"total": 0, "results": []}).find_exact("2014다26187") is None


def test_bigcase_case_raw_rule_off_until_keys_recorded():
    keys = json.load(open(os.path.join(ROOT, "skills", "intent-brief", "references", "response-keys.json"), encoding="utf-8"))
    req = keys["bigcase"]["case"]["required"]
    hit = FakeCS(case_out=CS._hit({"case_expression": "x"})).find_exact("2014다26187", "대법원")
    if req is None:
        assert hit is None  # 규칙 끔 — 지금처럼 번호 불일치면 없음


def test_bigcase_not_found_cache_rechecked_once_on_new_version(tmp_path):
    cdir = tmp_path / "cite"
    first = C.Checker(str(cdir), client=FakeLaw(MISSING), external=FakeExternal(None))
    first.check(C2014)
    f = next((cdir / "external").iterdir())
    old = json.load(open(f, encoding="utf-8"))
    assert old.get("v") == C.CHECK_VERSION
    json.dump({"hit": None}, open(f, "w", encoding="utf-8"))  # 옛 판 「없음」 캐시
    ext = FakeExternal(HIT)
    assert C.Checker(str(cdir), client=FakeLaw([]), external=ext).check(C2014)["status"] == "external" and len(ext.calls) == 1
    ext2 = FakeExternal(None)
    assert C.Checker(str(cdir), client=FakeLaw([]), external=ext2).check(C2014)["status"] == "external" and ext2.calls == []
