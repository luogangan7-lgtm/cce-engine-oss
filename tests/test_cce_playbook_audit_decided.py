# -*- coding: utf-8 -*-
"""闸: 对齐出口三值 + audit 弃用潜在姿态是**授权代定**(owner 可整体作废), 且裁定与代码、结果文件一致。零调用。"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_align_atoms as AT   # noqa: E402
DOC = (ROOT / "docs/decisions/PLAYBOOK_TRI_STATE_AUDIT_DECIDED_2026-10-01.md").read_text(encoding="utf-8")
KNOTS = {k["key"]: k for k in json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))["knots"]}
NEW_TEXT = "不辩解不表演;给可验证事实(数字/来源/可查记录)+明确邀请对方核验或追问具体细节(『Ask me anything specific』)"


def test_delegation_is_stated_and_revocable():
    head = DOC.split("---")[0]
    assert "授权代定，owner 一句话可整体作废" in head and "推理与取舍是我做的" in head
    assert "以他为准" in head and "作废重来" in head and "不是「你定的就是我想的」" in head
    assert "BLOCKED_EXTERNAL" in DOC and "不做、不招募" in DOC


def _audit_text_errors(pb):
    errs = []
    if "姿态" in pb: errs.append("潜在姿态仍在串里")
    if "明确邀请" not in pb or "可验证事实" not in pb: errs.append("A/B 两件事缺一")
    if "『Ask me anything specific』" not in pb: errs.append("显式邀请的示例丢了")
    if len([p for p in pb.replace("；", ";").split(";") if p.strip()]) != 2: errs.append("分号结构变了(旧分解应仍为 2 原子)")
    return errs


def test_decided_text_is_well_formed_and_landing_status_is_honest():
    """裁定的新串本身合格; 产品串若还没落地, 文件必须照实写「未落地」—— 落地了则必须逐字是裁定的串。"""
    assert not _audit_text_errors(NEW_TEXT) and NEW_TEXT in DOC
    assert "姿态" in KNOTS["audit"]["playbook"] or KNOTS["audit"]["playbook"] == NEW_TEXT, "★ 产品串被改成了第三种写法"
    if KNOTS["audit"]["playbook"] != NEW_TEXT:
        assert "未落地" in DOC and "negative_changelogs" in DOC, "★ 产品串没改, 文件却没写明为什么"


def test_measurement_side_untouched():
    """audit 的现行测量(OPERATIONAL + V3 题面)一字未动 ⇒ V3 与 tri 的 audit 结论仍适用。"""
    assert [t for t, _ in AT.atoms_of("audit")] == ["不辩解(不为自己的做法或资历辩护)", "不表演(不摆资历、不表忠心、不夸耀自己)",
                                                  "给出可验证的事实(具体数字、来源或可查的记录)", "明确邀请对方检验或追问具体细节"]
    v3 = json.loads((ROOT / "results/align_atoms_v3.json").read_text(encoding="utf-8"))
    live = hashlib.sha256(json.dumps({k: AT.jev_questions_v3(k, AT.PANEL_V3 + (AT.AUDIT_V3,)) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest()
    assert live == v3["questions_sha256"], "V3 题面在确认后被改过"
    assert {k: v["verdict"] for k, v in v3["per_atom"].items() if k.startswith("audit#")} == {
        "audit#0": "NOT_VALIDATED", "audit#1": "VALIDATED", "audit#2": "VALIDATED", "audit#3": "VALIDATED"}


def test_doc_numbers_are_the_result_files():
    r = json.loads((ROOT / "results/align_atoms_tri.json").read_text(encoding="utf-8"))
    assert r["summary"]["adopted"] == 6 and "6/7 ADOPTED" in DOC and r["requests"] == 252 and "252 次" in DOC
    assert r["per_atom"]["itch#1"]["verdict"] == "NOT_ADOPTED" and "itch#1 NOT_ADOPTED" in DOC
