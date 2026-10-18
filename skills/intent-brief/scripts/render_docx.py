"""draft.md → 초안 .docx, design.json·대조 결과 → 내부_…_의도대응표.docx (+ 의뢰인 보고).

외부 패키지 없이 zipfile 로 OOXML 을 직접 쓴다. A4, 바탕 12pt(w:eastAsia 지정), 여백 25/20/25/25mm, 양쪽 정렬.
[확인 필요: …]·[법제처 …] 태그는 빨간 글자. 기존 파일은 덮어쓰지 않고 _vN 을 올린다.

사용:
  render_docx.py all <state.json> --name <사건약칭> [--out-dir <폴더>]
"""
import argparse
import datetime
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402
import check_draft as CD  # noqa: E402

FONT = "바탕"
RED = "C00000"
_TAG = re.compile(r"(\[확인 필요[^\]]*\]|\[법제처[^\]]*\])")
_BOLD = re.compile(r"\*\*(.+?)\*\*")

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>"""
W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles %s>
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:eastAsia="{f}" w:cs="{f}"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="ko-KR" w:eastAsia="ko-KR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="240" w:after="360"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:jc w:val="left"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="60"/><w:jc w:val="left"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>
<w:style w:type="table" w:styleId="Grid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tblBorders></w:tblPr></w:style>
</w:styles>""".replace("%s", W_NS).replace("{f}", FONT)
SETTINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings %s><w:defaultTabStop w:val="800"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>""" % W_NS
# A4 11906×16838 twip, 여백 위 25mm·오른쪽 20mm·아래 25mm·왼쪽 25mm (1mm ≈ 56.7twip)
SECT = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1134" w:bottom="1417" w:left="1417" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>')
TEXT_WIDTH = 11906 - 1134 - 1417


def _runs(text, bold=False):
    out = []
    for part in _TAG.split(text):
        if not part:
            continue
        red = bool(_TAG.fullmatch(part))
        for j, seg in enumerate(_BOLD.split(part)):
            if not seg:
                continue
            b = bold or (j % 2 == 1)
            rpr = ""
            if b or red:
                rpr = "<w:rPr>%s%s</w:rPr>" % ("<w:b/>" if b else "", '<w:color w:val="%s"/>' % RED if red else "")
            out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, escape(seg)))
    return "".join(out)


def para(text, style=None, bold=False, align=None):
    ppr = ""
    if style or align:
        ppr = "<w:pPr>%s%s</w:pPr>" % ('<w:pStyle w:val="%s"/>' % style if style else "",
                                       '<w:jc w:val="%s"/>' % align if align else "")
    return "<w:p>%s%s</w:p>" % (ppr, _runs(text, bold))


def table(rows, widths=None, header=True):
    ncol = max(len(r) for r in rows) if rows else 1
    widths = widths or [TEXT_WIDTH // ncol] * ncol
    x = ['<w:tbl><w:tblPr><w:tblStyle w:val="Grid"/><w:tblW w:w="%d" w:type="dxa"/><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>' % sum(widths)]
    x += ['<w:gridCol w:w="%d"/>' % w for w in widths]
    x.append("</w:tblGrid>")
    for ri, r in enumerate(rows):
        x.append("<w:tr>")
        for ci in range(ncol):
            cell = str(r[ci]) if ci < len(r) and r[ci] is not None else ""
            paras = "".join('<w:p><w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/><w:jc w:val="left"/></w:pPr>%s</w:p>'
                            % _runs(ln, bold=(header and ri == 0)) for ln in (cell.split("\n") or [""]))
            x.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>%s</w:tc>' % (widths[ci], paras or "<w:p/>"))
        x.append("</w:tr>")
    x.append("</w:tbl>")
    x.append("<w:p/>")  # 표 뒤에 빈 문단(Word 는 표로 끝나는 본문을 싫어한다)
    return "".join(x)


def write_docx(path, body_xml, title="intent-brief"):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>%s</dc:title><dc:creator>lawfirm</dc:creator>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created></cp:coreProperties>') % (escape(title), now)
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties '
           'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>lawfirm</Application></Properties>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s%s</w:body></w:document>'
           % (W_NS, body_xml, SECT))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/settings.xml", SETTINGS)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    if os.path.exists(path):
        os.remove(tmp)
        raise P.BriefError("이미 있는 파일은 덮어쓰지 않습니다: %s" % path)
    os.replace(tmp, path)
    return path


def _md_table(lines):
    rows = []
    for ln in lines:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return table(rows)


def draft_body(md):
    """draft.md → 본문 XML. 앵커는 지우고 제목만 남긴다."""
    _, body = CD.split_front(md.replace("\r\n", "\n"))
    out, buf = [], []

    def flush():
        if buf:
            out.append(_md_table(buf))
            buf.clear()

    for ln in body.split("\n"):
        if ln.strip().startswith("|"):
            buf.append(ln)
            continue
        flush()
        m = CD._SEC.match(ln)
        if m:
            title = m.group("title").strip()
            out.append(para(title, "Title") if m.group("id") == "sec.header" else para(title, "Heading1"))
            continue
        m = CD._ISS.match(ln)
        if m:
            out.append(para(m.group("title").strip(), "Heading2"))
            continue
        if not ln.strip():
            continue
        s = ln.strip()
        if s.startswith("# "):
            out.append(para(s[2:], "Title"))
        else:
            out.append(para(s))
    flush()
    return "".join(out)


def next_version(out_dir, prefix):
    v = 0
    for n in os.listdir(out_dir):
        m = re.match(re.escape(prefix) + r"_v(\d+)\.docx$", P.nfc(n))
        if m:
            v = max(v, int(m.group(1)))
    for n in os.listdir(out_dir):
        m = re.match(r"내부_" + re.escape(prefix) + r"_v(\d+)_", P.nfc(n))
        if m:
            v = max(v, int(m.group(1)))
    return v + 1


def _cite_cell(r):
    """원문·요지 칸 — 「확인됨」 행에만 법제처 원문 위치(공개 조회 화면)를 붙인다."""
    text = r.get("excerpt") or r.get("detail") or ""
    if r.get("status") == "confirmed" and r.get("source_url"):
        text = (text + "\n" if text else "") + "원문: " + r["source_url"]
    return text


def table_body(st, design, cite, draft_md):
    names = design["intent_names"]
    sec_intents = ", ".join("%s(%d)" % (k, i + 2) for i, k in enumerate(design["secondaries"]))
    o = [para("내부용 — 의도대응표 (제출하지 않음)", "Title")]
    o.append(para("의도: %s %s%s · 당사자 지위: %s · 서면: %s" % (
        design["primary"], names[design["primary"]], (" / 부: " + sec_intents) if sec_intents else "",
        design["side"], design["brief_type"])))
    if design.get("success_sentence"):
        o.append(para("성공 판정 문장: " + design["success_sentence"]))
    rv = design.get("intent_review")
    if rv:
        o.append(para("0. 의도 유불리 검토 (소송 전체 기준)", "Heading1"))
        o.append(table([["항목", "내용"],
                        ["판정", rv.get("verdict") or ""],
                        ["얻는 것", "\n".join(rv.get("gains") or []) or "없음"],
                        ["놓치는 것", "\n".join(rv.get("forgoes") or []) or "없음"],
                        ["대안", "\n".join(rv.get("alternatives") or []) or "없음"],
                        ["변호사 결정", "%s%s" % (rv.get("decision") or "", (" — " + rv["note"]) if rv.get("note") else "")]],
                       [1800, 7555]))
    o.append(para("1. 파라미터와 값 출처", "Heading1"))
    o.append(table([["파라미터", "값", "출처"],
                    ["강도", "%s — %s" % (design["strength"]["level"], design["strength"]["desc"]), design["strength"]["source"]],
                    ["어조", design["tone"]["value"], design["tone"]["source"]],
                    ["분량", "%s(%d–%d자)" % (design["length"]["label"], design["length"]["chars"][0], design["length"]["chars"][1]), design["length"]["source"]],
                    ["증거 전략", design["evidence_strategy"]["value"], design["evidence_strategy"]["source"]],
                    ["결론", design["conclusion"]["text"], design["conclusion"]["source"]]], [1600, 5555, 2200]))
    o.append(para("2. 섹션 구성", "Heading1"))
    o.append(table([["섹션 ID", "섹션", "출처"]] + [[s["id"], s["title"], s["source"]] for s in design["sections"]], [2600, 4200, 2555]))
    if design["omitted"]:
        o.append(para("생략한 섹션과 사유", "Heading2"))
        o.append(table([["섹션", "의도", "사유"]] + [[x["id"], x["by"], x["reason"]] for x in design["omitted"]], [2600, 1600, 5155]))
    o.append(para("3. 쟁점별 태도", "Heading1"))
    rows = [["쟁점", "태도", "범위·금액", "증거", "출처"]]
    for it in design["issues"]:
        ev = it.get("evidence") or {}
        rows.append(["%d. %s" % (it["id"], it.get("title", "")), it["stance"],
                     P.fmt_won(it["amount"]) if it.get("amount") is not None else (it.get("scope") or ""),
                     "%s %s" % (ev.get("mode") or "", ", ".join(ev.get("items") or ev.get("targets") or [])), it["stance_source"]])
    o.append(table(rows, [3000, 1300, 1600, 2155, 1300]))
    adm = [it for it in design["issues"] if it["stance"] in ("인정", "일부 인정")]
    o.append(para("4. 인정 목록(재판상 자백 위치 추적 — 민사소송법 제288조)", "Heading1"))
    o.append(table([["쟁점", "인정 범위"]] + [["%d. %s" % (it["id"], it.get("title", "")),
                                                 P.fmt_won(it["amount"]) if it.get("amount") is not None else (it.get("scope") or "[확인 필요: 인정액]")]
                                                for it in adm] if adm else [["쟁점", "인정 범위"], ["없음", ""]], [5000, 4355]))
    if design["conflicts"]:
        o.append(para("5. 의도 조합 해소", "Heading1"))
        o.append(table([["조합", "규칙", "설명"]] + [[c["pair"], c["rule"], c["note"]] for c in design["conflicts"]], [1400, 2000, 5955]))
    o.append(para("6. 법적 근거와 인용 대조", "Heading1"))
    o.append(para("「확인됨」은 그 조문·판례가 법제처 원문에 존재한다는 뜻이며 인용의 적합성은 보증하지 않습니다. 「빅케이스 확인」은 법제처에 원문이 없어 빅케이스에서 같은 사건번호를 찾았다는 뜻입니다. 「해석」은 원문 대조 대상이 아닙니다."))
    o.append(table([["기본값 근거", "종류"]] + [[b["ref"], b["kind"]] for b in design["legal_basis"]], [7000, 2355]))
    if cite:
        lab = {"confirmed": "확인됨", "unverified": "미확인", "outage": "장애", "key_invalid": "키 오류",
               "external": "빅케이스 확인(법제처 원문 없음)",
               "format_changed": "응답 형식 변경", "pending": "대조 중단"}
        o.append(table([["초안 인용", "상태", "원문·요지(존재 확인 — 적합성 미보증)"]] +
                       [[r["text"], lab.get(r["status"], r["status"]), _cite_cell(r)] for r in cite["results"]],
                       [2600, 1300, 5455]))
    tags = sorted(set(re.findall(r"\[확인 필요[^\]]*\]|\[법제처[^\]]*\]", draft_md)))
    o.append(para("7. [확인 필요] 목록", "Heading1"))
    o.append(table([["태그", "건수"]] + [[t, str(draft_md.count(t))] for t in tags] if tags else [["태그", "건수"], ["없음", "0"]], [7355, 2000]))
    o.append(para("8. 할 일", "Heading1"))
    o.append(table([["할 일"]] + [[t["text"]] for t in design["todo"]] if design["todo"] else [["할 일"], ["없음"]], [9355]))
    comp = st.get("compliance") or {}
    o.append(para("9. 설계 준수율", "Heading1"))
    o.append(table([["회차", "준수율", "불일치"]] + [[k, str((comp.get(k) or {}).get("rate")), ", ".join((comp.get(k) or {}).get("failures") or [])]
                                               for k in ("first", "final")], [1600, 1600, 6155]))
    return "".join(o)


def render_all(state_path, name, out_dir=None):
    st = P.load_json(state_path)
    if not st.get("design_path") or not st.get("draft_path"):
        raise P.BriefError("design.json 과 draft.md 가 먼저 있어야 합니다")
    design = P.load_json(st["design_path"])
    draft_md = P.read_text(st["draft_path"])
    out_dir = out_dir or st["case_dir"]
    yymmdd = P.today().strftime("%y%m%d")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    prefix = "%s_%s_%s" % (yymmdd, safe, st["brief_type"])
    v = next_version(out_dir, prefix)
    paths = {"draft": write_docx(os.path.join(out_dir, "%s_v%d.docx" % (prefix, v)), draft_body(draft_md), prefix)}
    cite_path = os.path.join(os.path.dirname(state_path), "cite_results.json")
    cite = P.load_json(cite_path) if os.path.exists(cite_path) else None
    paths["table"] = write_docx(os.path.join(out_dir, "내부_%s_v%d_의도대응표.docx" % (prefix, v)),
                                table_body(st, design, cite, draft_md), "의도대응표")
    report = os.path.join(os.path.dirname(state_path), "client_report.md")
    if design.get("client_report") and os.path.exists(report):
        rep = P.read_text(report)
        body = [para("내부용 — 의뢰인 보고 요약 (제출하지 않음)", "Title")] + [para(ln.strip()) for ln in rep.splitlines() if ln.strip()]
        paths["client_report"] = write_docx(os.path.join(out_dir, "내부_%s_v%d_의뢰인보고.docx" % (prefix, v)), "".join(body), "의뢰인보고")
    import state as S
    st = P.load_json(state_path)
    st["outputs"].append({"version": v, **paths})
    if st["status"] == "designed":
        S.set_status(st, "drafted")
    S.save(state_path, st)
    return {"version": v, "paths": paths}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("all"); s.add_argument("state"); s.add_argument("--name", required=True); s.add_argument("--out-dir")
    a = ap.parse_args(argv)
    try:
        return P.emit(dict(ok=True, **render_all(a.state, a.name, a.out_dir)))
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
