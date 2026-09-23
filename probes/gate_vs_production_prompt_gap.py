#!/usr/bin/env python3
"""★★★ 验收闸的标注者 prompt 与生产分类器的 prompt **不是同一台仪器**。零 API。

## 怎么发现的
给 suspend 定修法时要回答「改 negative_examples_prompt 走哪条换代路」。
实测: 改它 **instrument_hash 一字不变**(d4cce4c745f3f991) —— 因为 `_stage2_template`
根本不读 negative_examples。顺着这条线查下去才发现: **两边喂的字段集合本就不同。**

## 这不是「闸有 bug」, 是一个**必须被写下来的作用域事实**
G-K1 完全可以正当地只是一次「分类学可被独立标注者一致标注吗」的信度研究。
问题不在它测了什么, 在于**它的读数被引用成什么** —— 一旦有人拿「G-K1 通过」去
支持「生产分类器可靠」, 那就跨了作用域, 而**跨没跨, 此前无处可查**。
"""
import json
import os
import pathlib
import sys

# ★ 本探针零 API。故意塞一个**不可能通话**的哨兵 key: run_gates 在 import 期读环境变量,
#   而塞哨兵比塞真 key 更安全 —— 万一将来有人给它加了调用, 会立刻 401 而不是静默烧钱。
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_PROBE_SENTINEL_NOT_A_KEY")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "accuracy"))


def fields():
    """两侧 prompt 各自喂进去的分类学字段 —— 从**源码实际构造**上读, 不靠人写清单。"""
    import cce_knot_classify as CK
    import run_gates as RG
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    k0 = taxo["knots"][0]
    prod = CK._build_stage2_prompt(taxo, "<T>", {"tops": "<S>", "appraisal": "<A>"})
    gate = RG.DIST_TMPL.format(unit="评论", brief=RG.KNOT_BRIEF, decision_tree=RG.DECISION_TREE,
                               negative_examples=RG.NEGATIVE_EXAMPLES, body="<B>")

    def has(hay, needle):
        return bool(needle) and str(needle)[:40] in hay

    probes = {
        "signature": json.dumps(k0["signature"], ensure_ascii=False)[:40],
        "behavior": k0["behavior"][:40],
        "typical_codes": json.dumps(k0["typical_codes"], ensure_ascii=False)[:40],
        "family": f"|{k0['family']})",
        "decision_tree": taxo["annotation_protocol"]["decision_tree_prompt"][0][:40],
        "negative_examples": k0.get("negative_examples_prompt", "")[:40],
        "levers_not_knots": list(taxo["levers_not_knots"].keys())[0],
        "anchor_examples": "【锚例·display】",
    }
    return {n: {"生产s2": has(prod, v), "验收闸": has(gate, v)} for n, v in probes.items()}


