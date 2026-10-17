"""e2e 재생 구동기(dev/replay.py·dev/e2e.py·dev/drf_replay.py) — 법제처·빅케이스 실서비스 0회, 실행마다 새 결과.

모델을 부르지 않는다(subprocess 를 가짜로 바꾼다). 과금 0.
"""
import json
import os
import subprocess
import sys
import types

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import drf_replay  # noqa: E402
import e2e  # noqa: E402
import lawapi as L  # noqa: E402
import replay  # noqa: E402

VARS = ("INTENT_BRIEF_LAW_URL", "INTENT_BRIEF_NO_CASESEARCH", "INTENT_BRIEF_LAW_OC")


@pytest.fixture
def srv():
    s = drf_replay.Server().start()
    yield s
    s.stop()


def client(s):
    os.environ["INTENT_BRIEF_LAW_URL"] = s.url
    return L.Client(oc="fake", interval=0, timeout=2, backoff=0)


# ── 재생 서버: 녹화는 그대로, 녹화 밖은 엔드포인트별 「결과 없음」 ──
def test_server_serves_recordings(srv, monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_LAW_URL", srv.url)
    c = client(srv)
    assert L.search_law(c, "민사소송법")["law_id"] == "001700"
    assert "불요증사실" in L.get_article(c, "001700", 288)["text"]
    assert [h["prec_id"] for h in L.find_prec_exact(c, "2016다225353")] == ["184487"]
    assert L.get_prec(c, "184487")["number"] == "2016다225353"


def test_server_unrecorded_shapes_are_not_format_changes(srv, monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_LAW_URL", srv.url)
    c = client(srv)
    assert L.search_law(c, "민법") is None  # 법령 검색 totalCnt 0
    assert L.get_article(c, "001700", 1) is None  # 조문 본문 빈 조문단위(제1조는 단일 조문 요청 1개 더)
    assert L.get_article(c, "001700", 750) is None
    assert L.find_prec_exact(c, "2019다12345") == []  # 판례 검색 totalCnt 0
    assert L.get_prec(c, "999999") is None  # 판례 본문 PrecService 없음
    assert srv.count == 6


def test_server_log_hides_key(srv, monkeypatch, tmp_path):
    monkeypatch.setenv("INTENT_BRIEF_LAW_URL", srv.url)
    L.search_law(L.Client(oc="secretkey", interval=0, timeout=2, backoff=0), "민사소송법")
    srv.dump(str(tmp_path / "drf.json"))
    text = (tmp_path / "drf.json").read_text(encoding="utf-8")
    assert "secretkey" not in text and json.loads(text)["count"] == 1


# ── 명령 조립: claude -p 환경·스크립트 환경·프롬프트에 세 변수 ──
def test_script_env_and_draft_command_carry_replay_vars(tmp_path, monkeypatch):
    law = replay.replay_env("http://127.0.0.1:1/DRF")
    assert law["INTENT_BRIEF_NO_CASESEARCH"] == "1" and law["INTENT_BRIEF_LAW_OC"]
    monkeypatch.setattr(replay, "EXTRA_ENV", law)
    env = replay.script_env(str(tmp_path))
    assert all(env[k] == law[k] for k in VARS)

    wd = tmp_path / "wd"
    wd.mkdir()
    state = wd / "state.json"
    state.write_text(json.dumps({"compliance": {}}), encoding="utf-8")
    seen = {}

    def fake_run(cmd, input=None, env=None, **k):
        seen.update(cmd=cmd, env=env, prompt=input.decode("utf-8"))
        (wd / "준비서면_draft.md").write_text("x", encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(replay.subprocess, "run", fake_run)
    replay.draft(str(tmp_path), str(state), "d.json", "case", "준비서면", "claude", "sonnet")
    assert all(seen["env"][k] == law[k] for k in VARS)
    cite_line = next(x for x in seen["prompt"].splitlines() if "cite_check.py run" in x)
    assert all("%s=" % k in cite_line for k in VARS)
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == "sonnet"


# ── 과금 0 사전 시험: 모델 없이 cite_check.py run 을 재생 서버에 ──
def test_precheck_passes_without_model(tmp_path, monkeypatch):
    # e2e 는 cite_check.py 를 하위 프로세스로 부른다 — 시험은 같은 대조를 프로세스 안에서 요청 간격 0 으로
    import cite_check

    def in_process(draft_path, env):
        for k, v in env.items():
            if k.startswith("INTENT_BRIEF_"):
                monkeypatch.setenv(k, v)
        cite_check.run(draft_path, client=L.Client(interval=0, timeout=2, backoff=0))

    r = replay.precheck(str(tmp_path / "pre"), run_cite=in_process)
    assert r["ok"], r
    assert r["server"] == r["req_json"] >= 3 and r["format_changed"] == 0 and r["external"] == 0


def test_cite_audit_reports_direction(tmp_path):
    cite = tmp_path / "cite"
    cite.mkdir()
    (cite / "a.req.json").write_text("{}", encoding="utf-8")
    (tmp_path / "cite_results.json").write_text(json.dumps({"summary": {"unverified": 1}}), encoding="utf-8")
    assert replay.cite_audit(str(tmp_path), 1)["ok"]
    assert "재생 서버 밖" in replay.cite_audit(str(tmp_path), 0)["error"]
    assert "캐시가 지워짐" in replay.cite_audit(str(tmp_path), 2)["error"]
    (tmp_path / "cite_results.json").write_text(json.dumps({"summary": {"format_changed": 1}}), encoding="utf-8")
    assert "format_changed" in replay.cite_audit(str(tmp_path), 1)["error"]
    (cite / "external").mkdir()
    (cite / "external" / "x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "cite_results.json").write_text(json.dumps({"summary": {}}), encoding="utf-8")
    assert "external" in replay.cite_audit(str(tmp_path), 1)["error"]


# ── 실행 식별값: 새 폴더 · 다른 식별값 결과는 재사용 0 · judge 는 식별값 1개만 ──
IDENT = {"head": "h1", "tree": "t1", "model": "sonnet"}


def _report(rd, ident, ok=True):
    os.makedirs(rd, exist_ok=True)
    json.dump({"ok": ok, "ident": ident}, open(os.path.join(rd, "report.json"), "w", encoding="utf-8"))


def test_run_one_reuses_only_same_ident(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(e2e.subprocess, "run", lambda cmd, **k: calls.append(cmd) or types.SimpleNamespace(returncode=0))
    _report(str(tmp_path / "F1A_r1"), IDENT)
    _report(str(tmp_path / "F1A_r2"), dict(IDENT, head="old"))
    assert e2e.run_one(str(tmp_path), IDENT, "F1A", 1)[2] is True and calls == []
    e2e.run_one(str(tmp_path), IDENT, "F1A", 2)
    assert len(calls) == 1 and "--ident" in calls[0] and json.loads(calls[0][calls[0].index("--ident") + 1]) == IDENT
    assert not os.path.exists(str(tmp_path / "F1A_r2" / "report.json"))  # 옛 결과는 치운 뒤 새로 돈다


def test_run_makes_new_folder_and_respects_cap(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(e2e, "ident", lambda model: IDENT)
    monkeypatch.setattr(e2e.R, "precheck", lambda d: {"ok": True})
    monkeypatch.setattr(e2e, "run_one", lambda out, ident, c, i: (c, i, True))
    a = types.SimpleNamespace(out=str(tmp_path), resume=None, runs=3, jobs=1, only=None, model="sonnet", max_claude=15)
    assert e2e.cmd_run(a) == 0
    out = capsys.readouterr().out
    assert "claude -p 15회" in out
    assert len([d for d in os.listdir(str(tmp_path))]) == 1  # 실행 시각 폴더 1개
    a.max_claude = 14
    assert e2e.cmd_run(a) == 2  # 상한 초과 — 시작하지 않는다


def test_run_stops_when_precheck_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(e2e, "ident", lambda model: IDENT)
    monkeypatch.setattr(e2e.R, "precheck", lambda d: {"ok": False, "error": "x"})
    called = []
    monkeypatch.setattr(e2e, "run_one", lambda *x: called.append(x))
    a = types.SimpleNamespace(out=str(tmp_path), resume=None, runs=1, jobs=1, only=["F1A"], model="sonnet", max_claude=15)
    assert e2e.cmd_run(a) == 3 and called == []


def test_judge_refuses_mixed_idents(tmp_path):
    _report(str(tmp_path / "F1A_r1"), IDENT, ok=False)
    _report(str(tmp_path / "F1A_r2"), dict(IDENT, tree="t2"), ok=False)
    a = types.SimpleNamespace(out=str(tmp_path), no_jev=True, max_jev=12)
    assert e2e.cmd_judge(a) == 2


def test_ident_records_head_tree_model():
    i = e2e.ident("sonnet")
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert i["head"] == head and i["model"] == "sonnet" and len(i["tree"]) == 16
