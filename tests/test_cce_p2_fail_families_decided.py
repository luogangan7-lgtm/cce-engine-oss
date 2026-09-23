# -*- coding: utf-8 -*-
"""闸: P2_FAIL 三族处置是**授权代定**(owner 可推翻), 且 P2 v2 的行为、重算、r2 不改, 全部现算。零调用。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_label_qualification as Q
DOC = (ROOT / "P2_FAIL_FAMILIES_DECIDED_2026-09-23.md").read_text(encoding="utf-8")
_s = importlib.util.spec_from_file_location("_rs", ROOT / "probes/p2_policy_v2_rescore.py"); rs = importlib.util.module_from_spec(_s); _s.loader.exec_module(rs)
TEXT = ("Settled on the Oticon after two fittings; the TV Connector also came in the box. "
        "Been wearing the Oticon daily since March and it gets me through a full day.")
REQ = ["输出新信息增量", "谈论对象是自己已拥有或已经历的"]


def _ev(span, sup, about=None, kind=None): return Q.EvidenceSpan(span, sup, TEXT, about=about, increment_kind=kind)


def test_delegation_is_stated_and_revocable():
    head = DOC.split("---")[0]
    assert "owner" in head and "代定" in head and "推理与取舍是我做的" in head
    assert "以他为准" in head and "作废重来" in head and "不是「你定的就是我想的」" in head
    for fam in ("**SET_MISMATCH**", "**SUBSTRING**", "**DISJOINT**"): assert fam in DOC
    assert "可比不可合" in DOC and "witness_intersection" in DOC and Q.P2_BINDING == "witness_intersection"


def test_surplus_evidence_about_another_object_no_longer_blocks_when_witness_exists():
    """SET_MISMATCH 族: A 支多给一条指向 TV Connector 的证据, 但两支在 Oticon 上有见证 ⇒ 升格; 多余证据记账。"""
    ev = [_ev("gets me through a full day", REQ[0], "Oticon", "数据"), _ev("the TV Connector also came in the box", REQ[0], "TV Connector", "使用细节"),
          _ev("Been wearing the Oticon daily since March", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CITED_UNVERIFIED and q["P2"]["witness"] == ["Oticon"] and q["P2"]["binding"] == "witness_intersection"
    assert [e["about"] for e in q["P2"]["surplus_dropped"]] == ["TV Connector"]


def test_disjoint_still_blocks_and_substring_is_not_merged():
    ev = [_ev("the TV Connector also came in the box", REQ[0], "TV Connector", "使用细节"), _ev("Been wearing the Oticon daily since March", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ); assert q["state"] == Q.CANDIDATE and q["P2"]["witness"] == [] and "不等价" in q["why"]
    ev2 = [_ev("gets me through a full day", REQ[0], "the Oticon daily", "数据"), _ev("Been wearing the Oticon daily since March", REQ[1], "Oticon")]
    q2 = Q.qualify("display", TEXT, evidence=ev2, required_conjuncts=REQ); assert q2["state"] == Q.CANDIDATE, "★ 子串/部件被当成同一对象 —— 裁定明禁"


def test_increment_checks_apply_to_witness_only_and_surplus_cannot_carry_them():
    """多余证据不能替见证 x 承担「增量种类/超出标识」: 见证上的增量片段缺种类 ⇒ 仍拦。"""
    ev = [_ev("gets me through a full day", REQ[0], "Oticon", None), _ev("the TV Connector also came in the box", REQ[0], "TV Connector", "使用细节"),
          _ev("Been wearing the Oticon daily since March", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ); assert q["state"] == Q.CANDIDATE and "哪一种" in q["why"]


def test_rescore_recomputes_and_r2_untouched():
    got = rs.build(); r = json.loads((ROOT / "results/p2_policy_v2_rescore.json").read_text(encoding="utf-8"))
    assert got["★v1 口径(r2 原读数)"] == r["★v1 口径(r2 原读数)"] and got["★v2 口径(见证交集)"] == r["★v2 口径(见证交集)"] and got["per_row"] == r["per_row"]
    assert r["★r2 产物 sha256(未改)"] == hashlib.sha256((ROOT / "results/real_corpus_pilot_r2.json").read_bytes()).hexdigest()
    assert r["★v1 口径(r2 原读数)"]["PASS_MECHANICAL"] == 12 and r["★v2 口径(见证交集)"]["PASS_MECHANICAL"] == 20
    mv = r["★★★ 三族去向(v1=P2_FAIL 的 16 张)"]; assert mv == {"SET_MISMATCH→PASS_MECHANICAL": 8, "SUBSTRING→P2_FAIL": 2, "DISJOINT→P2_FAIL": 6}
    assert "12/42" in DOC and "20/42" in DOC
    # 只有指针与标签, 没有原文: per_row 每个字符串值要么是 corpus/ 指针, 要么是状态/族标签(★ 文件名本身含 hearingaids, 不能拿它当原文检测)
    ok_labels = {"PASS_MECHANICAL", "P2_FAIL", "MALFORMED", "None", "SET_MISMATCH", "SUBSTRING", "DISJOINT"}
    for row in r["per_row"]:
        for v in row.values():
            if isinstance(v, str): assert v.startswith("corpus/") or v in ok_labels, v[:40]


def test_surplus_evidence_failing_increment_checks_does_not_block_a_complete_witness():
    """★ 反向: 多余证据(指向 TV Connector)自己缺增量种类 —— 若它还参与检查, 会把一张见证完整的证书拦下。v2 必须放行。"""
    ev = [_ev("gets me through a full day", REQ[0], "Oticon", "数据"), _ev("the TV Connector also came in the box", REQ[0], "TV Connector", None),
          _ev("Been wearing the Oticon daily since March", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CITED_UNVERIFIED and [e["about"] for e in q["P2"]["surplus_dropped"]] == ["TV Connector"]
