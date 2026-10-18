"""빅케이스 setup·login·token·status·forget 경로(FR-10) — 가짜 HTTP·가짜 키체인, 네트워크·실제 키체인 없음."""
import io
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("scrapling", reason="빅케이스 테스트는 scrapling·keyring 이 필요 — AGENTS.md Health Stack 의 셋째 줄로 돌린다")
pytest.importorskip("keyring")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "case-search" / "scripts"))
import bigcase  # noqa: E402
from test_bigcase import FakeHTTP, Resp, jwt, signin  # noqa: E402

REAL = bigcase.Bigcase


def client(routes, session=None):
    bc = object.__new__(REAL)  # 진짜 클래스로 — main() 이 여는 자리만 FakeBigcase 로 바꾼다
    bc._email = bc._password = None
    bc.http = FakeHTTP(routes)
    bc.session = session or {}
    return bc


class FakeKeyring:
    priority = 5

    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, pw):
        self.store[(service, user)] = pw

    def delete_password(self, service, user):
        self.store.pop((service, user))


@pytest.fixture
def kr(tmp_path, monkeypatch):
    k = FakeKeyring()
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    for n in ("BIGCASE_ID", "BIGCASE_PW", "BICCASE_ID", "BICCASE_PW"):
        monkeypatch.delenv(n, raising=False)
    import keyring
    monkeypatch.setattr(keyring, "get_keyring", lambda: k)
    return k


class FakeBigcase:
    """main()·cmd_setup 이 여는 Bigcase 자리 — HTTP 는 FakeHTTP."""
    routes = {}
    made = []

    def __new__(cls, email=None, password=None):
        bc = client(dict(cls.routes))
        bc._email, bc._password = email, password
        bc.close = lambda: None
        cls.made.append(bc)
        return bc


@pytest.fixture
def fake_bc(monkeypatch):
    FakeBigcase.made = []
    FakeBigcase.routes = {("post", "/auth/unified-signin"): signin()}
    monkeypatch.setattr(bigcase, "Bigcase", FakeBigcase)
    return FakeBigcase


def run_main(monkeypatch, *argv, stdin=""):
    monkeypatch.setattr(sys, "argv", ["bigcase"] + list(argv))
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return bigcase.main()


# ── keyring ──
def test_keyring_backend_refuses_fail_backend(monkeypatch):
    import keyring
    fail = type("FailKeyring", (), {"priority": 0})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: fail)
    with pytest.raises(bigcase.BigcaseError, match="키체인이 없습니다"):
        bigcase.keyring_backend()


def test_store_and_forget_credentials(kr):
    bigcase.store_credentials("u@example.com", "pw")
    assert kr.store[(bigcase.KEYRING_SERVICE, "u@example.com")] == "pw"
    assert bigcase.configured_email() == ("u@example.com", str(bigcase.config_file()))
    assert bigcase.stored_password("u@example.com")[0] == "pw"
    bigcase.write_private(bigcase.session_file(), {"accessToken": "x"})
    done = bigcase.forget_credentials()
    assert len(done) == 3 and kr.store == {} and not bigcase.config_file().exists()


def test_credentials_errors(kr):
    bc = client({})
    with pytest.raises(bigcase.BigcaseError, match="계정이 없습니다"):
        bc._credentials()
    bigcase.write_private(bigcase.config_file(), {"email": "u@example.com"})
    with pytest.raises(bigcase.BigcaseError, match="비밀번호가 키체인에 없습니다"):
        bc._credentials()


# ── setup ──
def test_setup_stores_only_after_login(kr, fake_bc, monkeypatch, capsys):
    assert run_main(monkeypatch, "setup", "--email", "u@example.com", "--password-stdin", stdin="pw\n") == 0
    assert kr.store[(bigcase.KEYRING_SERVICE, "u@example.com")] == "pw"
    assert json.loads(bigcase.session_file().read_text())["email"] == "u@example.com"
    out = capsys.readouterr().out
    assert "등록 완료" in out and "pw" not in out.replace("password", "")


