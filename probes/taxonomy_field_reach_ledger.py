#!/usr/bin/env python3
"""★★★ 分类学**每一个字段**到底进不进 prompt —— 零 API 的静态消融。

## 为什么
2026-09-08 在 `negative_examples_prompt` 上发现: 它只进**验收闸**, 不进**生产 s2**。
而在此之前, `hard_discriminant` 被我当成病因写进诊断 —— 它**两边都不进**。
⇒ 「这个字段影响模型吗」此前是**逐个字段临时查**的, 查漏一个就得到一条假因果(今天第三次)。
本台账把它做成**全字段现算**: 每个字段落在四格之一。

## 四格
· BOTH        —— 闸与生产都看得到
· GATE_ONLY   —— 只有验收闸看得到(改它 = 改闸, 不改生产)
· PROD_ONLY   —— 只有生产看得到(改它 = 改仪器, instrument_hash 会变)
· NEITHER     —— **两边都不进**。它是给人读的, 或者是死字段。
                 ★ 拿 NEITHER 的字段解释模型行为, 一定是假因果。

## ★ 这不是消融
它只回答「字面是否出现在 prompt 里」, **不回答「删了读数会不会变」**。
真消融要花 API。⇒ 本台账给的是**下界: NEITHER 一定没影响; BOTH/GATE_ONLY 未必有影响。**
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_PROBE_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))


# ══ ★★★ NEITHER 的第二个轴(2026-09-09) ══════════════════════════════════════
#  网页版 GPT 指出: **27 个不进 prompt 的字段不应一概视为测量无关** ——
#  changelog 与 hard_discriminant 的语义地位完全不同。应按
#  「**是否规定构念边界 / 是否影响实际程序 / 是否影响结果用途**」分类。**这条批评我接受。**
#  ★★ 本轴是**人判的, 无法从源码推出**  ⇒ 它是一份**可被反驳的声明**, 不是测量结果。
#     闸只保证「每个 NEITHER 字段都有明确归类」, **不保证归类是对的**。
NEITHER_AXIS = {
    "changelog_1_1_0": "均不",
    "changelog_1_1_1": "均不",
    "changelog_1_2_0": "均不",
    "changelog_1_3_0": "均不",
    "changelog_1_3_1": "均不",
    "changelog_1_3_1_b": "均不",
    "changelog_2026_09_05_atoms_a1a2": "均不",
    "changelog_2026_09_07_acceptance_rerun": "均不",
    "changelog_2026_09_07_gk3_revoked": "均不",
    "changelog_2026_09_07_qualification_is_a_coin_flip": "均不",
    "changelog_2026_09_07_repeatability_external_belong": "均不",
    "definition_of_knot": "规定构念边界",
    "extension_slots_pending_data": "影响结果用途",
    "extra_appraisal_slots": "规定构念边界",
    "frozen_at": "影响结果用途",
    "identity_criterion": "规定构念边界",
    "knots[].composition_note": "规定构念边界",
    "knots[].cost_tier": "规定构念边界",
    "knots[].cost_tier_note": "规定构念边界",
    "knots[].cross_turn_strategy": "规定构念边界",
    "knots[].evidence_level": "影响结果用途",
    "knots[].hard_discriminant": "规定构念边界",
    "knots[].internal_examples": "影响结果用途",
    "knots[].playbook": "影响结果用途",
    "source": "影响结果用途",
    "status": "影响结果用途",
    "★qualification_premise_of_the_2026-09-07_PASS_is_revised": "均不"
}

NEITHER_NOTE = {
    "changelog_1_1_0": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_1_1_1": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_1_2_0": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_1_3_0": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_1_3_1": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_1_3_1_b": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_2026_09_05_atoms_a1a2": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_2026_09_07_acceptance_rerun": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_2026_09_07_gk3_revoked": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_2026_09_07_qualification_is_a_coin_flip": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "changelog_2026_09_07_repeatability_external_belong": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**",
    "definition_of_knot": "**结的定义本身**。不进 prompt, 但它是整个分类学的构念根。",
    "extension_slots_pending_data": "待扩展槽位 —— 决定「哪些还没被覆盖」。",
    "extra_appraisal_slots": "附加评价维度。",
    "frozen_at": "冻结时间, 版本追溯用。",
    "identity_criterion": "同一性判据 —— 决定「两个类算不算同一个」。",
    "knots[].composition_note": "组合/顺序约束, 属构念定义。",
    "knots[].cost_tier": "成本档是构念的一部分(行为成本), 但其文字已包含在 behavior 里, 单独字段不进 prompt。",
    "knots[].cost_tier_note": "同上的说明。",
    "knots[].cross_turn_strategy": "跨轮次规则 —— 单文本判官**结构上看不到**, 所以正当地不进 prompt; 但它是构念的一部分。",
    "knots[].evidence_level": "该类的证据等级标注 —— 决定结论能被引用到多强, 不进 prompt。",
    "knots[].hard_discriminant": "★★ **规定构念边界**(它是九类判别的人读定义), 但**不进任何 prompt** ⇒ 它约束的是**人怎么理解这个类**, 不是模型怎么判。⇒ 拿它解释模型行为=假因果; 但拿它当构念定义的真值**是正当的**。",
    "knots[].internal_examples": "人读例子; 已实测七个里六个不在语料中(见 test_cce_internal_examples)。不进 prompt, 但被引用为「这个类长什么样」。",
    "knots[].playbook": "下游 manipulation 建议, 由 manifest 第五条路专门管辖。不进 prompt, 但**改变三个下游读数测的是什么**。",
    "source": "来源出处。",
    "status": "★★ 整个分类学的**现状与作用域声明** —— 它决定所有结论能被引用到多强。不进 prompt, 但**测量学上最要紧的字段之一**。",
    "★qualification_premise_of_the_2026-09-07_PASS_is_revised": "变更历史 —— 不规定构念、不影响程序、不影响结论用途。**这一格才是真正的『测量无关』。**"
}


def _prompts():
    import cce_knot_classify as CK
    import run_gates as RG
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    gate = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                               decision_tree=RG.DECISION_TREE,
                               negative_examples=RG.NEGATIVE_EXAMPLES, body="<B>")
    prod = CK._build_stage2_prompt(taxo, "<T>", {"tops": "<S>", "appraisal": "<A>"})
    prod += CK._stage1_template()          # s1 也是仪器的一部分
    return taxo, gate, prod


def _frags(v, out=None):
    """把一个字段值**递归**摊成可检索的字面片段 —— 键与值都要, 嵌套也要。

    ★ 第一版只取顶层字符串值 ⇒ `family`(短串被长度阈值滤掉)、`levers_not_knots`(是**键**不是值)、
      `typical_codes`(值是**列表**) 全部漏判成 NEITHER。
      **漏判方向是「说它不进 prompt」—— 正是会制造假因果的那个方向。**
    """
    out = [] if out is None else out
    if isinstance(v, str):
        if v.strip():
            out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            if isinstance(k, str) and k.strip():
                out.append(k)          # ★ 键也进 prompt(levers_not_knots 就是靠键)
            _frags(x, out)
    elif isinstance(v, list):
        for x in v:
            _frags(x, out)
    return out


def _reach(frag, hay, n=24):
    """判定「这个字段到达了这份 prompt 吗」。

    ★ 两版都错过, 记下来:
      v1 只取顶层字符串值 + 长度 >=4 ⇒ `family`(值只有两字)、`levers_not_knots`(内容在**键**上)、
         `typical_codes`(值是列表) 全被漏判成 NEITHER —— **漏判方向正是会制造假因果的那个**。
      v2 递归 + 阈值降到 2 ⇒ 冒出**假阳性**: `typical_codes` 的**键**「need」命中了签名里的
         `"need_status"` 子串, 于是它被判成 BOTH(实际 PROD_ONLY)。

    ⇒ 现行判据(两者取或): **>=2 个互不相同的片段命中**, 或 **单个 >=6 字的片段命中**。
      单个短片段的偶然命中(如「need」)因此被挡掉, 而真到达的字段总能满足其一。
      ★ 这条规则不是推理出来的, 是由 main() 的自校验**对着六个已独立核实的字段调出来的**;
        它若再错, 自校验会停在落盘之前。
    """
    hits = {f for f in frag if len(f) >= 2 and f[:n] in hay}
    return len(hits) >= 2 or any(len(f) >= 6 for f in hits)


def _read_by_source():
    """★★ 主判据: **prompt 构造器的源码里读了哪些分类学字段**。

    子串法答错了问题 —— 它答「这个字段的文字出现在 prompt 里吗」, 而**文字会重叠**:
    `changelog_1_3_0` 逐字引用了决策树原文, 于是被子串法判成 BOTH; `cost_tier` 的
    「高成本」也出现在 behavior 里。两者都不是被注入的。
    ⇒ 正确的问题是「**构造 prompt 的代码取了这个键吗**」, 用 AST 直接答。
    """
    import ast
    import re
    src = {}
    rg = (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8")
    ck = (ROOT / "scripts/cce_knot_classify.py").read_text(encoding="utf-8")

    def keys_in(text):
        """text 里 ['x'] / .get("x") / ["x"] 取到的键名。"""
        out = set()
        for m in re.finditer(r"""\[\s*["'](\w+)["']\s*\]|\.get\(\s*["'](\w+)["']""", text):
            out.add(m.group(1) or m.group(2))
        return out

    # 闸侧: KNOT_BRIEF / DECISION_TREE / NEGATIVE_EXAMPLES 三处组装块
    i = rg.index("KNOT_BRIEF = ")
    j = rg.index("# ══ G-K1 v2")
    src["gate"] = keys_in(rg[i:j])
    # 生产侧: _build_stage2_prompt + _stage1_case/build_prompt 的分类学取用
    a = ck.index("def _build_stage2_prompt")
    b = ck.index("\ndef ", a + 10)
    src["prod"] = keys_in(ck[a:b])
    return src


def main():
    taxo, gate, prod = _prompts()
    rows = {}
    knot_fields = sorted({k for kn in taxo["knots"] for k in kn})
    for f in knot_fields:
        frag = [x for kn in taxo["knots"] for x in _frags(kn.get(f))]
        if not frag:
            continue
        g, p = _reach(frag, gate), _reach(frag, prod)
        rows[f"knots[].{f}"] = "BOTH" if g and p else "GATE_ONLY" if g else "PROD_ONLY" if p else "NEITHER"
    for f, v in taxo.items():
        if f in ("knots",):
            continue
        frag = _frags(v)
        if not frag:
            continue
        g, p = _reach(frag, gate), _reach(frag, prod)
        rows[f] = "BOTH" if g and p else "GATE_ONLY" if g else "PROD_ONLY" if p else "NEITHER"

    # ── ★★★ 主判据: 源码读取。子串法降为**交叉核对**, 不一致就报出来, 不静默择一 ──
    by_src = _read_by_source()
    src_rows, disagree = {}, {}
    for f in knot_fields:
        g, p_ = f in by_src["gate"], f in by_src["prod"]
        src_rows[f"knots[].{f}"] = ("BOTH" if g and p_ else "GATE_ONLY" if g else
                                    "PROD_ONLY" if p_ else "NEITHER")
    for f in taxo:
        if f == "knots":
            continue
        g, p_ = f in by_src["gate"], f in by_src["prod"]
        src_rows[f] = ("BOTH" if g and p_ else "GATE_ONLY" if g else
                       "PROD_ONLY" if p_ else "NEITHER")
    for k in set(src_rows) | set(rows):
        if src_rows.get(k, "NEITHER") != rows.get(k, "NEITHER"):
            disagree[k] = {"源码读取(主判据)": src_rows.get(k, "NEITHER"),
                           "字面子串(交叉核对)": rows.get(k, "NEITHER")}
    rows = src_rows


    # ★★★ 自校验必须校**主判据**(src_rows), 不是被它覆盖掉的那个。
    #   ★ 我第一版把自校验放在 `rows = src_rows` **之前** —— 于是它校的是随后被丢弃的中间结果,
    #     **主判据一行都没被检查过**。今天第三次「新机制自己也要被检查」。
    KNOWN = {"knots[].typical_codes": "PROD_ONLY", "knots[].family": "PROD_ONLY",
             "levers_not_knots": "PROD_ONLY", "knots[].negative_examples_prompt": "GATE_ONLY",
             "knots[].signature": "BOTH", "knots[].behavior": "BOTH",
             "knots[].hard_discriminant": "NEITHER"}
    wrong = {k: (rows.get(k), want) for k, want in KNOWN.items() if rows.get(k) != want}
    assert not wrong, (
        f"★★★ 自校验失败(主判据: 现算 vs 已独立核实): {wrong}\n"
        "⇒ **不落盘** —— 一张说错「进不进 prompt」的表比没有表更危险。")

    buckets = {}
    for k, v in rows.items():
        buckets.setdefault(v, []).append(k)
    out = {
        "block": "TAXONOMY_FIELD_REACH_LEDGER",
        "★zero_api": "现算两侧真实 prompt 再做字面子串检测, 零 API。",
        "★what_it_is_not": ("**不是消融**。只答「字面进不进 prompt」, 不答「删了读数变不变」。"
                            "⇒ 给的是**下界**: NEITHER 一定**不影响模型的判读行为**(但可能影响构念定义与结论用途, 见第二个轴); BOTH/GATE_ONLY 未必有影响。"),
        "per_field": rows,
        "★★判据": ("**主判据 = prompt 构造器源码里取了哪个键**(AST/正则现算)。"
                   "字面子串法降为交叉核对 —— 它答的是「这个字段的文字出现了吗」, 而**文字会重叠**: "
                   "`changelog_1_3_0` 逐字引用决策树原文、`cost_tier` 的「高成本」也在 behavior 里, "
                   "两者都被子串法误判为到达。"),
        "★★★两种判法不一致的字段(不静默择一, 摆出来)": disagree,
        "buckets": {k: sorted(v) for k, v in sorted(buckets.items())},
        "★★★NEITHER_的第二个轴": {
            "★why": ("不进 prompt **不等于**测量无关。按「规定构念边界 / 影响实际程序 / 影响结果用途」再分一次。"
                     "★ 本轴人判、可被反驳; 闸只保证每个 NEITHER 都有归类, 不保证归类对。"),
            "分类": {k: {"轴": NEITHER_AXIS[k], "说明": NEITHER_NOTE[k]}
                     for k in buckets.get("NEITHER", []) if k in NEITHER_AXIS},
            "未归类": [k for k in buckets.get("NEITHER", []) if k not in NEITHER_AXIS],
            "★统计": {a: sum(1 for k in buckets.get("NEITHER", []) if NEITHER_AXIS.get(k) == a)
                      for a in ("规定构念边界", "影响结果用途", "均不")},
            "★★★结论": ("**只有 changelog 类是真正的测量无关。** 其余要么规定构念边界、要么影响结论用途。"
                        "⇒ 原表那句「NEITHER 一定没影响」**说过头了**。正确说法: "
                        "**NEITHER 一定不影响模型的判读行为, 但可能影响构念定义与结论的可引用范围。**"),
        },
        "★★NEITHER_是最要紧的一格": (
            "两边都不进的字段**不可能**解释模型行为。"
            "★ 2026-09-08 我就是拿 NEITHER 格的 `hard_discriminant` 写了 suspend 的病因, "
            "而那个短语模型一次都没见过 —— 一条讲得通但为假的因果。"),
        "★GATE_ONLY_的含义": (
            "改它 = **只改验收闸**, 生产分类器一个字不变, `instrument_hash` 也不变。"
            "⇒ 换代路由不能走「递增 instrument_generation」那条。"),
        "★how_to_use": "改任何分类学字段之前, 先在本表里查它落在哪一格。**这是三次假因果的直接对策。**",
        "★★★granularity_limit_do_not_over_read": (
            "★ 粒度是「顶层字段」与「knots[].字段」两层, **不拆嵌套**。"
            "⇒ `annotation_protocol` 判 GATE_ONLY, 指的是**这个容器里有东西**进闸(decision_tree_prompt), "
            "**不等于**它每个子字段都进 —— 同一个容器里的 `gate_record` / `anchor_source` / `version` "
            "一个都不进 prompt。"
            "★★ 拿容器的格子去推子字段, 就是本表要防的那类假因果的**变体**。要判子字段, 单独查。"),
    }
    p = ROOT / "tests/data/taxonomy_field_reach_ledger.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("✏️", p.relative_to(ROOT), "\n")
    for b in ("BOTH", "GATE_ONLY", "PROD_ONLY", "NEITHER"):
        if b in buckets:
            print(f"  {b:10s} ({len(buckets[b])}): {', '.join(sorted(buckets[b]))}")


if __name__ == "__main__":
    main()
