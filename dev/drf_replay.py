"""개발 전용 법제처 재생 서버 — e2e 가 실제 법제처를 부르지 않게 `tests/recorded/` 녹화를 루프백에서 낸다.

녹화 밖 요청은 엔드포인트별 「결과 없음」 모양으로 답한다(형식 변경으로 읽히지 않게):
법령·판례 검색 `totalCnt` "0" · 조문 본문 빈 `조문단위` · 판례 본문 `PrecService` 없음.
받은 요청 수를 세고, 기록에는 키(OC)를 남기지 않는다.
"""
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECORDED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "recorded")
# (경로, target, ID, JO, query, nb) 정확 일치 → 녹화 파일
ROUTES = {
    ("lawSearch.do", "law", None, None, "민사소송법", None): "drf_law_search_민사소송법.json",
    ("lawSearch.do", "law", None, None, "소송촉진법", None): "drf_law_search_소송촉진법.json",
    ("lawService.do", "law", "001700", "028800", None, None): "drf_article_001700_028800.json",
    ("lawService.do", "law", "001700", "045100", None, None): "drf_article_001700_045100.json",
    ("lawService.do", "law", "003984", None, None, None): "drf_law_003984.json",
    ("lawService.do", "law", "003984", "000100", None, None): "drf_article_003984_000100.json",
    ("lawSearch.do", "prec", None, None, None, "2016다225353"): "drf_prec_nb_2016다225353.json",
    ("lawSearch.do", "prec", None, None, None, "2018다248626"): "drf_prec_nb_2018다248626.json",
    ("lawService.do", "prec", "184487", None, None, None): "drf_prec_184487.json",
}


def _route_key(path, q):
    return (path, q.get("target"), q.get("ID"), q.get("JO"), q.get("query"), q.get("nb"))


def _empty(path, q):
    if path == "lawService.do":
        return {"법령": {"조문": {"조문단위": []}}} if q.get("target") == "law" else {}
    return {"PrecSearch": {"totalCnt": "0"}} if q.get("target") == "prec" else {"LawSearch": {"totalCnt": "0"}}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path.rsplit("/", 1)[-1]
        f = ROUTES.get(_route_key(path, q))
        with self.server.lock:
            self.server.log.append({"path": path, "params": {k: v for k, v in q.items() if k != "OC"}, "recorded": f})
        body = open(os.path.join(RECORDED, f), encoding="utf-8").read() if f else json.dumps(_empty(path, q), ensure_ascii=False)
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Server:
    def start(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.lock, self.httpd.log = threading.Lock(), []
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/DRF" % self.httpd.server_port
        return self

    @property
    def count(self):
        return len(self.httpd.log)

    def dump(self, path):
        with self.httpd.lock:
            json.dump({"count": len(self.httpd.log), "requests": self.httpd.log}, open(path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
