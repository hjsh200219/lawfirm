#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["scrapling[fetchers]>=0.4.11,<0.5", "keyring>=25,<26"]
# ///
"""bigcase — 빅케이스(bigcase.ai) 로그인·판례 검색을 브라우저 없이 한다(Scrapling).

실행은 항상 `uv run <이 파일> <명령>` — 의존성은 위 inline 메타데이터로 uv 가 붙인다.

  setup [--email E] [--password-stdin] [--force]
                          자격증명 등록. 로그인 1회로 확인한 뒤에만 저장한다
  status                  등록 상태(값은 출력하지 않음 · 네트워크 안 씀)
  login                   저장 토큰을 무시하고 새로 로그인, 계정 요약 출력(토큰 제외)
  token                   유효한 accessToken 만 출력(다른 도구에 넘길 때)
  search <검색어> [--page N] [--raw]
                          판례 검색 — 총 건수와 페이지당 10건 요약(JSON)
  similar <법원> <사건번호> [--limit N]
                          유사 판례(최대 50건 중 상위 N)
  brief <사건 서술문 | -> [--page N] [--laws] [--raw]
                          서술문으로 비슷한 판례(또는 --laws 관련 법령) 찾기
  decisions <결정례|법령해석|행정심판> <검색어> [--page N]
  decision <결정례|법령해석|행정심판> <id>
                          결정례·법령해석·행정심판 검색 / 원문 PDF 주소
  case <법원> <사건번호> | case <판례 URL> [--raw]
                          판결문 전문(Markdown) — 판시사항·요지·주문·이유·심급
  get <경로> · post <경로> [--json '{...}']
                          /api/v1 아래 인증 요청(API 탐색용), JSON 출력 — https://bigcase.ai 밖 절대 주소는 거부
  forget                  키체인 항목·설정·토큰 파일 삭제

자격증명 보관(사용자마다 자기 빅케이스 계정):
- 이메일(비밀 아님) → $CASE_SEARCH_HOME/bigcase/config.json (기본 ~/.case-search, 0600)
- 비밀번호 → OS 키체인(keyring), 서비스명 "case-search-bigcase"
- 토큰 → $CASE_SEARCH_HOME/bigcase/session.json (0600)
- 환경변수 BIGCASE_ID / BIGCASE_PW(옛 이름 BICCASE_ID / BICCASE_PW)가 있으면 그쪽이 우선한다.
비밀번호는 명령행 인자로 받지 않는다. 입력 경로: 터미널 getpass · 터미널이 없으면 OS 입력 창
(macOS osascript · Windows Get-Credential) · 자동화면 --password-stdin.

API(2026-10-15 bigcase.ai Next.js 번들에서 발굴·실측, 상세 docs/case-search/bigcase-api.md):
- POST /api/v1/auth/unified-signin {email, password}
  → 200 {signInStatus, accountType, user, accessToken, refreshToken}.
  signInStatus 가 normal·not-exist-intg·integrated 일 때만 프론트가 로그인 성공으로 본다.
- POST /api/v1/auth/renew {refreshToken} → {accessToken, refreshToken}
- 인증은 Authorization: Bearer <accessToken>. 만료 60초 전이면 갱신, 갱신 실패면 재로그인, 401 이면 1회 재시도.
- POST /api/v1/esapi/cases/search {q, page, complete:"1"} → {result_count, results[10], keywords, ...}
- GET /api/v1/esapi/cases/match_view?case_number=&court= → 판례 상세(fulltext.reasoning 등 전문).
  비로그인이면 하급심은 restricted=true 로 이유가 잘린다.
- GET /esapi/cases/similar/search/v2?case_number=&court= → {results[50]} 유사 판례
- POST /esapi/brief/search/v2 {text, type:cases|laws, page, itemsperpage, index, model} → 서술문 검색
- POST /{decision-cases|regulation-interpretations|administrative-appeals}/searchList {query, page}
  → {total_count, datas[10]} · GET /<같은 경로>/view/<id> → {filepath(원문 PDF), ...}
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import getpass
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

API = "https://bigcase.ai/api/v1"
KEYRING_SERVICE = os.environ.get("BIGCASE_KEYRING_SERVICE", "case-search-bigcase")
OK_STATUS = {"normal", "not-exist-intg", "integrated"}
SEARCH_FIELDS = ("case_id", "case_expression", "case_number", "court", "case_type", "outcome", "level")
# 결정례·법령해석·행정심판 — 같은 형태의 searchList/view API (2026-10-15 실측)
DECISION_KINDS = {"결정례": "decision-cases", "법령해석": "regulation-interpretations", "행정심판": "administrative-appeals"}


class BigcaseError(RuntimeError):
    pass


# ---------- 파일 ----------

def home() -> Path:
    return Path(os.environ.get("CASE_SEARCH_HOME", Path.home() / ".case-search")) / "bigcase"


def config_file() -> Path:
    return home() / "config.json"


def session_file() -> Path:
    return home() / "session.json"


def write_private(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


# ---------- 자격증명 ----------

def _env(*names: str) -> tuple[str | None, str]:
    for n in names:
        if os.environ.get(n):
            return os.environ[n], f"환경변수 {n}"
    return None, ""


def keyring_backend():
    import keyring
    kr = keyring.get_keyring()
    name = f"{type(kr).__module__}.{type(kr).__name__}"
    if "fail" in name or "null" in name or getattr(kr, "priority", 1) <= 0:
        raise BigcaseError(f"이 컴퓨터에서 쓸 수 있는 키체인이 없습니다({name}). "
                           "환경변수 BIGCASE_ID/BIGCASE_PW 로 대신 지정하세요.")
    return kr


def configured_email() -> tuple[str | None, str]:
    email, src = _env("BIGCASE_ID", "BICCASE_ID")
    if email:
        return email.strip(), src
    email = read_json(config_file()).get("email")
    return (email, str(config_file())) if email else (None, "")


def stored_password(email: str) -> tuple[str | None, str]:
    pw, src = _env("BIGCASE_PW", "BICCASE_PW")
    if pw:
        return pw, src
    kr = keyring_backend()
    pw = kr.get_password(KEYRING_SERVICE, email)
    return (pw, f"키체인({type(kr).__name__}) 서비스 {KEYRING_SERVICE}") if pw else (None, "")


def store_credentials(email: str, password: str) -> None:
    keyring_backend().set_password(KEYRING_SERVICE, email, password)
    write_private(config_file(), {"email": email, "saved_at": int(time.time())})


def forget_credentials() -> list[str]:
    done = []
    email = read_json(config_file()).get("email")
    if email:
        with contextlib.suppress(Exception):  # 항목이 없거나 백엔드가 없으면 지울 것도 없다
            keyring_backend().delete_password(KEYRING_SERVICE, email)
            done.append(f"키체인 항목({KEYRING_SERVICE} / {email})")
    for p in (config_file(), session_file()):
        if p.exists():
            p.unlink()
            done.append(str(p))
    return done


# ---------- 입력 ----------

DIALOG_FAIL = "입력 창을 띄우지 못했습니다(%s) — Codex 샌드박스라면 권한 상승으로 다시 실행하거나, 자기 터미널에서 같은 명령을 직접 실행하십시오"


def _osascript_dialog(message: str, hidden: bool) -> str:
    esc = message.replace("\\", "\\\\").replace('"', '\\"')
    script = (f'display dialog "{esc}" default answer "" '
              f'{"with hidden answer " if hidden else ""}with title "BigCase" '
              'buttons {"취소", "확인"} default button "확인" cancel button "취소"\n'
              "text returned of result")
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600, check=False)
    if r.returncode != 0:
        if "-128" in (r.stderr or ""):  # 사람이 「취소」를 누름
            raise BigcaseError("입력을 취소했습니다.")
        raise BigcaseError(DIALOG_FAIL % ((r.stderr or "").strip()[:120] or f"osascript 종료 {r.returncode}"))
    return r.stdout.rstrip("\n")


def _windows_dialog(message: str, hidden: bool, username: str | None) -> str:
    msg = message.replace("'", "''")
    if hidden:
        user = (username or "").replace("'", "''")
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              f"$c=Get-Credential -UserName '{user}' -Message '{msg}';"
              "if(-not $c){exit 3};[Console]::Out.Write($c.GetNetworkCredential().Password)")
    else:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName Microsoft.VisualBasic;"
              f"$v=[Microsoft.VisualBasic.Interaction]::InputBox('{msg}','BigCase');"
              "if(-not $v){exit 3};[Console]::Out.Write($v)")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=600, check=False)
    if r.returncode == 3:  # 우리 스크립트의 취소 코드
        raise BigcaseError("입력을 취소했습니다.")
    if r.returncode != 0:
        raise BigcaseError(DIALOG_FAIL % ((r.stderr or b"").decode("utf-8", "replace").strip()[:120] or f"PowerShell 종료 {r.returncode}"))
    return r.stdout.decode("utf-8", "replace")


def ask(message: str, hidden: bool, username: str | None = None) -> str:
    """사람에게 값을 받는다. 터미널 → getpass/input, 아니면 OS 입력 창. 채팅·명령행 인자는 쓰지 않는다."""
    if sys.stdin.isatty():
        return getpass.getpass(f"{message}: ") if hidden else input(f"{message}: ")
    if sys.platform == "darwin":
        return _osascript_dialog(message, hidden)
    if os.name == "nt":
        return _windows_dialog(message, hidden, username)
    raise BigcaseError("입력 창을 띄울 수 없습니다. 터미널에서 직접 `uv run <플러그인>/skills/case-search/scripts/bigcase.py setup` 을 실행하세요.")


# ---------- 클라이언트 ----------

def _jwt_exp(token: str) -> int:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:  # noqa: BLE001 — 형식이 아니면 만료로 본다
        return 0


def _json(resp):
    try:
        return json.loads(resp.body)
    except Exception:  # noqa: BLE001
        return None


def _message(data) -> str:
    return (data.get("message") or "") if isinstance(data, dict) else ""


class Bigcase:
    def __init__(self, email: str | None = None, password: str | None = None):
        from scrapling.fetchers import FetcherSession
        logging.getLogger("scrapling").setLevel(logging.WARNING)
        self._email, self._password = email, password
        self._fs = FetcherSession(impersonate="chrome", stealthy_headers=False, timeout=15, retries=1)
        self.http = self._fs.__enter__()
        self.session = read_json(session_file())

    def close(self):
        self._fs.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _credentials(self) -> tuple[str, str]:
        if self._email and self._password:
            return self._email, self._password
        email, _ = configured_email()
        if not email:
            raise BigcaseError("등록된 빅케이스 계정이 없습니다. 먼저 `setup` 을 실행하세요.")
        pw, _ = stored_password(email)
        if not pw:
            raise BigcaseError(f"{email} 의 비밀번호가 키체인에 없습니다. `setup --force` 로 다시 등록하세요.")
        return email, pw

    def login(self, save: bool = True) -> dict:
        email, pw = self._credentials()
        r = self.http.post(f"{API}/auth/unified-signin", json={"email": email, "password": pw})
        data = _json(r)
        if r.status != 200 or not isinstance(data, dict):
            raise BigcaseError(f"로그인 실패 HTTP {r.status} {_message(data)}".strip())
        status = data.get("signInStatus")
        if status not in OK_STATUS or not data.get("accessToken"):
            raise BigcaseError(f"로그인 미완료 signInStatus={status} — 브라우저에서 계정 통합·확인을 먼저 끝내세요.")
        user = data.get("user") or {}
        self.session = {
            "email": email,
            "accessToken": data["accessToken"],
            "refreshToken": data["refreshToken"],
            "signInStatus": status,
            "accountType": data.get("accountType"),
            "role": user.get("role"),
            "hasMembership": user.get("hasMembership"),
            "loggedInAt": int(time.time()),
        }
        if save:
            write_private(session_file(), self.session)
        return self.session

    def renew(self) -> dict:
        rt = self.session.get("refreshToken")
        if not rt:
            raise BigcaseError("refreshToken 없음")
        r = self.http.post(f"{API}/auth/renew", json={"refreshToken": rt})
        data = _json(r)
        if r.status != 200 or not isinstance(data, dict) or not data.get("accessToken"):
            raise BigcaseError(f"토큰 갱신 실패 HTTP {r.status}")
        self.session.update(accessToken=data["accessToken"], refreshToken=data.get("refreshToken", rt))
        write_private(session_file(), self.session)
        return self.session

    def access_token(self) -> str:
        email, _ = configured_email()
        if self.session.get("email") not in (None, email):
            self.session = {}  # 다른 계정의 토큰은 쓰지 않는다
        at = self.session.get("accessToken")
        if at and _jwt_exp(at) > time.time() + 60:
            return at
        if self.session.get("refreshToken"):
            try:
                return self.renew()["accessToken"]
            except BigcaseError:
                pass
        return self.login()["accessToken"]

    def request(self, method: str, path: str, **kw):
        url = _api_url(path)
        fn = getattr(self.http, method.lower())
        extra = kw.pop("headers", {})
        for attempt in range(2):
            r = fn(url, headers={**extra, "Authorization": f"Bearer {self.access_token()}"}, **kw)
            if r.status == 401 and attempt == 0:
                self.session.pop("accessToken", None)  # 서버가 만료 판정 → 갱신 후 1회 재시도
                continue
            break
        data = _json(r)
        if r.status >= 400:
            raise BigcaseError(f"{method.upper()} {path} HTTP {r.status} {_message(data)}".strip())
        return data if data is not None else r.body.decode("utf-8", "replace")

    def get(self, path: str, **kw):
        return self.request("get", path, **kw)

    def post(self, path: str, **kw):
        return self.request("post", path, **kw)

    def search(self, q: str, page: int = 1) -> dict:
        return self.post("/esapi/cases/search", json={"q": q, "page": page, "complete": "1"})

    def case(self, court: str, case_number: str) -> dict:
        return self.get("/esapi/cases/match_view", params={"case_number": case_number, "court": court})

    def similar(self, court: str, case_number: str) -> dict:
        return self.get("/esapi/cases/similar/search/v2", params={"case_number": case_number, "court": court})

    def brief(self, text: str, page: int = 1, target: str = "cases") -> dict:
        """사건 서술문으로 비슷한 판례(target=cases)·법령(laws)을 찾는다(화면의 「문서로 검색」)."""
        return self.post("/esapi/brief/search/v2", json={
            "itemsperpage": 10, "page": page, "text": text,
            "index": "cases_small_avg", "model": "lawbert_small", "type": target})

    def decisions(self, kind: str, q: str, page: int = 1) -> dict:
        return self.post(f"/{DECISION_KINDS[kind]}/searchList", json={"query": q, "page": page})

    def decision(self, kind: str, doc_id: str) -> dict:
        return self.get(f"/{DECISION_KINDS[kind]}/view/{quote(str(doc_id), safe='')}")


def _api_url(path: str) -> str:
    """경로 → 빅케이스 API 주소. Bearer 토큰이 붙으므로 https://bigcase.ai 밖의 절대 주소는 거부한다."""
    u, api = urlparse(path.strip()), urlparse(API)
    if not u.scheme:
        return f"{API}/{path.lstrip('/')}"
    if (u.scheme.lower(), u.hostname, u.port, u.username) != (api.scheme, api.hostname, None, None):
        raise BigcaseError(f"빅케이스({api.scheme}://{api.netloc}) 밖 주소에는 인증 요청을 보내지 않습니다: {u.scheme}://{u.netloc}")
    return urlunparse(u._replace(scheme=api.scheme, netloc=api.netloc))  # 검사한 값 그대로 보낸다


