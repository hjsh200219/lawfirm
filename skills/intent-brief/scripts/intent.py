"""의도 선택 검증과 해석(resolve) → design.json.

(주 의도, 당사자 지위) 기본값 → 부 의도 섹션(근거 조건·일반 축소 규칙) → 결론부 합성(자리표시자) →
충돌표 → 설계 확인 덮어쓰기 → design.json. 어떤 의도도 거부·경고하지 않는다(정보가 모자라면 질문만 요청).

사용:
  intent.py resolve <state.json> [--write]   설계안 계산(--write 면 작업 폴더에 design.json 고정)
  intent.py stats [<작업 폴더 루트>]          의도·덮어쓰기 빈도(허용 필드 7개) + 복사용 블록 — 네트워크 없음
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402


class NeedInput(Exception):
    """해석에 답이 더 필요하다(conflict 라운드 등)."""

    def __init__(self, needs):
        super().__init__("; ".join(n["key"] for n in needs))
        self.needs = needs


def validate_selection(intent, params):
    prim = intent.get("primary")
    secs = intent.get("secondaries") or []
    ints = params["intents"]
    if not prim:
        raise P.BriefError("주 의도가 선택되지 않았습니다 — 주 의도 없이 초안을 쓰지 않습니다")
    if prim not in ints:
        raise P.BriefError("주 의도 %r 는 목록에 없습니다" % prim)
    if not ints[prim]["primary_allowed"]:
        raise P.BriefError("%s(%s) 는 부 의도로만 고를 수 있습니다" % (prim, ints[prim]["name"]))
    if len(secs) > 2:
        raise P.BriefError("부 의도는 최대 2개입니다")
    if len(set(secs)) != len(secs) or prim in secs:
        raise P.BriefError("의도가 중복됐습니다")
    for s in secs:
        if s not in ints:
            raise P.BriefError("부 의도 %r 는 목록에 없습니다" % s)


def _admitted(st):
    return [i for i in st["issues"] if i.get("stance") in ("인정", "일부 인정")]


def basis_ok(name, st):
    f = st["flags"]
    if name == "always":
        return True
    if name == "admitted_issue":
        return bool(_admitted(st))
    if name == "settle_will":
        return bool(f.get("settle_will")) or bool(st["intent"].get("concession"))
    if name == "doc_targets":
        return bool(f.get("doc_targets")) or any((i.get("evidence") or {}).get("mode") == "제출 요구" for i in st["issues"])
    if name == "alt_cause":
        return bool(f.get("alt_cause"))
    if name == "reduction_reasons":
        return bool(f.get("reduction_reasons"))
    if name == "procedural_issue":
        return bool(f.get("procedural_issue"))
    raise P.BriefError("알 수 없는 근거 조건: %s" % name)


def section_basis(sec, side, params):
    sb = params["section_basis"]
    return sb.get("%s@%s" % (sec, side)) or sb.get(sec) or "always"


def relief_plaintiff(st, params):
    """원고 쪽 인용 문구(§2.2-5 표). 반환 (문구, 메모)."""
    R = params["relief"]
    claim = st.get("claim_amount")
    interest = R["interest"] if st.get("claim_interest") else ""
    adm = _admitted(st)
    if not adm:
        return R["plaintiff_full"].format(claim=P.fmt_won(claim) if claim else params["tag"]["claim_amount_missing"], interest=interest), "full"
    if any(i.get("amount") is None for i in adm):
        return R["plaintiff_deduct_scope"].format(interest=interest), "scope"
    total = sum(i["amount"] for i in adm)
    if claim is None:
        return R["plaintiff_deduct_noclaim"].format(admitted=P.fmt_won(total), interest=interest), "noclaim"
    remaining = claim - total
    if remaining <= 0:
        raise NeedInput([{"key": "design.amounts", "round_type": "design_confirm",
                          "why": "인정액 합계(%s)가 청구금액(%s) 이상입니다 — 인정액이나 청구금액을 고쳐 주십시오"
                                 % (P.fmt_won(total), P.fmt_won(claim))}])
    return R["plaintiff_deduct"].format(admitted=P.fmt_won(total), remaining=P.fmt_won(remaining), interest=interest), "deduct"


def _remaining_text(st, params):
    claim = st.get("claim_amount")
    adm = _admitted(st)
    if claim is None or any(i.get("amount") is None for i in adm):
        return params["tag"]["claim_amount_missing"] if claim is None else params["tag"]["admitted_amount_missing"]
    return P.fmt_won(claim - sum(i["amount"] for i in adm))


def _override_map(st):
    m = {}
    for o in st.get("overrides", []):
        m[o["cell"]] = o["value"]
    return m


def resolve(st, params=None, phrases=None):
    params = params or P.load_params()
    phrases = phrases or P.load_phrases()
    validate_selection(st["intent"], params)
    side, brief = st.get("side"), st["brief_type"]
    if side not in params["sides"]:
        raise NeedInput([{"key": "round0.side", "round_type": "round0", "why": "당사자 지위(원고·피고)가 정해지지 않았습니다"}])
    bt = params["brief_types"][brief]
    if side not in bt["sides"]:
        raise P.BriefError("%s 는 %s 쪽 서면입니다" % (brief, "·".join(bt["sides"])))
    prim = st["intent"]["primary"]
    secs = list(st["intent"].get("secondaries") or [])
    base = params["defaults"]["%s|%s" % (prim, side)]
    ov = _override_map(st)
    needs, conflicts, omitted, addenda, todo = [], [], [], [], []
    sources = {}
    sections = collections.OrderedDict()

    for s in bt["fixed_sections"]:
        sections[s] = "fixed"
    for s in base["must_include"]:
        sections.setdefault(s, "primary")
    omit = set(base["must_omit"])
    strength = base["strength"]
    sources["strength"] = "default"

    for sec in secs:
        if sec == "C":
            continue
        pair = "%s+%s" % (prim, sec)
        rule = params["conflicts"].get(pair)
        both_goal = params["intents"][prim]["layer"] == "goal" and params["intents"][sec]["layer"] == "goal"
        if rule:
            conflicts.append({"pair": pair, "rule": rule["rule"], "note": rule["note"]})
            if rule["rule"] == "stance_by_issue" and any(not i.get("stance") for i in st["issues"]):
                needs.append({"key": "conflict.%s" % pair, "round_type": "conflict",
                              "why": "전부 다툼과 일부 인정을 섞으려면 쟁점마다 태도가 정해져야 합니다"})
            if rule["rule"] == "core_strength":
                strength = rule["set"]["strength"]
                sources["strength"] = "conflict_rule"
            if rule["rule"] == "ask" and st["conflict_answers"].get(rule["ask_key"]) is None \
                    and st["flags"].get(rule["ask_key"]) is None:
                needs.append({"key": "conflict.%s.%s" % (pair, rule["ask_key"]), "round_type": "conflict", "why": rule["note"]})
        elif both_goal:
            needs.append({"key": "conflict.%s" % pair, "round_type": "conflict", "why": "충돌표에 없는 목표 조합입니다"})
        sd = params["defaults"]["%s|%s" % (sec, side)]
        for s in sd["must_include"]:
            if s in sections:
                continue
            if s in omit:
                sub = params["omit_substitutes"].get(s)
                if sub and sub not in omit and sub not in sections:
                    sections[sub] = "secondary:%s(대체)" % sec
                else:
                    omitted.append({"id": s, "by": sec, "reason": "주 의도 %s 의 생략 섹션" % prim})
                continue
            b = section_basis(s, side, params)
            if basis_ok(b, st):
                sections[s] = "secondary:%s" % sec
            else:
                omitted.append({"id": s, "by": sec, "reason": "근거 없음(%s)" % b})
        ad = params["addenda"].get("%s|%s" % (sec, side))
        if ad:
            if basis_ok(ad["basis"], st):
                addenda.append({"by": sec, "text": ad["text"]})
            else:
                omitted.append({"id": "addendum", "by": sec, "reason": "근거 없음(%s)" % ad["basis"]})

    # 원고가 청구원인이 다른 예비적 청구를 지정 — 청구 변경이므로 할 일을 남긴다
    if side == "원고" and st["flags"].get("alt_cause"):
        if "sec.alt_claim" in omit:
            omitted.append({"id": "sec.alt_claim", "by": "alt_cause", "reason": "주 의도 %s 의 생략 섹션" % prim})
        else:
            sections.setdefault("sec.alt_claim", "alt_cause")
        todo.append({"key": "claim_change_required",
                     "text": phrases["tag"]["claim_change_required"].format(alt_cause=st["flags"]["alt_cause"])})

    if needs:
        raise NeedInput(needs)

    # 결론부 — 자리표시자만 치환한다
    relief_p, relief_kind = (relief_plaintiff(st, params) if side == "원고" else (None, None))
    tmpl = base["conclusion_template"]
    conclusion = tmpl.replace("{relief_plaintiff}", relief_p or "").replace("{relief_defendant}", params["relief"]["defendant"])
    if side == "원고" and _admitted(st):
        todo.insert(0, {"key": "claim_reduction_optional",
                        "text": phrases["tag"]["claim_reduction_optional"].format(remaining=_remaining_text(st, params))})

    # 의도 유불리 검토에서 「놓치는 것」으로 본 항목 — 변호사가 진행을 골랐어도 할 일로 남긴다
    review = st.get("intent_review")
    if review and P.review_current(st):
        for item in review.get("forgoes") or []:
            todo.append({"key": "intent_review_forgone", "text": phrases["tag"]["intent_review_forgone"].format(item=item)})

    # 쟁점 태도 — 답이 없으면 기본값
    issues = []
    for it in st["issues"]:
        d = dict(it)
        if d.get("stance"):
            d["stance_source"] = "answer"
        else:
            d["stance"] = base["stance_default"]
            d["stance_source"] = "default"
        issues.append(d)

    design = {
        "params_version": params["params_version"],
        "brief_type": brief, "side": side,
        "primary": prim, "secondaries": secs,
        "intent_names": {k: params["intents"][k]["name"] for k in [prim] + secs},
        "success_sentence": st["intent"].get("success_sentence"),
        "concession": st["intent"].get("concession"),
        "claim_amount": st.get("claim_amount"),
        "claim_interest": bool(st.get("claim_interest")),
        "strength": {"level": strength, "desc": params["strength_levels"].get(strength, ""), "source": sources["strength"]},
        "tone": {"value": base["tone"], "source": "default"},
        "length": {"label": base["length"], "chars": base["length_chars"], "source": "default"},
        "evidence_strategy": {"value": base["evidence_strategy"], "source": "default"},
        "issues": issues,
        "omitted": omitted,
        "addenda": addenda,
        "todo": todo,
        "conflicts": conflicts,
        "legal_basis": _legal_basis(prim, secs, side, relief_kind, params),
        "client_report": "C" in secs,
        "relief_kind": relief_kind,
        "withheld_evidence": st["conflict_answers"].get("withheld_evidence") or st["flags"].get("withheld_evidence"),
        "instance": st.get("instance"),
        "intent_review": review,
    }

    # 설계 확인 덮어쓰기 — 바꾼 값은 source: override
    applied = []
    for cell, val in ov.items():
        if cell == "strength":
            design["strength"] = {"level": val, "desc": params["strength_levels"].get(val, ""), "source": "override"}
        elif cell == "tone":
            design["tone"] = {"value": val, "source": "override"}
        elif cell == "length":
            design["length"] = {"label": val["label"], "chars": val["chars"], "source": "override"} if isinstance(val, dict) \
                else {"label": val, "chars": design["length"]["chars"], "source": "override"}
        elif cell == "evidence_strategy":
            design["evidence_strategy"] = {"value": val, "source": "override"}
        elif cell == "sections.add":
            for s in val:
                if s not in params["sections"]:
                    raise P.BriefError("섹션 ID %r 는 어휘에 없습니다" % s)
                sections[s] = "override"
        elif cell == "sections.remove":
            for s in val:
                if s in bt["fixed_sections"]:
                    raise P.BriefError("%s 는 고정 섹션이라 뺄 수 없습니다" % s)
                sections.pop(s, None)
                omitted.append({"id": s, "by": "override", "reason": "변호사가 뺌"})
        elif cell == "addenda":
            if val == "삭제":
                design["addenda"] = []
        elif cell == "todo":
            if val == "삭제":
                design["todo"] = []
        elif cell == "conclusion":
            conclusion = val
        else:
            raise P.BriefError("덮어쓸 수 없는 칸: %s" % cell)
        applied.append({"cell": cell, "value": val, "source": "override"})

    order = params["section_order"]
    design["sections"] = [{"id": s, "title": params["sections"][s], "source": sections[s]}
                          for s in sorted(sections, key=lambda x: order.index(x))]
    text = conclusion + "".join(" " + a["text"] for a in design["addenda"])
    design["conclusion"] = {"text": text, "template": tmpl, "source": "override" if "conclusion" in ov else "default"}
    design["overrides"] = applied
    return design


def _legal_basis(prim, secs, side, relief_kind, params):
    """주 의도 + 부 의도 근거, 공제 결론이면 (M, 원고) 근거까지 — 중복 제거."""
    keys = [prim] + [s for s in secs if s != "C"]
    if relief_kind in ("deduct", "scope", "noclaim"):
        keys.append("M")
    out, seen = [], set()
    for k in keys:
        for b in params["defaults"]["%s|%s" % (k, side)]["legal_basis"]:
            if b["ref"] not in seen:
                seen.add(b["ref"])
                out.append(dict(b, by=k))
    return out


def write_design(state_path, st, design):
    wd = os.path.dirname(state_path)
    path = os.path.join(wd, "%s_design.json" % st["brief_type"])
    P.atomic_write_json(path, design)
    return path


# 덮어쓰기 분기가 받는 칸 이름 — 통계 키 성분은 이 목록 안만(목록 밖은 other)
OVERRIDE_CELLS = ("strength", "tone", "length", "evidence_strategy", "sections.add", "sections.remove", "addenda", "todo", "conclusion")
STATS_FIELDS = ("cases", "intent_side", "override_cells", "avg_rounds", "fast_path_ratio", "plugin_version", "period")


def _plugin_version():
    try:
        return P.load_json(os.path.join(P.PLUGIN_ROOT, ".claude-plugin", "plugin.json")).get("version")
    except (OSError, ValueError):
        return None


def stats(root):
    """사용 통계 요약 — 허용 필드 7개만. 키 성분은 닫힌 어휘(의도 ID·측·덮어쓰기 칸), 목록 밖 값은 other.
    사건 폴더 이름·자유 텍스트는 내지 않는다. 네트워크를 쓰지 않는다(이 PC 에만)."""
    params = P.load_params()
    intents, sides = set(params["intents"]), set(params["sides"])
    pick = lambda v, allowed: v if v in allowed else "other"  # noqa: E731
    root = root or os.path.join(P.work_root(), "cases")
    cnt = collections.Counter()
    ovc = collections.Counter()
    rounds, n, fast, days = [], 0, 0, []
    for case in (os.listdir(root) if os.path.isdir(root) else []):
        d = os.path.join(root, case)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith("_state.json"):
                st = P.load_json(os.path.join(d, f))
                n += 1
                prim = pick((st.get("intent") or {}).get("primary"), intents)
                side = pick(st.get("side"), sides)
                cnt["%s|%s" % (prim, side)] += 1
                for o in st.get("overrides", []):
                    ovc["%s|%s|%s" % (prim, side, pick(o.get("cell"), OVERRIDE_CELLS))] += 1
                rounds.append(len(st.get("rounds") or []))
                fast += 1 if (st.get("intent") or {}).get("fast_path") else 0
                days += [str(st[k])[:10] for k in ("created", "updated") if st.get(k)]
    return {"cases": n, "intent_side": dict(cnt), "override_cells": dict(ovc),
            "avg_rounds": round(sum(rounds) / len(rounds), 2) if rounds else None, "fast_path_ratio": round(fast / n, 2) if n else None,
            "plugin_version": _plugin_version(), "period": {"from": min(days), "to": max(days)} if days else None}


def share_block(summary):
    """복사용 블록 — 허용 필드만 다시 골라 담는다. 보내는 곳·방법은 아직 정하지 않았다(D-06)."""
    data = {k: summary.get(k) for k in STATS_FIELDS}
    return "```\nlawfirm 사용 통계\n%s\n```" % json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("resolve"); s.add_argument("state"); s.add_argument("--write", action="store_true")
    s = sub.add_parser("stats"); s.add_argument("root", nargs="?")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "resolve":
            st = P.load_json(a.state)
            design = resolve(st)
            out = {"ok": True, "design": design}
            if a.write:
                if not P.review_current(st):
                    raise NeedInput([{"key": "intent_review", "round_type": "intent_review",
                                      "why": "지금 의도에 대한 유불리 검토(「진행」 결정)가 없어 설계를 확정할 수 없습니다"}])
                import state as S
                path = write_design(a.state, st, design)
                st["design_path"] = path
                S.set_status(st, "designed")
                S.save(a.state, st)
                out["design_path"] = path
            return P.emit(out)
        if a.cmd == "stats":
            summary = stats(a.root)
            return P.emit({"ok": True, "summary": summary, "share_block": share_block(summary)})
    except NeedInput as e:
        return P.emit({"ok": False, "needs": e.needs}, 3)
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
