"""사용 통계 요약(FR-17 허용 필드 7개 · FR-38 복사용 블록) · 네트워크 0(FR-18)."""
import json
import os
import socket

import pytest

import intent as I

ALLOWED = {"cases", "intent_side", "override_cells", "avg_rounds", "fast_path_ratio", "plugin_version", "period"}


def _state(d, name, **kw):
    st = {"intent": {"primary": "W", "fast_path": False}, "side": "원고", "rounds": [1, 2], "overrides": [],
          "created": "2026-10-01T10:00:00", "updated": "2026-10-02T10:00:00"}
    st.update(kw)
    os.makedirs(d, exist_ok=True)
    json.dump(st, open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "cases"
    _state(str(r / "홍길동_대여금"), "준비서면_state.json", overrides=[{"cell": "strength"}])
    _state(str(r / "김대출_답변"), "답변서_state.json", side="피고", intent={"primary": "M", "fast_path": True},
           created="2026-09-20T09:00:00", updated="2026-10-05T09:00:00")
    _state(str(r / "이가명_사건"), "준비서면_state.json",
           side="원고 측 김철수 사건", intent={"primary": "자유입력 의도"}, overrides=[{"cell": "의뢰인 이름 칸"}])
    return str(r)


def test_output_keys_are_allowlisted(root):
    s = I.stats(root)
    assert set(s) == ALLOWED and s["cases"] == 3
    assert s["period"] == {"from": "2026-09-20", "to": "2026-10-05"}


def test_free_text_components_become_other(root):
    blob = json.dumps(I.stats(root), ensure_ascii=False)
    assert "김철수" not in blob and "자유입력" not in blob and "의뢰인 이름" not in blob
    s = I.stats(root)
    assert s["intent_side"]["other|other"] == 1 and s["override_cells"]["other|other|other"] == 1
    assert s["override_cells"]["W|원고|strength"] == 1


def test_no_case_folder_names(root):
    blob = json.dumps(I.stats(root), ensure_ascii=False) + I.share_block(I.stats(root))
    for name in ("홍길동", "김대출", "이가명"):
        assert name not in blob


def test_empty_or_missing_root(tmp_path):
    s = I.stats(str(tmp_path / "없음"))
    assert set(s) == ALLOWED and s["cases"] == 0 and s["period"] is None


def test_share_block_has_only_allowed_fields(root):
    block = I.share_block(I.stats(root))
    body = block.split("```")[1].strip().split("\n", 1)[1] if block.count("```") >= 2 else block
    data = json.loads(body)
    assert set(data) == ALLOWED and "김철수" not in block


def test_share_block_names_no_recipient(root):
    block = I.share_block(I.stats(root))
    for word in ("@", "http", "보내는 곳", "이메일", "issue"):
        assert word not in block


def test_cli_emits_summary_and_block(root, capsys):
    assert I.main(["stats", root]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["summary"]) == ALLOWED and out["share_block"] == I.share_block(out["summary"])


def test_no_network_for_stats_and_hook(root, monkeypatch, tmp_path, capsys):
    attempts = []

    def deny(*a, **k):
        attempts.append(a)
        raise OSError("네트워크 금지(테스트)")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    I.stats(root)
    I.share_block(I.stats(root))
    import sys
    from conftest import ROOT
    sys.path.insert(0, os.path.join(ROOT, "skills", "litigation-calc", "scripts"))
    import dday as dd
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("INTENT_BRIEF_NO_NOTICE", "1")
    try:
        dd.main(["hook"])
    except SystemExit:
        pass
    capsys.readouterr()
    assert attempts == []