def case_url(court: str | None, case_number: str | None) -> str | None:
    """판례 화면 /cases/<법원>/<사건번호> (2026-10-15 실측 200)."""
    if not court or not case_number:
        return None
    return f"https://bigcase.ai/cases/{quote(court)}/{quote(case_number)}"


def parse_case_ref(args: list[str]) -> tuple[str, str]:
    """`<법원> <사건번호>` 또는 판례 화면 URL 하나 → (법원, 사건번호)."""
    if len(args) == 1 and "/cases/" in args[0]:
        parts = [unquote(p) for p in urlparse(args[0]).path.split("/") if p]
        if len(parts) >= 3 and parts[-3] == "cases":
            return parts[-2], parts[-1]
    if len(args) >= 2:
        return " ".join(args[:-1]), args[-1]
    raise BigcaseError("법원과 사건번호를 주세요 — 예: case 대법원 99도4797 · case '수원지방법원 성남지원' 2022고합240 · case <판례 URL>")


def _plain(s) -> str:
    return re.sub(r"</?(?:law_cite|case_cite)[^>]*>", "", s or "").strip()


def _lines(v) -> str:
    if isinstance(v, list):
        return "\n".join(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in v)
    return v or ""


def case_markdown(d: dict) -> str:
    """match_view 응답 → 판결문 전문 Markdown."""
    ft = d.get("fulltext") or {}
    out = [f"# {d.get('case_expression') or d.get('case_number')}", "",
           f"- 결과: {d.get('outcome') or '-'} · 선고일: {d.get('judgment_date') or '-'}",
           f"- 화면: {case_url(d.get('court'), d.get('case_number'))}"]
    if d.get("pub_info"):
        out.append(f"- 공보: {d['pub_info']}")
    for title, key in (("판시사항", "holdings"), ("판결요지", "summary"), ("참조조문", "ref_laws"), ("참조판례", "ref_cases")):
        if d.get(key):
            text = _plain(d[key])
            if key.startswith("ref_"):
                text = re.sub(r"(?<=\S)\s*(\[\d+\])", r"\n\1", text)  # [1]…[2] 가 붙어 온다
            out += ["", f"## {title}", "", text]
    out += ["", "## 판결문", "", (ft.get("body_court") or "").replace("\n", " ")]
    out += [f"- {i.get('item')}: {(i.get('content') or '').replace(chr(10), ' / ')}" for i in ft.get("body_infos") or []]
    for title, key in (("주문", "disposition"), ("청구취지", "claim"), ("이유", "reasoning"), ("판사", "judges"), ("각주", "comments")):
        text = _lines(ft.get(key)).strip()
        if text:
            out += ["", f"### {title}", "", text]
    if d.get("attached_text"):
        out += ["", "## 첨부 본문", "", _lines(d["attached_text"]).strip()]
    if d.get("attached"):
        out += ["", "## 첨부(이미지, 받지 않음)", ""]
        out += [f"- {a.get('title')}: {len(a.get('files') or [])}장" for a in d["attached"]]
    if d.get("history_cases"):
        out += ["", "## 심급", ""] + [f"- {h.get('case_expression')}" for h in d["history_cases"]]
    return "\n".join(out).rstrip() + "\n"


