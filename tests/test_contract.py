"""법제처 계약 점검(FR-04) — 가짜 클라이언트로 녹화와 같은 응답·필드 1개 뺀 응답·목록 밖 필드를 비교한다(네트워크 없음)."""
import copy
import io
import json
import os
import shutil
import sys

import pytest

import lawapi as L
from conftest import RECORDED, ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import contract as K  # noqa: E402


def _rec(name):
    return json.load(open(os.path.join(RECORDED, name), encoding="utf-8"))


class FakeLawClient:
    def __init__(self, key, mutate=None):
        self.key, self.mutate = key, mutate or {}

    def get(self, path, **params):
        if self.key == K.FAKE_OC:
            raise L.KeyInvalid("법제처 사용자 검증 실패")
        for fname, p, prm, _ in K.LAW_CASES:
            if p == path and prm == params:
                obj = copy.deepcopy(_rec(fname)) if os.path.exists(os.path.join(RECORDED, fname)) else {"LawSearch": {"totalCnt": "0"}}
                if fname in self.mutate:
                    self.mutate[fname](obj)
                return obj
        raise AssertionError((path, params))


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    rec = tmp_path / "recorded"
    shutil.copytree(RECORDED, str(rec))
    monkeypatch.setattr(K, "RECORDED", str(rec))
    monkeypatch.setenv("INTENT_BRIEF_LAW_OC", "realsecret")

    def _run(mutate=None):
        code = K.run_law(client_factory=lambda key: FakeLawClient(key, mutate))
        out = capsys.readouterr().out
        assert "realsecret" not in out
        return code, json.loads(out)
    return _run


def test_same_shape_exit_0(run):
    code, out = run()
    assert code == 0 and out["requests"] == 12 and out["diffs"] == []


def _drop(path):
    def f(obj):
        node = obj
        for k in path[:-1]:
            node = node[k][0] if isinstance(node[k], list) else node[k]
        node.pop(path[-1])
    return f


@pytest.mark.parametrize("fname,path", [
    ("drf_law_search_민사소송법.json", ["LawSearch", "law", "법령ID"]),
    ("drf_prec_nb_2016다225353.json", ["PrecSearch", "prec", "판례일련번호"]),
    ("drf_prec_184487.json", ["PrecService", "판결요지"]),
    ("drf_article_001700_028800.json", ["법령", "조문", "조문단위"]),
])
def test_dropped_listed_field_exit_1(run, fname, path):
    code, out = run({fname: _drop(path)})
    assert code == 1 and any(d.startswith(fname) and path[-1] in d for d in out["diffs"])


def _units(obj):
    u = obj["법령"]["조문"]["조문단위"]
    return u if isinstance(u, list) else [u]


def test_dropped_paragraph_exit_1(run):
    code, out = run({"drf_article_001700_045100.json": lambda o: [x.pop("항", None) for x in _units(o)]})
    assert code == 1 and any(d.endswith(".항") for d in out["diffs"])


def test_nested_item_fields_dropped(run):
    """조문 본문 경로의 호·목 — 녹화에 있는 것만 본다."""
    rec = _rec("drf_article_001700_045100.json")
    shapes = K.shape(rec, K.law_keys("article"))
    nested = [k for k in ("호", "목") if any(p.endswith("." + k) for p in shapes)]
    assert "호" in nested

    def drop_ho(obj):
        for u in obj["법령"]["조문"]["조문단위"] if isinstance(obj["법령"]["조문"]["조문단위"], list) else [obj["법령"]["조문"]["조문단위"]]:
            for h in (u.get("항") if isinstance(u.get("항"), list) else [u.get("항")]) if u.get("항") else []:
                if isinstance(h, dict):
                    h.pop("호", None)
    code, out = run({"drf_article_001700_045100.json": drop_ho})
    assert code == 1 and any(d.endswith(".호") for d in out["diffs"])


def test_outside_list_field_is_warning_only(run):
    code, out = run({"drf_law_search_민사소송법.json": lambda o: o["LawSearch"].update(새필드="x")})
    assert code == 0 and out["warnings_outside_list"] == 1


def test_no_key_exit_3(monkeypatch, capsys, home):
    for k in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        monkeypatch.delenv(k, raising=False)
    assert K.run_law(client_factory=lambda key: FakeLawClient(key)) == 3
    capsys.readouterr()


def test_network_blocked_exit_7_not_outage(monkeypatch, capsys):
    monkeypatch.setenv("INTENT_BRIEF_LAW_OC", "k")

    class Blocked:
        def get(self, *a, **k):
            raise L.NetworkBlocked("x")
    assert K.run_law(client_factory=lambda key: Blocked()) == 7
    assert json.loads(capsys.readouterr().out)["error"] == "network_blocked"


def test_empty_law_search_recording_exists():
    obj = _rec(K.EMPTY_LAW)
    assert obj["LawSearch"].get("totalCnt") == "0"
    L.check_search(obj["LawSearch"], "law", page=1, matched=False)  # FR-31 거짓 경보 0
