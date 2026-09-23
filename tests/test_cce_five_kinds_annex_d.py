# -*- coding: utf-8 -*-
"""闸: 五类增量成立条件 = 候选附件 D(授权代定, 未升合同)。零调用。守: 代定头 · 五类齐全且每类有 成立/反例/怎么核 · 与代码里的 INCREMENT_KINDS 同名同序 · 判据层五类仍走 BY_INTERPRETATION · 启用门槛数字在。"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
DOC = (ROOT / "FIVE_KINDS_ANNEX_D_CANDIDATE_2026-09-23.md").read_text(encoding="utf-8")


def test_delegation_head_and_candidate_status():
    head = DOC.split("---")[0]
    assert "owner" in head and "代定" in head and "推理与取舍是我做的" in head and "以他为准" in head and "作废重来" in head and "不是「你定的就是我想的」" in head
    assert "候选，未升合同" in head and "BY_INTERPRETATION" in head


def test_five_kinds_match_code_and_each_has_condition_counterexample_check():
    import cce_label_qualification as LQ
    rows = re.findall(r"^\| \*\*(.+?)\*\* \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$", DOC, flags=re.M)
    names = [r[0] for r in rows]
    assert tuple(names) == LQ.INCREMENT_KINDS, (names, LQ.INCREMENT_KINDS)
    for name, cond, counter, check, cant in rows:
        assert len(cond) > 10 and len(counter) > 5 and len(check) > 10 and len(cant) > 3, name
    src = (ROOT / "scripts/cce_claim_frame.py").read_text(encoding="utf-8")
    assert "BY_INTERPRETATION" in src and "BY_CONTRACT" in src, "★ 判据层两档都得在"


def test_promotion_gate_is_frozen_with_numbers_and_forbidden_shortcuts():
    gate = DOC.split("启用（升合同）门槛")[1]
    assert "每一类至少 6 个鉴别格" in gate and "总鉴别格 ≥ 30" in gate and "超过最佳浅层规则臂" in gate and "CONTRACT_CHANGE" in gate
    for bad in ("直接写成正则塞进资格层", "改成 BY_CONTRACT", "用旧对照集跑一轮"): assert bad in DOC, bad
    assert "析取" in DOC and "只算**一次**" in DOC