def case_rows(results: list, fields=SEARCH_FIELDS) -> list[dict]:
    return [{**{k: r.get(k) for k in fields if k in r}, "url": case_url(r.get("court"), r.get("case_number"))}
            for r in results or []]


def _strip_em(s) -> str:
    return re.sub(r"</?(?:em|keyword)>", "", str(s or "")).strip()


def summarize_decisions(d: dict, kind: str, q: str, page: int) -> dict:
    return {"kind": kind, "query": q, "page": page, "total": d.get("total_count"),
            "results": [{"id": r.get("id"), "title": r.get("title"), "date": r.get("date"),
                         "organization": r.get("organizationName"),
                         "snippet": _strip_em(r.get("highlight")).strip("[]'\"")[:200]} for r in d.get("datas") or []]}


def summarize_search(d: dict, q: str, page: int) -> dict:
    return {
        "query": q, "page": page, "total": d.get("result_count"),
        "results": case_rows(d.get("results")),
    }


# ---------- 명령 ----------

def cmd_setup(a) -> int:
    keyring_backend()  # 저장할 곳이 없으면 비밀번호를 묻기 전에 멈춘다
    email, src = configured_email()
    if email and not a.force and stored_password(email)[0]:
        with Bigcase() as bc:
            bc.access_token()
        print(f"✓ 이미 등록돼 있습니다 · {email} ({src}) · 다시 넣으려면 setup --force")
        return 0
    email = (a.email or (None if a.force else email) or ask("빅케이스 이메일", hidden=False)).strip()
    pw = sys.stdin.readline().rstrip("\n") if a.password_stdin else ask(f"빅케이스 비밀번호 ({email})", hidden=True, username=email)
    if not email or not pw:
        raise BigcaseError("이메일·비밀번호가 비었습니다.")
    with Bigcase(email, pw) as bc:
        try:
            s = bc.login(save=False)
        except BigcaseError as e:
            print(f"✗ 저장하지 않았습니다 — {e}")
            return 1
        store_credentials(email, pw)
        write_private(session_file(), s)
    print(f"✓ 등록 완료 · {email} · 계정 유형 {s.get('accountType')} · 비밀번호는 키체인 서비스 {KEYRING_SERVICE}")
    return 0