def main():
    f = fields()
    only_gate = sorted(k for k, v in f.items() if v["验收闸"] and not v["生产s2"])
    only_prod = sorted(k for k, v in f.items() if v["生产s2"] and not v["验收闸"])
    out = {
        "block": "GATE_VS_PRODUCTION_PROMPT_GAP",
        "★zero_api": "全部从源码现算构造两侧 prompt 再做子串检测, 零 API。",
        "per_field": f,
        "★only_the_gate_sees": only_gate,
        "★only_production_sees": only_prod,
        "★★the_fact": (
            f"验收闸的标注者独占 **{len(only_gate)}** 个分类学字段({', '.join(only_gate)}), "
            f"生产分类器独占 **{len(only_prod)}** 个({', '.join(only_prod)})。"
            "⇒ **两边不是同一份结定义, 而且是双向差异, 不是包含关系。** "
            "G-K1 的一致性是**闸这台仪器**的一致性。"),
        "★★★what_it_licenses_and_what_it_does_not": {
            "仍成立": "「九结分类学能被一组独立模型以一致的分布标注出来」—— 这是一次正当的信度研究, 本发现不动摇它。",
            "★不成立": ("「G-K1 通过 ⇒ 生产 s2 分类器可靠」。生产**看不到**决策树/负例/锚例, "
                       "只看到 signature+typical_codes+behavior[:60]+family+levers。"),
            "★★★precision_i_nearly_got_wrong": (
                "★ 我差点写成「生产是**未被测量**的一台仪器」—— **那是错的, 已改**。"
                "生产分类器的 **test-retest**(同稿 8 次重跑)**测过**: "
                "tests/data/phase2/k1_reliability_verdict.json 判 **FAIL** —— "
                "四项判据过 2 项(top-1 一致 8/8 ✅), 败在「出现率一致 5/8」与「逐对容差一致 **32.1%**」。"
                "★ 未被测量的是**另一个轴**: 生产字段集下的**跨模型一致性**。"
                "⇒ 正确表述: 生产已有一个 **FAIL** 读数(test-retest), 缺的是跨标注者那一维。"),
            "★★the_two_readings_do_not_contradict_but_the_citation_habit_does": (
                "K1(FAIL) 是 test-retest, G-K1(PASS) 是 inter-model —— **不同的量, 不构成矛盾**。"
                "★★ 但它足以否掉一种引用习惯: **「G-K1 通过」不得被读成「结分类可靠」** —— "
                "在另一个轴上, 生产侧已经有一个**明确的 FAIL**, 而且败得不轻(容差一致 32.1%)。"
                "★ 注: 那次 K1 的 instrument_hash 是 gen4 的 565470cf26c16d01, 现网是 gen6 d4cce4c745f3f991; "
                "manifest 记 gen4 标定对 gen6 仍适用(SCOPE_WIDENINGS 子串自证), 故该 FAIL 未过期。"),
            "★★★but_that_FAIL_is_already_diagnosed_do_not_cite_it_as_an_open_mystery": (
                "★ 引用那个 FAIL 时**必须**带上它的根因, 否则会读成「生产侧有个没查清的大问题」。"
                "tests/data/phase2/k1_rootcause_verdict.json(270 次调用, 四条假设逐条判)已定论: "
                "K1 的 0.40 极差**不是**强度现象, 是**稀有结的点火/不点火**被 median(非零) 编码成 0.0 "
                "后混进极差 —— 与 2026-08-18 的 P1a 根因(support 闸二值化)**是同一个根因**。"
                "★ 判决器已按处方把稀有结排除(k1_reliability_verdict 里 6/9 可评估、occurrence 单列)。"
                "★★ 剩下的 32.1% 是**常火结**上的容差一致率, 而根因分析实测: 常火结的变异"
                "**就是抽样噪声**(n 5→12 的比值中位数 0.592, 纯噪声理论预期 0.645, 几乎正中) "
                "⇒ 那一项在 n=8 上达不到 0.95, 更像是**判据与 n 不匹配**, 不是构念坏了。"
                "★ 本探针不改判 K1 —— 只要求引用它时**别把已诊断的东西说成未解之谜**。"),
            "★★★方向不明 —— 我一开始判错了": (
                "★ 我的第一版写「闸多拿了降歧义材料 ⇒ G-K1 是生产可靠性的**乐观上界**」。"
                "**实测推翻**: 这不是「闸多、生产少」, 是**双向各独占 3 个字段** —— "
                "闸独占 决策树/负例/锚例, 生产独占 family/typical_codes/levers_not_knots, "
                "而后三者同样是降歧义材料(尤其 typical_codes 与 levers 的「结 vs 杠杆」之分)。"
                "⇒ **谁更一致无法从字段清单推断**, 只能实测。"
                "★ 正确的表述只剩一句: **两台仪器的读数不可互相引用**, 方向未知。"),
        },
        "★the_suspend_fix_consequence": (
            "★★ 直接后果: 改 `suspend.negative_examples_prompt` **只改闸, 不改生产** —— "
            "instrument_hash 实测不变(d4cce4c745f3f991)。"
            "⇒ 那条修法即使 C1~C4 全过, 也**修不到生产分类器的 suspend 判定**。这必须写在结论里, 不能默认读者知道。"),
        "★what_this_probe_cannot_say": (
            "★ 它只比**字段是否出现**, 不比措辞、顺序、任务形态(闸要带权分布≤3个≥0.1; 生产要完整 schema)。"
            "⇒ 「字段一致」也不等于「同一台仪器」。本探针给的是**差异的下界**, 不是全貌。"),
    }
    p = ROOT / "tests/data/gate_vs_production_prompt_gap.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("✏️", p.relative_to(ROOT))
    for k, v in f.items():
        print(f"  {k:20s} 生产={'✅' if v['生产s2'] else '❌'}  闸={'✅' if v['验收闸'] else '❌'}")
    print(f"\n★ 只有闸看得到: {only_gate}")
    print(f"★ 只有生产看得到: {only_prod}")


if __name__ == "__main__":
    main()
