"""첫 사용 고지(FR-35 · S-01) — 세션 시작 훅이 사용자 화면에 보이는 systemMessage 로 한 번 알린다.

환경(Claude Code·Codex)마다 따로 기록하고, 문구 판이 바뀌면 다시 알린다. 고지 끔 환경변수면 출력·기록 0.
"""
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "skills", "litigation-calc", "scripts")
sys.path.insert(0, SCRIPTS)
import dday as DD  # noqa: E402


@pytest.fixture
def on(home, monkeypatch):
    monkeypatch.delenv("INTENT_BRIEF_NO_NOTICE", raising=False)
    for k in ("PLUGIN_ROOT", "PLUGIN_DATA"):
        monkeypatch.delenv(k, raising=False)
    return home


def hook(capsys):
    assert DD.main(["hook"]) == 0
    raw = capsys.readouterr().out
    assert raw == "" or raw.isascii()
    return json.loads(raw) if raw else None


def record(home):
    p = os.path.join(str(home), ".intent-brief", "notice.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def test_first_session_shows_notice_once(on, capsys):
    out = hook(capsys)
    msg = out["systemMessage"]
    assert "변호사 업무 보조용" in msg and "모델 제공자" in msg and "state.py purge" in msg
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "모델 제공자" in out["hookSpecificOutput"]["additionalContext"]
    assert record(on)["claude"]["version"] == DD.NOTICE_VERSION
    assert hook(capsys) is None  # 두 번째 세션 — 기한도 없으니 출력 없음


def test_environments_recorded_separately(on, capsys, monkeypatch):
    hook(capsys)
    monkeypatch.setenv("PLUGIN_ROOT", "/x")  # Codex 는 플러그인 훅에 PLUGIN_ROOT 를 준다
    assert "systemMessage" in hook(capsys)
    assert set(record(on)) == {"claude", "codex"}
    assert hook(capsys) is None


def test_new_version_notifies_again(on, capsys, monkeypatch):
    hook(capsys)
    monkeypatch.setattr(DD, "NOTICE_VERSION", DD.NOTICE_VERSION + "-next")
    assert "systemMessage" in hook(capsys)


def test_notice_off_env_outputs_and_records_nothing(on, capsys, monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_NO_NOTICE", "1")
    assert hook(capsys) is None and record(on) is None


def test_notice_merges_with_deadlines(on, tmp_path, capsys):
    from test_dday import _case
    root = tmp_path / "사건"
    _case(root, "260901_손해배상(가명갑)")
    DD.roots_add(str(root))
    out = hook(capsys)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "systemMessage" in out and "모델 제공자" in ctx and "D-3" in ctx


def test_record_write_refused_shows_guide_and_retries(on, capsys, monkeypatch):
    def deny(*a, **k):
        raise PermissionError(13, "Operation not permitted")
    monkeypatch.setattr(DD, "_write_notice_record", deny)
    out = hook(capsys)
    assert "기록하지 못했습니다" in out["systemMessage"]
    assert record(on) is None
    monkeypatch.undo()


def test_hook_never_fails_on_notice_error(on, capsys, monkeypatch):
    monkeypatch.setattr(DD, "notice_text", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert DD.main(["hook"]) == 0
    capsys.readouterr()


def test_replay_turns_notice_off():
    sys.path.insert(0, os.path.join(ROOT, "dev"))
    import replay
    assert replay.replay_env("http://127.0.0.1:1/DRF")["INTENT_BRIEF_NO_NOTICE"] == "1"


def test_hook_descriptions_mention_notice():
    h = json.load(open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8"))
    assert "첫 사용 고지" in h["description"]
    assert "첫 사용 고지" in open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()


def test_hook_subprocess_first_notice(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("INTENT_BRIEF_NO_NOTICE", "PLUGIN_ROOT", "PLUGIN_DATA")}
    env.update(HOME=str(tmp_path), LOCALAPPDATA=str(tmp_path / "AppData" / "Local"))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "dday.py"), "hook"], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0 and "systemMessage" in json.loads(r.stdout)
