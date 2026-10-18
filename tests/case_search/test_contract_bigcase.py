"""빅케이스 계약 점검(FR-06)·HTTP 예산(NFR-03)·로컬 녹화 재생(FR-05) — 가짜 HTTP, 네트워크·키체인 없음."""
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("scrapling", reason="빅케이스 테스트는 scrapling·keyring 이 필요 — AGENTS.md Health Stack 의 셋째 줄로 돌린다")
pytest.importorskip("keyring")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "skills" / "case-search" / "scripts"))
import bigcase  # noqa: E402
import contract as K  # noqa: E402
from test_bigcase import FakeHTTP, Resp, jwt, signin  # noqa: E402

SYN = {n: json.load(open(HERE / "synthetic" / (n + ".json"), encoding="utf-8"))
       for n in ("search", "similar", "brief", "decisions", "decision", "case")}
ROUTES = {
    ("post", "/esapi/cases/search"): "search", ("get", "/esapi/cases/similar/search/v2"): "similar",
    ("post", "/esapi/brief/search/v2"): "brief", ("post", "/decision-cases/searchList"): "decisions",
    ("get", "/decision-cases/view/7"): "decision", ("get", "/esapi/cases/match_view"): "case",
}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make(session, data=None, extra=None):
    data = data or SYN
    routes = {k: Resp(200, data[v]) for k, v in ROUTES.items()}
    routes.update(extra or {})
    bc = object.__new__(bigcase.Bigcase)
    bc._email = bc._password = None
    bc.http = FakeHTTP(routes)
    bc.session = session
    clock = Clock()
    bc.http = K.Budget(bc.http, clock=clock, sleep=clock.sleep)
    return bc


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    monkeypatch.setenv("BIGCASE_ID", "u@example.com")
    monkeypatch.setenv("BIGCASE_PW", "pw")


def valid():
    return {"email": "u@example.com", "accessToken": jwt(time.time() + 3600), "refreshToken": "r"}


@pytest.mark.parametrize("scenario,session,extra,total", [
    ("valid", valid, {}, 6),
    ("expired", lambda: dict(valid(), accessToken=jwt(time.time() - 10)),
     {("post", "/auth/renew"): Resp(200, {"accessToken": jwt(time.time() + 3600), "refreshToken": "r2"})}, 7),
    ("renew_fails", lambda: dict(valid(), accessToken=jwt(time.time() - 10)),
     {("post", "/auth/renew"): Resp(500, {}), ("post", "/auth/unified-signin"): signin()}, 8),
])
def test_http_budget_scenarios(env, scenario, session, extra, total):
    bc = make(session(), extra=extra)
    out, code = K.run_bigcase_with(bc, refs=SYN)
    assert code == 0 and out["done"] == list(SYN) and bc.http.total == total
    assert all(b - a >= 2.0 for a, b in zip(bc.http.times, bc.http.times[1:]))


def test_http_budget_401_retry(env):
    first = {"n": 0}

    def search(kw):
        first["n"] += 1
        return Resp(401, {}) if first["n"] == 1 else Resp(200, SYN["search"])
    bc = make(valid(), extra={("post", "/esapi/cases/search"): search,
                              ("post", "/auth/renew"): Resp(200, {"accessToken": jwt(time.time() + 3600), "refreshToken": "r2"})})
    out, code = K.run_bigcase_with(bc, refs=SYN)
    assert code == 0 and bc.http.total == 8 and bc.http.used == {"data": 6, "auth": 1, "retry": 1}


def test_budget_stops_before_exceeding(env):
    clock = Clock()
    b = K.Budget(FakeHTTP({("get", "/x"): Resp(200, {})}), clock=clock, sleep=clock.sleep)
    b.LIMITS = dict(b.LIMITS, data=100)
    for i in range(10):
        b.get("https://bigcase.ai/api/v1/x%d" % i) if False else None
    calls = 0
    with pytest.raises(K.BudgetExceeded):
        for i in range(11):
            b.http.routes[("get", "/x%d" % i)] = Resp(200, {})
            b.get("https://bigcase.ai/api/v1/x%d" % i)
            calls += 1
    assert calls == 10


