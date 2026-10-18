"""의도대응표 6절 「확인됨」 행의 법제처 원문 위치(FR-24) — 확인됨에만, 키 값 없이."""
import json
import os

import _paths as P
import cite_check as C
import render_docx as R
from test_cite import FakeLaw, LAWS, LAW288, MISSING, C2014, P2016
from test_draft_render import rendered  # noqa: F401 — 픽스처 재사용

CASE = {"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"}


def test_confirmed_results_carry_source_url(tmp_path):
    law = C.Checker(str(tmp_path / "a"), client=FakeLaw(LAWS)).check(LAW288)
    assert law["source_url"] == "https://www.law.go.kr/법령/민사소송법/제288조"
    case = C.Checker(str(tmp_path / "b"), client=FakeLaw(P2016)).check(CASE)
    assert case["source_url"] == "https://www.law.go.kr/판례/(2016다225353)"
    miss = C.Checker(str(tmp_path / "c"), client=FakeLaw(MISSING)).check(C2014)
    assert "source_url" not in miss


def test_sub_article_url(tmp_path):
    t = [LAWS[0], ({"ID": "001700", "JO": "026602"}, {"법령": {"조문": {"조문단위": [
        {"조문여부": "조문", "조문내용": "제266조의2(소의 취하) …"}]}}})]
    r = C.Checker(str(tmp_path / "s"), client=FakeLaw(t)).check({"kind": "law", "law": "민사소송법", "article": 266, "sub": 2})
    assert r["source_url"].endswith("/민사소송법/제266조의2")


def test_table_shows_location_only_for_confirmed(rendered, tmp_path):  # noqa: F811
    import docx
    c, path, _ = rendered
    res = []
    for cite, table in ((dict(LAW288, text="민사소송법 제288조", pos=0), LAWS), (dict(CASE, text="2016다225353 판결", pos=10), P2016),
                        (dict(C2014, text="2014다26187 판결", pos=20), MISSING)):
        r = dict(cite)
        r.update(C.Checker(str(tmp_path / str(cite["pos"])), client=FakeLaw(table)).check(cite))
        res.append(r)
    P.atomic_write_json(os.path.join(os.path.dirname(path), "cite_results.json"), {"complete": True, "summary": {}, "results": res})
    out = R.render_all(path, "대여금")
    t = docx.Document(out["paths"]["table"])
    rows = [[cell.text for cell in row.cells] for tb in t.tables for row in tb.rows if len(row.cells) == 3 and row.cells[0].text in
            ("민사소송법 제288조", "2016다225353 판결", "2014다26187 판결")]  # 인용 대조 표(3칸)만 — 기본값 근거 표는 2칸
    assert len(rows) == 3
    by = {r[0]: r for r in rows}
    assert "https://www.law.go.kr/법령/민사소송법/제288조" in by["민사소송법 제288조"][2]
    assert "https://www.law.go.kr/판례/(2016다225353)" in by["2016다225353 판결"][2]
    assert "law.go.kr" not in by["2014다26187 판결"][2]
    assert all("OC=" not in x for r in rows for x in r)
