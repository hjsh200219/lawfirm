#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["scrapling[fetchers]>=0.4.11,<0.5"]
# ///
"""URL 하나에서 API 후보를 찾는다 — 실행: uv run discover.py <URL> [--out 폴더] [--cdp http://localhost:9222 --scroll 3]

1) robots.txt 가 일반(*) 또는 AI 에이전트(Claude-User) 접근을 막으면 멈춘다. 2) 페이지와 같은 호스트의 스크립트(최대 MAX_SCRIPTS개, 요청 간격 1초)를 받아
extract.py 로 정적 분석한다. 3) --cdp 를 주면 이미 떠 있는 Chrome(원격 디버깅 포트)에 붙어 실제 XHR·fetch 요청을 잡는다
(로그인·검색을 사람이 그 창에서 해 두면 정확해진다). 응답 본문은 저장하지 않고 JSON 키 구조만 남긴다(개인정보 보호).
Authorization·Cookie 헤더 값과 쿼리 인자 값은 기록하지 않는다(이름만). 저장하는 주소에서도 계정 정보·쿼리·fragment 를 뺀다.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract  # noqa: E402

MAX_SCRIPTS = 40
DELAY = 1.0
UA = "Mozilla/5.0"
SECRET_HEADERS = {"authorization", "cookie", "x-csrf-token", "x-xsrf-token", "x-api-key"}


AGENTS = ("Claude-User", "*")  # 사람 요청으로 Claude 가 부르는 도구 — AI 에이전트용 규칙과 일반 규칙을 모두 지킨다


def robots_decision(text: str, url: str) -> tuple[bool, list[str]]:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    blocked = [a for a in AGENTS if not rp.can_fetch(UA if a == "*" else a, url)]
    return not blocked, blocked


def robots_allows(url: str) -> tuple[bool, str, list[str]]:
    u = urlparse(url)
    robots = f"{u.scheme}://{u.netloc}/robots.txt"
    req = urllib.request.Request(robots, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read(512 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"{robots} 접근 거부(HTTP {e.code}) — 자동 접근을 막는 사이트로 본다", ["*"]
        if e.code >= 500:
            return False, f"{robots} 서버 오류(HTTP {e.code}) — 규칙을 알 수 없어 멈춘다. 나중에 다시 시도", ["*"]
        return True, f"{robots} 없음(HTTP {e.code})", []
    except Exception as e:  # noqa: BLE001 — 규칙을 모르는 채 진행하지 않는다(Claude-User 차단을 건너뛰게 됨)
        return False, f"robots.txt 읽기 실패({type(e).__name__}) — 규칙을 알 수 없어 멈춘다. 다시 시도", ["*"]
    ok, blocked = robots_decision(text, url)
    return ok, robots, blocked


def query_names(query: str) -> list[str]:
    """쿼리 값(토큰·검색어일 수 있다)은 버리고 인자 이름만."""
    return sorted({k for k, _ in parse_qsl(query, keep_blank_values=True)})


def shape(data, depth=0):
    """값 대신 구조만 — {키: 타입} · [첫 원소 구조]."""
    if depth > 3:
        return "…"
    if isinstance(data, dict):
        return {k: shape(v, depth + 1) for k, v in list(data.items())[:30]}
    if isinstance(data, list):
        return [shape(data[0], depth + 1)] if data else []
    return type(data).__name__


def static_scan(url: str) -> dict:
    from scrapling.fetchers import Fetcher
    logging.getLogger("scrapling").setLevel(logging.WARNING)
    page = Fetcher.get(url, impersonate="chrome", timeout=20)
    html = page.body.decode("utf-8", "replace")
    texts, fetched = [html], []
    for src in extract.script_urls(html, url)[:MAX_SCRIPTS]:
        time.sleep(DELAY)
        try:
            r = Fetcher.get(src, impersonate="chrome", timeout=20)
        except Exception as e:  # noqa: BLE001
            fetched.append({"url": extract.clean_url(src), "error": type(e).__name__})
            continue
        fetched.append({"url": extract.clean_url(src), "status": r.status, "bytes": len(r.body)})
        if r.status == 200:
            texts.append(r.body.decode("utf-8", "replace"))
    out = extract.find_endpoints("\n".join(texts), url)
    out.update(status=page.status, scripts=fetched, inline_state=extract.inline_state(html), forms=extract.form_actions(html, url))
    return out


def cdp_capture(url: str, cdp: str, scroll: int) -> list[dict]:
    from playwright.sync_api import sync_playwright
    seen = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()  # 실제 Chrome 은 새 context 를 막는 경우가 있다
        page = ctx.new_page()

        def on_response(resp):
            req = resp.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            item = {"method": req.method, "url": extract.clean_url(req.url), "same_host": extract._same_host(req.url, url),
                    "query_params": query_names(urlparse(req.url).query),
                    "status": resp.status, "content_type": resp.headers.get("content-type", ""),
                    "request_headers": sorted(h for h in req.headers if h.lower() not in SECRET_HEADERS),
                    "has_auth_header": any(h.lower() in SECRET_HEADERS for h in req.headers)}
            if req.post_data:
                try:
                    item["body_shape"] = shape(json.loads(req.post_data))
                except ValueError:
                    item["body_shape"] = "form/text"
            if "json" in item["content_type"]:
                try:
                    item["response_shape"] = shape(resp.json())
                except Exception as e:  # noqa: BLE001 — 본문을 못 읽은 응답(리다이렉트·잘림)도 요청 목록에는 남긴다
                    item["response_shape"] = f"읽기 실패({type(e).__name__})"
            seen.append(item)

        page.on("response", on_response)
        page.goto(url, wait_until="networkidle", timeout=45000)
        for _ in range(scroll):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1500)
        page.close()
    seen.sort(key=lambda x: not x["same_host"])  # 대상 사이트 요청 먼저, 분석·광고 등 제3자 요청은 뒤
    return seen


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="URL 에서 API 후보 발굴")
    ap.add_argument("url")
    ap.add_argument("--out", default=".")
    ap.add_argument("--cdp", help="원격 디버깅 Chrome 주소(예: http://localhost:9222)")
    ap.add_argument("--scroll", type=int, default=3)
    a = ap.parse_args()
    if urlparse(a.url).scheme not in ("http", "https"):
        print(json.dumps({"ok": False, "error": "http(s) 주소가 필요합니다"}, ensure_ascii=False))
        return 3
    allowed, robots, blocked = robots_allows(a.url)
    if not allowed:
        print(json.dumps({"ok": False, "error": "robots_disallow", "robots": robots, "blocked_for": blocked,
                          "message": "robots.txt 가 이 주소의 자동 접근을 막습니다(%s). 멈춥니다." % ", ".join(blocked)},
                         ensure_ascii=False))
        return 4
    result = {"ok": True, "url": extract.clean_url(a.url), "robots": robots, "static": static_scan(a.url)}
    if a.cdp:
        try:
            result["network"] = cdp_capture(a.url, a.cdp, a.scroll)
        except Exception as e:  # noqa: BLE001 — 연결 실패·networkidle 시간 초과도 JSON 으로 알린다
            result["network"], result["network_error"] = [], f"{type(e).__name__}: {str(e)[:200]}"
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "endpoints.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    st = result["static"]
    print(json.dumps({"ok": True, "saved": path, "endpoints": [e["path"] for e in st["endpoints"][:15]],
                      "auth_candidates": st["auth_candidates"], "inline_state": st["inline_state"],
                      "network_requests": len(result.get("network", [])),
                      "network_same_host": sum(1 for x in result.get("network", []) if x["same_host"])}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
