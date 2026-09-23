# -*- coding: utf-8 -*-
"""附件 A 已升为合同(owner 2026-09-14 裁定)的闸。

★★★ 本文件守的核心是一条**边界**: **升的只有 A**。
  「五类各自的成立条件」是**另一条**解释, **未升** —— 一旦它也被当成合同,
  「只用合同明文」那一档就会虚高, 而那一档正是 r3/MIS-4 头条结论的载体。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SHEET = ROOT / "OWNER_DECISION_SHEET.md"
ANNEX = ROOT / "OWNER_DECISION_ANNEX_definitions.md"
REPLAY = ROOT / "results/claim_frame_replay.json"
RANN = ROOT / "tests/data/claim_frame_replay_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
import cce_claim_frame as CF                                        # noqa: E402

P = CF.CONJ_P
BASE = dict(speaker="SELF", polarity="ASSERTED", time="PAST_OR_PRESENT",
            citation="DIRECT", possession="OWNED", increment_kind="数据")


def _p(pv, ui):
    return CF.adjudicate(CF.ClaimFrame("x", P, object="o", predicate=pv, **BASE),
                         use_interpretation=ui)


def test_附件A已升为合同_两档都拦且标合同档():
    for ui in (True, False):
        st, why, basis = _p("RESTATES_IDENTIFIER", ui)
        assert st == CF.REFUTES, "★★★ 附件 A 已是合同, 两档都该拦(解释档=%s 时却 %s)" % (ui, st)
        assert basis == CF.BY_CONTRACT, "★★★ 依据档应为合同明文, 实际 %r" % basis
        assert "附件 A" in why and "升为合同" in why


def test_没升的那条不许一起升():
    """★★★ 「五类各自的成立条件」**未升** —— 它必须仍然只在解释档拦。
    一旦它也走合同档, 「只用合同明文」那一档就虚高了。"""
    st_i, _, basis_i = _p("NOT_OF_DECLARED_KIND", True)
    st_c, _, _ = _p("NOT_OF_DECLARED_KIND", False)
    assert st_i == CF.REFUTES and basis_i == CF.BY_INTERPRETATION, (
        "★ 解释档下应拦住且标依赖解释, 实际 %s / %s" % (st_i, basis_i))
    assert st_c == CF.SUPPORTS, (
        "★★★ NOT_OF_DECLARED_KIND 在**只用合同明文**档下被拦住了 —— "
        "那条**没有升**, 把它当合同会让那一档虚高")


def test_两个否定取值必须是分开的():
    """★ 拆开之前两条混在同一个取值里, **一升就会把没升的那条一起当成合同**。"""
    assert set(CF.PREDICATE_NEG) == {"RESTATES_IDENTIFIER", "NOT_OF_DECLARED_KIND"}
    src = (ROOT / "scripts/cce_claim_frame.py").read_text(encoding="utf-8")
    assert "只升 A" in src, "★ 源码里必须写明只升了 A"


def test_决策书与附件都记了裁定_且写明只升A():
    sh, an = SHEET.read_text(encoding="utf-8"), ANNEX.read_text(encoding="utf-8")
    for f, t in (("决策书", sh), ("附件", an)):
        assert "owner" in t and "升为合同" in t, "★ %s 没记裁定" % f
        assert "2026-09-14" in t
    # ★ 原句以**引述**形式留痕("原文曾写「…」—— 该状态已结束"), 不是原位保留。
    #   两者都可以, 但**必须有一个** —— 抹掉它, 读者就看不到这条曾经是可推翻的提案。
    assert "原文曾写「这条是我的提案，可以被你推翻」" in sh, (
        "★★★ 原句的留痕被抹掉了 —— 读者将看不到「它曾经是可被推翻的提案」这件事")
    assert "该状态**已结束**" in sh
    # ★★★ 「只升 A」这条边界**决策书与附件都要有** —— 少一处, 读另一处的人就会以为全升了
    for f, t, phrase in (("决策书", sh, "这次升的只有附件 A"),
                         ("附件", an, "升的只有 A")):
        assert phrase in t, "★★★ %s 里缺「只升 A」的边界声明(%r)" % (f, phrase)
    for must in ("不覆盖", "五类各自的成立条件", "仍未升"):
        assert must in sh, "★ 决策书里缺边界声明: %s" % must
    assert "**B（文本正面证据包含什么）与 C（确定标签指什么）状态未变**" in an, (
        "★ 附件里必须逐字写明 B/C 状态未变")
    # ★ 回滚点必须是**实际存在的路径**, 不是「回滚点」这三个字
    m = re.search(r"回滚点\*\*[:：]\s*`([^`]+)`", an)
    assert m, "★★★ 合同变更必须留**可指路径**的回滚点(现在连路径都没有)"
    assert "backup-annexA-" in m.group(1), "★ 回滚点路径不像这次变更的备份: %r" % m.group(1)


def test_裁定依据是owner的决定_不是读数():
    """★★★ 这次变更的依据是 owner 裁定。若写成「读数证明了该升」, 那就是用读数改合同。"""
    sh = SHEET.read_text(encoding="utf-8")
    assert "裁定依据不是读数" in sh, "★★★ 必须写明依据不是读数"
    assert "它们**不构成**依据" in sh, "★ 三条线索必须被标成「促成提问」而不是「依据」"
    d = json.loads(RANN.read_text(encoding="utf-8"))
    k = [x for x in d if "合同变更" in x][0]
    assert "不是任何读数" in d[k]


def test_合同明文现在拦得住那次真实的错误升格():
    if not REPLAY.exists():
        return
    r = json.loads(REPLAY.read_text(encoding="utf-8"))
    k = [x for x in r if "那次真实的错误升格" in x][0]
    assert r[k]["只用合同明文"] == "拦住", (
        "★★★ 升了附件 A 之后, 合同明文仍拦不住 r3/MIS-4 —— 那这次变更没起作用")
    assert r["★★★阴性_拦得住吗"]["只用合同明文"]["被拦住"] == "3/3"
    # ★ 对照不许被误拦 —— 升合同不得把对照也拦掉
    for t in ("只用合同明文", "明文+解释"):
        assert r["★★★对照_会不会误拦"][t]["★被误拦"].startswith("0/"), (
            "★★★ 升合同后 %s 误拦了对照 —— 那比漏更糟" % t)


def test_最小对照没覆盖附件A这件事要如实登记():
    """★ 实测: 最小对照那五类**没有一类依据附件 A** ⇒ 升了合同但那套测不到它。
    这是个**缺口**, 必须登记, 否则下一个人会以为已经测过。"""
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    bases = {p["依据"] for p in d["pairs"]}
    assert "附件 A" not in " ".join(bases), "★ 若已有一类依据附件 A, 本条要重写"
    k = [x for x in d if "附件 A" in x and "零覆盖" in x]
    assert k, (
        "★★★ 最小对照对附件 A **零覆盖**这件事没登记 —— "
        "下一个人会以为「升了合同且测过了」")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("附件 A 升合同闸 %d 项全过" % n)
