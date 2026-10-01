#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: display 剩余两项(④ 识别器 · 因子二)的授权代定 —— 代定可撤、数与结果文件一致、前提仍成立。

★ 文档里的数不是第二个真相源: 每个都从结果文件现算比对, 文件变了文档没跟 ⇒ 红。
★ (B) 的前提「已付费的真实语料行没存 A 支片段」也现算: 谁往行里加了片段/偏移, 前提就变了, 本闸红, 逼着重裁。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_REL = "docs/decisions/DISPLAY_REMAINDER_DECIDED_2026-10-01.md"
DOC = (ROOT / DOC_REL).read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "scripts"))
import cce_label_qualification as Q  # noqa: E402


def _j(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_delegation_is_stated_first_and_revocable():
    head = DOC.split("---")[0]
    assert "授权代定，owner 一句话可整体作废" in head
    assert "推理与取舍是我做的" in head and "以他为准" in head and "整体作废重来" in head
    assert "不是「你定的就是我想的」" in head


def test_rule_provenance_still_closed_and_points_here():
    """④ 不做 ⇒ rule 必须仍然抛错, 且错误信息指向本裁定; 任何状态都不可引用为已确认。"""
    assert Q.DECISION_RULE_CONFIRMED == DOC_REL
    t = "I wear my Oticon More 1 every day and the battery lasts 30 hours."
    ev = [Q.EvidenceSpan("the battery lasts 30 hours", "信息增量", t, about="Oticon More 1",
                         increment_kind="数据"),
          Q.EvidenceSpan("I wear my Oticon More 1", "已拥有", t, about="Oticon More 1")]
    try:
        Q.qualify("display", t, evidence=ev, required_conjuncts=["信息增量", "已拥有"], provenance="rule")
    except NotImplementedError as e:
        assert DOC_REL in str(e), "★ rule 的错误信息没指向裁定 —— 下一个人会以为只是还没写"
    else:
        raise AssertionError("★★★ provenance='rule' 放行了 —— 本裁定说 ④ 不做")
    q = Q.qualify("display", t, evidence=ev, required_conjuncts=["信息增量", "已拥有"])
    assert q["state"] == Q.CITED_UNVERIFIED and not Q.is_citable_as_confirmed(q)


def _main(rel):
    return _j(rel)["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]


def test_closed_routes_match_result_files():
    # ② 模型填槽: 三轮 B 臂鉴别格与冻结的门
    for rel, tag in (("results/slot_filling_r5.json", "r5"), ("results/slot_filling_r6.json", "r6"),
                     ("results/slot_filling_r6_jev.json", "r6-jev")):
        m = _main(rel)
        got = m["B 臂鉴别格"]
        gate = re.search(r"≥(\d+)/24", m["★冻结的门(预注册, 非现算)"]).group(1)
        assert int(got.split("/")[0]) < int(gate), "★ %s 现在过门了 —— (A) 的前提变了, 重裁" % tag
        assert "%s **%s**（门 ≥%s/24）" % (tag, got, gate) in DOC, "★ 文档里 %s 的数与结果文件不符" % tag
    # ③ 规则: 真实证书上冻结族最佳净增益
    real = _j("results/shallow_rule_on_real_certs.json")
    best = max(r["净增益"] for r in real["★真实证书上重搜冻结族的最佳"])
    assert best == 0 and real["★★★那条规则在真实证书上"]["净增益"] == 0
    assert "最佳**净增益 0**" in DOC
    assert _j("results/best_shallow_rule_search.json")["★★★冻结规则族"]["族规模"] == 378 and "378 条" in DOC
    # ① prompt: gen9 生产臂 vs 候选臂
    g = _j("results/gen9_verdict.json")
    rate = next(v for k, v in g.items() if k.startswith("★★★超出冻结决策规则的发现"))
    rate = next(v for k, v in rate.items() if k.startswith("① display 出现率"))
    frac = lambda *ks: [tuple(map(int, rate[k].split("/"))) for k in ks]
    s = lambda xs: "%d/%d" % (sum(a for a, _ in xs), sum(b for _, b in xs))
    prod, cand = s(frac("生产 A 臂(合同说不该)", "生产 B 臂(合理可能)")), s(frac("候选 A 臂", "候选 B 臂"))
    assert "生产臂 **%s**" % prod in DOC and "候选臂 **%s**" % cand in DOC
    assert "A 臂 %s > B 臂 %s" % (rate["候选 A 臂"], rate["候选 B 臂"]) in DOC


def test_factor_two_premise_spans_not_stored():
    """(B) 的前提: 已付费的真实语料行里没有 A 支片段的原文 / sha / 偏移。"""
    n = 0
    for rel in ("results/real_corpus_pilot_partial.jsonl", "results/real_corpus_pilot_r2_partial.jsonl"):
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            n += 1
            bad = [k for k in row if ("span" in k.lower() or "偏移" in k or "offset" in k.lower())
                   and k != "span_逐字"]
            assert not bad, "★★★ 行里有片段字段 %s —— 因子二可能零调用可算, (B) 必须重裁" % bad
            assert all(isinstance(x, bool) for x in row.get("span_逐字", []))
    assert n == 84 and "84 行" in DOC
    feas = _j("results/real_corpus_feasibility.json")
    k = next(k for k in feas["★语料规模"] if k.startswith("机械候选"))
    assert "%d 条机械候选" % feas["★语料规模"][k] in DOC


def test_it_does_not_smuggle_in_an_authorization():
    blk = DOC.split("## 这些裁定**没有**授权什么")[1].split("## ")[0]
    for must in ("不构成运行授权", "不倒灌", "一字未动"):
        assert must in blk
    reopen = DOC.split("## 重开条件")[1]
    assert "新预注册" in reopen and "留出集" in reopen and "偏移" in reopen


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("test_cce_display_remainder_decided: OK (④ rule 仍关且指向裁定 · 三条已关路线的数与结果文件现算一致 · "
          "因子二前提「84 行未存 A 支片段」现算成立 · 代定可撤)")
