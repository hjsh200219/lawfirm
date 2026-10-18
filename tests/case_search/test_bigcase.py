"""오프라인 단위 테스트 — 네트워크·키체인을 쓰지 않는다.

실행: uv run --no-project --with "scrapling[fetchers]>=0.4.11,<0.5" --with "keyring>=25,<26" --with pytest --with python-docx==1.2.0 pytest tests -q
"""
import base64
import json
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("scrapling", reason="빅케이스 테스트는 scrapling·keyring 이 필요 — AGENTS.md Health Stack 의 셋째 줄로 돌린다")
pytest.importorskip("keyring")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "case-search" / "scripts"))
import bigcase  # noqa: E402


def jwt(exp):
    p = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{p}.s"


class Resp:
    def __init__(self, status, body):
        self.status, self.body = status, json.dumps(body).encode()


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _do(self, method, url, **kw):
        self.calls.append((method, url.split("/api/v1")[-1], kw.get("headers", {}).get("Authorization")))
        handler = self.routes[(method, url.split("/api/v1")[-1])]
        return handler(kw) if callable(handler) else handler

    def get(self, url, **kw):
        return self._do("get", url, **kw)

    def post(self, url, **kw):
        return self._do("post", url, **kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    monkeypatch.setenv("BIGCASE_ID", "u@example.com")
    monkeypatch.setenv("BIGCASE_PW", "pw")
    monkeypatch.delenv("BICCASE_ID", raising=False)
    monkeypatch.delenv("BICCASE_PW", raising=False)


def client(routes, session=None):
    bc = bigcase.Bigcase.__new__(bigcase.Bigcase)
    bc._email = bc._password = None
    bc.http = FakeHTTP(routes)
    bc.session = session or {}
    return bc


def signin(status="integrated", at=None):
    return Resp(200, {"signInStatus": status, "accountType": "x", "user": {"role": "r"},
                      "accessToken": at or jwt(time.time() + 3600), "refreshToken": "rt1"})


def test_jwt_exp_handles_garbage():
    assert bigcase._jwt_exp("nope") == 0
    assert bigcase._jwt_exp(jwt(123)) == 123


def test_login_saves_session_without_password(env):
    bc = client({("post", "/auth/unified-signin"): signin()})
    s = bc.login()
    saved = json.loads(bigcase.session_file().read_text())
    assert saved["email"] == "u@example.com" and saved["refreshToken"] == "rt1"
    assert "pw" not in json.dumps(saved)
    assert oct(bigcase.session_file().stat().st_mode)[-3:] == "600"
    assert s["signInStatus"] == "integrated"


def test_login_rejects_unfinished_integration(env):
    bc = client({("post", "/auth/unified-signin"): signin(status="exist-intg")})
    with pytest.raises(bigcase.BigcaseError, match="signInStatus=exist-intg"):
        bc.login()


def test_login_http_error(env):
    bc = client({("post", "/auth/unified-signin"): Resp(400, {"message": "bad"})})
    with pytest.raises(bigcase.BigcaseError, match="HTTP 400 bad"):
        bc.login()


def test_valid_token_is_reused(env):
    at = jwt(time.time() + 3600)
    bc = client({}, {"email": "u@example.com", "accessToken": at, "refreshToken": "rt"})
    assert bc.access_token() == at and bc.http.calls == []


def test_expired_token_renews(env):
    new = jwt(time.time() + 3600)
    bc = client({("post", "/auth/renew"): Resp(200, {"accessToken": new, "refreshToken": "rt2"})},
                {"email": "u@example.com", "accessToken": jwt(1), "refreshToken": "rt"})
    assert bc.access_token() == new
    assert bc.session["refreshToken"] == "rt2"


def test_failed_renew_falls_back_to_login(env):
    bc = client({("post", "/auth/renew"): Resp(401, {}), ("post", "/auth/unified-signin"): signin()},
                {"email": "u@example.com", "accessToken": jwt(1), "refreshToken": "bad"})
    bc.access_token()
    assert [c[1] for c in bc.http.calls] == ["/auth/renew", "/auth/unified-signin"]


def test_other_accounts_token_is_ignored(env):
    bc = client({("post", "/auth/unified-signin"): signin()},
                {"email": "other@example.com", "accessToken": jwt(time.time() + 3600), "refreshToken": "rt"})
    bc.access_token()
    assert bc.http.calls[0][1] == "/auth/unified-signin"


def test_401_retries_once_after_renew(env):
    seen = []

    def folders(kw):
        seen.append(kw["headers"]["Authorization"])
        return Resp(401, {}) if len(seen) == 1 else Resp(200, [{"_id": "f"}])

    fresh = jwt(time.time() + 7200)
    bc = client({("get", "/my-documents/folders"): folders,
                 ("post", "/auth/renew"): Resp(200, {"accessToken": fresh, "refreshToken": "rt2"})},
                {"email": "u@example.com", "accessToken": jwt(time.time() + 3600), "refreshToken": "rt"})
    assert bc.get("/my-documents/folders") == [{"_id": "f"}]
    assert seen[1] == f"Bearer {fresh}"


def test_search_body_and_summary(env):
    captured = {}

    def search(kw):
        captured.update(kw["json"])
        return Resp(200, {"result_count": 2, "results": [
            {"case_id": "1", "case_expression": "대법원 … 99도4797 판결 사기", "case_number": "99도4797",
             "court": "대법원", "case_type": "형사", "outcome": "상고기각", "level": 3, "paragraph": "긴 본문"}]})

    bc = client({("post", "/esapi/cases/search"): search},
                {"email": "u@example.com", "accessToken": jwt(time.time() + 3600)})
    d = bc.search("사기", 2)
    assert captured == {"q": "사기", "page": 2, "complete": "1"}
    s = bigcase.summarize_search(d, "사기", 2)
    assert s["total"] == 2 and "paragraph" not in s["results"][0]
    assert s["results"][0]["url"] == "https://bigcase.ai/cases/%EB%8C%80%EB%B2%95%EC%9B%90/99%EB%8F%844797"


def test_env_overrides_and_legacy_names(monkeypatch, tmp_path):
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    monkeypatch.delenv("BIGCASE_ID", raising=False)
    monkeypatch.setenv("BICCASE_ID", "legacy@example.com")
    assert bigcase.configured_email() == ("legacy@example.com", "환경변수 BICCASE_ID")


def test_case_request_and_markdown(env):
    captured = {}

    def view(kw):
        captured.update(kw["params"])
        return Resp(200, {
            "case_expression": "대법원 2000. 2. 11. 선고 99도4797 판결 사기", "case_number": "99도4797", "court": "대법원",
            "outcome": "상고기각", "judgment_date": "2000-02-11", "holdings": "[1] 판시",
            "ref_laws": '[1] <law_cite ref="형법/제347조">형법 제347조</law_cite>[2] 형법 제351조',
            "fulltext": {"body_court": "대법원\n판결", "body_infos": [{"item": "피고인", "content": "A"}],
                         "disposition": "상고를 기각한다.", "claim": [], "reasoning": "상고이유를 본다.", "judges": "대법관 X"},
            "attached": [{"title": "별지", "files": ["a.jpg", "b.jpg"]}],
            "history_cases": [{"case_expression": "서울지방법원 99노7843"}], "restricted": False})

    bc = client({("get", "/esapi/cases/match_view"): view},
                {"email": "u@example.com", "accessToken": jwt(time.time() + 3600)})
    md = bigcase.case_markdown(bc.case("대법원", "99도4797"))
    assert captured == {"case_number": "99도4797", "court": "대법원"}
    assert "<law_cite" not in md and "형법 제347조\n[2] 형법 제351조" in md
    assert "### 주문\n\n상고를 기각한다." in md and "### 이유\n\n상고이유를 본다." in md
    assert "- 피고인: A" in md and "- 별지: 2장" in md and "### 청구취지" not in md


def test_parse_case_ref():
    assert bigcase.parse_case_ref(["대법원", "99도4797"]) == ("대법원", "99도4797")
    assert bigcase.parse_case_ref(["수원지방법원", "성남지원", "2022고합240"]) == ("수원지방법원 성남지원", "2022고합240")
    url = "https://bigcase.ai/cases/%EC%88%98%EC%9B%90%EC%A7%80%EB%B0%A9%EB%B2%95%EC%9B%90%20%EC%84%B1%EB%82%A8%EC%A7%80%EC%9B%90/2022%EA%B3%A0%ED%95%A9240"
    assert bigcase.parse_case_ref([url]) == ("수원지방법원 성남지원", "2022고합240")
    with pytest.raises(bigcase.BigcaseError):
        bigcase.parse_case_ref(["99도4797"])


def test_similar_brief_decisions_requests(env):
    seen = {}

    def rec(name, body):
        def h(kw):
            seen[name] = kw.get("params") or kw.get("json")
            return Resp(200, body)
        return h

    bc = client({
        ("get", "/esapi/cases/similar/search/v2"): rec("similar", {"results": [
            {"case_number": "87도2193", "court": "대법원", "ranking": 1, "paragraph": "긴 본문"}]}),
        ("post", "/esapi/brief/search/v2"): rec("brief", {"result_count": 1, "results": []}),
        ("post", "/administrative-appeals/searchList"): rec("decisions", {"total_count": 1, "datas": [
            {"id": 1, "title": "t", "date": "2021-02-09", "organizationName": "o", "highlight": "['<em>사기</em> 요지']"}]}),
        ("get", "/administrative-appeals/view/1"): rec("decision", {"id": 1, "filepath": "https://x/1.pdf"}),
    }, {"email": "u@example.com", "accessToken": jwt(time.time() + 3600)})
    rows = bigcase.case_rows(bc.similar("대법원", "99도4797")["results"], bigcase.SEARCH_FIELDS + ("ranking",))
    assert seen["similar"] == {"case_number": "99도4797", "court": "대법원"}
    assert rows[0]["ranking"] == 1 and "paragraph" not in rows[0] and rows[0]["url"].endswith("87%EB%8F%842193")
    bc.brief("서술문", 2, "laws")
    assert seen["brief"]["text"] == "서술문" and seen["brief"]["type"] == "laws" and seen["brief"]["page"] == 2
    s = bigcase.summarize_decisions(bc.decisions("행정심판", "사기"), "행정심판", "사기", 1)
    assert seen["decisions"] == {"query": "사기", "page": 1}
    assert s["results"][0]["snippet"] == "사기 요지"
    assert bc.decision("행정심판", "1")["filepath"] == "https://x/1.pdf"


@pytest.mark.parametrize("url", ["https://evil.example/api", "http://bigcase.ai/api/v1/x", "https://bigcase.ai.evil.example/x",
                                 "https://user@bigcase.ai/x", "https://bigcase.ai@evil.example/x", "https://bigcase.ai:8443/x"])
def test_request_never_sends_token_off_host(env, url):
    """Bearer 토큰은 https://bigcase.ai 로만 — 다른 호스트·평문 http 주소는 요청 전에 거부한다."""
    bc = client({}, {"accessToken": jwt(time.time() + 3600)})
    with pytest.raises(bigcase.BigcaseError):
        bc.get(url)
    assert bc.http.calls == []


def test_decision_id_cannot_escape_path(env):
    bc = client({("get", "/administrative-appeals/view/..%2F..%2Fauth%2Frenew"): Resp(200, {"id": 1})},
                {"accessToken": jwt(time.time() + 3600)})
    bc.decision("행정심판", "../../auth/renew")
    assert bc.http.calls[-1][1] == "/administrative-appeals/view/..%2F..%2Fauth%2Frenew"


def test_api_url_accepts_bigcase_and_normalizes():
    assert bigcase._api_url("/esapi/x") == "https://bigcase.ai/api/v1/esapi/x"
    assert bigcase._api_url("https://bigcase.ai/api/v1/esapi/x") == "https://bigcase.ai/api/v1/esapi/x"
    assert bigcase._api_url("https://BIGCASE.AI/api/v1/x") == "https://bigcase.ai/api/v1/x"
    assert "\t" not in bigcase._api_url("https://bigcase.ai\t/api/v1/x")


def test_http_404_message_matches_casesearch_contract():
    """casesearch.py 는 stderr 의 「HTTP 404」 로 「없음」을 가른다 — 그 문구 계약."""
    bc = client({("get", "/esapi/cases/match_view"): Resp(404, {"message": "없음"})}, {"accessToken": jwt(time.time() + 3600)})
    with pytest.raises(bigcase.BigcaseError, match=r"HTTP 404"):
        bc.case("대법원", "2099다99999")


def test_stdout_is_utf8_on_cp949_console(tmp_path):
    """한국어 Windows 콘솔(cp949)에서도 출력은 UTF-8 — casesearch.py 가 UTF-8 로 읽는다."""
    import os
    import subprocess
    script = Path(__file__).resolve().parents[2] / "skills" / "case-search" / "scripts" / "bigcase.py"
    env = {**os.environ, "PYTHONIOENCODING": "cp949", "CASE_SEARCH_HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, env=env).stdout
    assert "빅케이스" in out.decode("utf-8")


def test_dialog_cancel_vs_failure(monkeypatch):
    """창을 못 띄운 것(Codex 샌드박스 등)을 「취소」로 보면 등록 절차가 끝나 버린다 — osascript 취소는 -128, 우리 PowerShell 창 취소는 3."""
    import types

    def run(rc, err):
        return lambda *a, **k: types.SimpleNamespace(returncode=rc, stdout="" if isinstance(err, str) else b"", stderr=err)
    monkeypatch.setattr(bigcase.subprocess, "run", run(1, "execution error: User canceled. (-128)"))
    with pytest.raises(bigcase.BigcaseError, match="취소"):
        bigcase._osascript_dialog("m", True)
    monkeypatch.setattr(bigcase.subprocess, "run", run(1, "Operation not permitted"))
    with pytest.raises(bigcase.BigcaseError, match="띄우지 못했습니다"):
        bigcase._osascript_dialog("m", True)
    monkeypatch.setattr(bigcase.subprocess, "run", run(3, b""))
    with pytest.raises(bigcase.BigcaseError, match="취소"):
        bigcase._windows_dialog("m", True, None)
    monkeypatch.setattr(bigcase.subprocess, "run", run(1, b"Access denied"))
    with pytest.raises(bigcase.BigcaseError, match="띄우지 못했습니다"):
        bigcase._windows_dialog("m", True, None)