def test_setup_login_failure_saves_nothing(kr, fake_bc, monkeypatch, capsys):
    fake_bc.routes = {("post", "/auth/unified-signin"): Resp(401, {"message": "bad"})}
    assert run_main(monkeypatch, "setup", "--email", "u@example.com", "--password-stdin", stdin="pw\n") == 1
    assert kr.store == {} and not bigcase.config_file().exists()
    assert "저장하지 않았습니다" in capsys.readouterr().out


def test_setup_already_registered_checks_token(kr, fake_bc, monkeypatch, capsys):
    bigcase.store_credentials("u@example.com", "pw")
    assert run_main(monkeypatch, "setup") == 0
    assert "이미 등록돼 있습니다" in capsys.readouterr().out
    assert fake_bc.made[0].http.calls[0][1] == "/auth/unified-signin"


def test_setup_empty_input_refused(kr, fake_bc, monkeypatch, capsys):
    assert run_main(monkeypatch, "setup", "--email", "u@example.com", "--password-stdin", stdin="\n") == 1
    assert "비었습니다" in capsys.readouterr().err


# ── login · token · status · forget ──
def test_login_cli_hides_tokens(kr, fake_bc, monkeypatch, capsys):
    bigcase.store_credentials("u@example.com", "pw")
    assert run_main(monkeypatch, "login") == 0
    out = capsys.readouterr().out
    assert "Token" not in out and json.loads(out)["email"] == "u@example.com"


def test_token_cli_reuses_valid_session(kr, fake_bc, monkeypatch, capsys):
    bigcase.store_credentials("u@example.com", "pw")
    at = jwt(9999999999)
    bigcase.write_private(bigcase.session_file(), {"email": "u@example.com", "accessToken": at, "refreshToken": "r"})
    fake_bc.routes = {}
    real = FakeBigcase.__new__

    def with_session(cls, email=None, password=None):
        bc = real(cls, email, password)
        bc.session = bigcase.read_json(bigcase.session_file())
        return bc

    monkeypatch.setattr(FakeBigcase, "__new__", with_session)
    assert run_main(monkeypatch, "token") == 0
    assert capsys.readouterr().out.strip() == at and fake_bc.made[0].http.calls == []


def test_status_reports_without_secrets(kr, monkeypatch, capsys):
    bigcase.store_credentials("u@example.com", "pw")
    bigcase.write_private(bigcase.session_file(), {"accessToken": jwt(9999999999)})
    assert run_main(monkeypatch, "status") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["password_saved"] is True and out["access_token_valid_for_sec"] > 0 and "pw" not in json.dumps(out)


def test_forget_cli(kr, monkeypatch, capsys):
    assert run_main(monkeypatch, "forget") == 0
    assert "지울 것이 없습니다" in capsys.readouterr().out


def test_cli_error_exit_1(kr, fake_bc, monkeypatch, capsys):
    assert run_main(monkeypatch, "login") == 1  # 등록된 계정 없음
    assert "등록된 빅케이스 계정이 없습니다" in capsys.readouterr().err


def test_cli_data_commands_print_summaries(kr, fake_bc, monkeypatch, capsys):
    bigcase.store_credentials("u@example.com", "pw")
    fake_bc.routes = {
        ("post", "/auth/unified-signin"): signin(),
        ("post", "/esapi/cases/search"): Resp(200, {"result_count": 1, "results": [
            {"case_id": 1, "case_number": "2014다26187", "court": "대법원", "case_expression": "대법원 2014. 7. 10. 선고 2014다26187 판결"}]}),
        ("post", "/decision-cases/searchList"): Resp(200, {"total_count": 1, "datas": [{"id": 7, "title": "<em>결정</em>", "date": "2020"}]}),
    }
    assert run_main(monkeypatch, "search", "2014다26187") == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["case_number"] == "2014다26187"
    assert run_main(monkeypatch, "decisions", "결정례", "결정") == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["id"] == 7