def cmd_status(_a) -> int:
    email, src = configured_email()
    out = {"email": email, "email_source": src or None, "password_saved": False, "session_file": None}
    if email:
        try:
            pw, psrc = stored_password(email)
            out.update(password_saved=bool(pw), password_source=psrc or None)
        except BigcaseError as e:
            out["password_error"] = str(e)
    s = read_json(session_file())
    if s.get("accessToken"):
        out["session_file"] = str(session_file())
        out["access_token_valid_for_sec"] = max(0, _jwt_exp(s["accessToken"]) - int(time.time()))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # 한국어 Windows 콘솔(cp949)에서도 UTF-8 — casesearch.py 가 UTF-8 로 읽는다
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="bigcase", description="빅케이스(bigcase.ai) 로그인·판례 검색·전문 조회")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--email")
    p.add_argument("--password-stdin", action="store_true")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status")
    sub.add_parser("login")
    sub.add_parser("token")
    p = sub.add_parser("search")
    p.add_argument("q", nargs="+")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--raw", action="store_true", help="응답 원본 전체")
    p = sub.add_parser("similar")
    p.add_argument("ref", nargs="+", help="<법원> <사건번호> 또는 판례 화면 URL")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("brief")
    p.add_argument("text", nargs="+", help="사건 서술문, - 면 표준입력")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--laws", action="store_true", help="판례 대신 관련 법령")
    p.add_argument("--raw", action="store_true")
    p = sub.add_parser("decisions")
    p.add_argument("kind", choices=list(DECISION_KINDS))
    p.add_argument("q", nargs="+")
    p.add_argument("--page", type=int, default=1)
    p = sub.add_parser("decision")
    p.add_argument("kind", choices=list(DECISION_KINDS))
    p.add_argument("id")
    p = sub.add_parser("case")
    p.add_argument("ref", nargs="+", help="<법원> <사건번호> 또는 판례 화면 URL")
    p.add_argument("--raw", action="store_true", help="응답 원본 JSON")
    for name in ("get", "post"):
        p = sub.add_parser(name)
        p.add_argument("path")
        if name == "post":
            p.add_argument("--json", default="{}")
    sub.add_parser("forget")
    a = ap.parse_args()
    try:
        if a.cmd == "setup":
            return cmd_setup(a)
        if a.cmd == "status":
            return cmd_status(a)
        if a.cmd == "forget":
            done = forget_credentials()
            print("삭제: " + (", ".join(done) if done else "지울 것이 없습니다"))
            return 0
        with Bigcase() as bc:
            if a.cmd == "login":
                s = bc.login()
                print(json.dumps({k: v for k, v in s.items() if "Token" not in k}, ensure_ascii=False))
            elif a.cmd == "token":
                print(bc.access_token())
            elif a.cmd == "search":
                q = " ".join(a.q)
                d = bc.search(q, a.page)
                print(json.dumps(d if a.raw else summarize_search(d, q, a.page), ensure_ascii=False, indent=1))
            elif a.cmd == "similar":
                court, no = parse_case_ref(a.ref)
                rows = case_rows(bc.similar(court, no).get("results"), SEARCH_FIELDS + ("ranking",))
                print(json.dumps({"court": court, "case_number": no, "total": len(rows), "results": rows[:a.limit]},
                                 ensure_ascii=False, indent=1))
            elif a.cmd == "brief":
                text = sys.stdin.read().strip() if a.text == ["-"] else " ".join(a.text)
                d = bc.brief(text, a.page, "laws" if a.laws else "cases")
                out = d if a.raw or a.laws else {"page": a.page, "total": d.get("result_count"),
                                                  "results": case_rows(d.get("results"))}
                print(json.dumps(out, ensure_ascii=False, indent=1))
            elif a.cmd == "decisions":
                q = " ".join(a.q)
                print(json.dumps(summarize_decisions(bc.decisions(a.kind, q, a.page), a.kind, q, a.page),
                                 ensure_ascii=False, indent=1))
            elif a.cmd == "decision":
                d = bc.decision(a.kind, a.id)
                d = d.get("data", d) if isinstance(d, dict) else d
                print(json.dumps({k: d.get(k) for k in ("id", "title", "date", "dateName", "organizationName", "filepath")
                                  if k in d}, ensure_ascii=False, indent=1))
            elif a.cmd == "case":
                d = bc.case(*parse_case_ref(a.ref))
                if d.get("restricted"):
                    print("! restricted=true — 본문이 잘려 있습니다(로그인·멤버십 확인)", file=sys.stderr)
                print(json.dumps(d, ensure_ascii=False, indent=1) if a.raw else case_markdown(d), end="" if not a.raw else "\n")
            else:
                out = bc.get(a.path) if a.cmd == "get" else bc.post(a.path, json=json.loads(a.json))
                print(json.dumps(out, ensure_ascii=False, indent=1) if not isinstance(out, str) else out)
        return 0
    except BigcaseError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except PermissionError as e:
        if not os.environ.get("CODEX_SANDBOX"):
            raise
        print(f"✗ Codex 샌드박스가 홈 폴더 쓰기를 막았습니다({e.filename}). 권한 상승으로 같은 명령을 다시 실행하거나, "
              "config.toml 의 [sandbox_workspace_write] writable_roots 에 그 폴더를 넣으십시오.", file=sys.stderr)
        return 6


if __name__ == "__main__":
    sys.exit(main())