def test_incomplete_exit_6(env):
    bc = make(valid())
    bc.http.LIMITS = dict(bc.http.LIMITS, data=3)
    out, code = K.run_bigcase_with(bc, refs=SYN)
    assert code == 6 and out["error"] == "incomplete" and out["done"] == ["search", "similar", "brief"]


@pytest.mark.parametrize("name,drop", [
    ("search", ("results",)), ("similar", ("results",)), ("brief", ("results",)),
    ("decisions", ("datas",)), ("decision", ("filepath",)), ("case", ("fulltext", "reasoning")),
])
def test_dropped_field_each_command_exit_1(env, name, drop):
    live = copy.deepcopy(SYN)
    node = live[name]
    for k in drop[:-1]:
        node = node[k]
    node.pop(drop[-1])
    out, code = K.run_bigcase_with(make(valid(), data=live), refs=SYN)
    assert code == 1 and any(x.startswith(name + ":") and drop[-1] in x for x in out["diffs"])


def test_not_logged_in_exit_4(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    for n in ("BIGCASE_ID", "BIGCASE_PW", "BICCASE_ID", "BICCASE_PW"):
        monkeypatch.delenv(n, raising=False)
    assert K.run_bigcase() == 4
    assert json.loads(capsys.readouterr().out)["error"] == "skipped"


def test_record_refuses_secret_like_response(env, tmp_path, monkeypatch):
    monkeypatch.setattr(K, "BIGCASE_LOCAL", str(tmp_path / "rec"))
    live = copy.deepcopy(SYN)
    live["case"]["note"] = "contact someone@lawoffice.kr"
    out, code = K.run_bigcase_with(make(valid(), data=live), record=True)
    assert "case" not in out["recorded"] and any("녹화 안 함" in d for d in out["diffs"])
    assert sorted(os.listdir(tmp_path / "rec")) == ["brief.json", "decision.json", "decisions.json", "search.json", "similar.json"]


# ── FR-05 로컬 녹화(git 무시) ──
LOCAL = ROOT / "tests" / "case_search" / "recorded_local"


def test_local_recordings_are_ignored_and_untracked():
    assert subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "tests/case_search/recorded_local/case.json"]).returncode == 0
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "tests/case_search/recorded_local"], capture_output=True, text=True).stdout
    assert out.strip() == ""


@pytest.mark.parametrize("name", list(ROUTES.values()))
def test_replay_local_recording(env, name):
    path = LOCAL / (name + ".json")
    if not path.exists():
        pytest.skip("빅케이스 로컬 녹화 없음 — dev/contract.py bigcase --record 로 이 PC 에 만든다")
    rec = json.load(open(path, encoding="utf-8"))
    d, _ = K.compare(rec, rec, K.bigcase_keys(name))
    assert d == []
    keys = K.shape(rec, K.bigcase_keys(name))
    assert keys, "녹화에 키 목록의 키가 하나도 없음"
    if name == "search":
        assert bigcase.summarize_search(rec, "q", 1)["results"]
    if name == "case":
        assert bigcase.case_markdown(rec)


@pytest.mark.parametrize("name", list(ROUTES.values()))
def test_replay_synthetic_through_client(env, name):
    bc = make(valid())
    fn = dict(K.bigcase_commands(bc))
    if name == "decision":
        fn["decisions"]()
    got = fn[name]()
    assert K.compare(SYN[name], got, K.bigcase_keys(name))[0] == []


def test_renamed_key_in_recording_is_detected():
    bad = copy.deepcopy(SYN["search"])
    bad["results"][0]["사건번호"] = bad["results"][0].pop("case_number")
    assert K.compare(SYN["search"], bad, K.bigcase_keys("search"))[0] == ["results[].case_number"]
