"""★★★ 分类学每个字段进不进 prompt —— 台账必须**现算**, 且必须自证判法没错。零 API。

## 为什么要这张表
「改这个字段会不会改变模型行为」此前是**逐个临时查**的, 查漏一个就得到一条假因果。
2026-09-08 一天之内踩了三次:
· 拿 `hard_discriminant`(**两边都不进**)当 suspend 的病因写进诊断
· 差点按「改 negative_examples 要递增 instrument_generation」去换代(它**只进闸**, 不进生产)
· 把「生产是未被测量的仪器」写进文档(它测过, 判 FAIL)
⇒ 做成全字段台账, 改任何字段之前先查这张表。

## ★★ 台账自己也错过两版, 都记下来
· v1: 只取顶层字符串值 + 长度>=4 ⇒ `family`/`levers_not_knots`/`typical_codes` 全被漏判成
  NEITHER —— **漏判方向正是会制造假因果的那个方向**。
· v2: 改用「字面子串」+ 递归 ⇒ 冒出假阳性(`typical_codes` 的键「need」命中签名里的
  `need_status`), 且 `changelog_1_3_0` 因为**逐字引用了决策树原文**被判成 BOTH。
⇒ v3 主判据换成「**prompt 构造器源码里取了哪个键**」, 子串法降为交叉核对、不一致就摆出来。
★ 而 v3 的自校验我第一版又放错了位置(放在 `rows = src_rows` **之前**), 校的是随后被丢弃的
  中间结果 —— **主判据一行都没被检查过**。已挪到之后。
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_TEST_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "probes"))
DOC = ROOT / "tests" / "data" / "taxonomy_field_reach_ledger.json"
# ★ 这七条由 probes/gate_vs_production_prompt_gap.py **独立**核实过(不同实现)
KNOWN = {"knots[].typical_codes": "PROD_ONLY", "knots[].family": "PROD_ONLY",
         "levers_not_knots": "PROD_ONLY", "knots[].negative_examples_prompt": "GATE_ONLY",
         "knots[].signature": "BOTH", "knots[].behavior": "BOTH",
         "knots[].hard_discriminant": "NEITHER"}


def _doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_the_ledger_is_recomputed_not_copied():
    """★ 留档必须与现算一致 —— 否则改了 prompt 构造器, 表会悄悄过时。"""
    import importlib
    import io
    import contextlib
    import taxonomy_field_reach_ledger as L
    importlib.reload(L)
    before = _doc()["per_field"]
    with contextlib.redirect_stdout(io.StringIO()):
        L.main()                       # 它自带自校验; 算错会在落盘前 assert
    after = _doc()["per_field"]
    assert before == after, (
        f"★ 台账与现算不符。有人改了 prompt 构造器却没重跑台账。\n"
        f"差异: { {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)} }")


def test_the_seven_independently_verified_fields_agree():
    """★★ 台账必须复现另一个**不同实现**核实过的七个字段。两法都错到一块的概率低得多。"""
    got = _doc()["per_field"]
    wrong = {k: (got.get(k), w) for k, w in KNOWN.items() if got.get(k) != w}
    assert not wrong, f"★★★ 与独立核实不符(现算 vs 已核实): {wrong}"


def test_hard_discriminant_is_in_the_NEITHER_bucket():
    """★★★ 这一条单列: 它就是那条假因果的来源, 必须永远查得到。"""
    assert _doc()["per_field"]["knots[].hard_discriminant"] == "NEITHER", (
        "★★ hard_discriminant 现在进 prompt 了 —— 若是有意接入, "
        "2026-09-08 那条『它不可能是 suspend 的病因』的更正需要重新评估。")


def test_disagreements_are_shown_not_silently_resolved():
    """★ 两种判法不一致的字段必须**摆出来**, 不许静默择一。"""
    d = _doc()
    k = "★★★两种判法不一致的字段(不静默择一, 摆出来)"
    assert k in d, "★ 不一致清单不见了"
    assert d[k], "★ 不一致清单空了 —— 两法完全一致本身可疑(子串法有已知噪声), 请复核"
    assert "changelog" in json.dumps(d[k], ensure_ascii=False), (
        "★ changelog 类字段不再出现在不一致清单里 —— 它是子串法噪声的典型例证, "
        "没了说明判法变了, 请复核文档说法")


def test_it_says_what_it_is_not():
    """★ 它**不是消融**: 只答字面/源码是否到达, 不答删了读数变不变。这条限度不许删。"""
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "不是消融" in d and "下界" in d, "★ 「这不是消融, 只给下界」的限度声明不见了"
    assert "不拆嵌套" in d and "gate_record" in d, (
        "★★ 粒度限度声明不见了 —— `annotation_protocol` 判 GATE_ONLY 不代表它每个子字段都进 prompt "
        "(同容器里的 gate_record 一个都不进)。拿容器的格子推子字段是本表要防的假因果的变体。")


def test_every_NEITHER_field_is_classified_on_the_second_axis():
    """★★★ 「不进 prompt」不等于「测量无关」—— 每个 NEITHER 都必须有明确归类。

    网页版 GPT 的批评(已接受): changelog 与 hard_discriminant 的语义地位完全不同,
    不该被同一个 NEITHER 标签盖住。第二个轴按
    「规定构念边界 / 影响结果用途 / 均不」分。
    ★ 本轴**人判、可被反驳** —— 本闸只保证「每个都有归类」, **不保证归类是对的**。
    """
    d = _doc()
    blk = d.get("★★★NEITHER_的第二个轴")
    assert blk, "★ 第二个轴被删了 —— 那样 NEITHER 又变回一个笼统标签"
    assert not blk["未归类"], f"★★ 这些 NEITHER 字段没有归类: {blk['未归类']}"
    assert set(blk["分类"]) == set(d["buckets"]["NEITHER"]), "★ 归类表与 NEITHER 桶不一致"
    assert blk["★统计"]["均不"] < len(d["buckets"]["NEITHER"]), (
        "★★ 所有 NEITHER 都被归成「测量无关」了 —— 那正是这个轴要防的懒惰归类")
    assert blk["分类"].get("knots[].hard_discriminant", {}).get("轴") == "规定构念边界", (
        "★★★ hard_discriminant 必须归在「规定构念边界」—— 它不进 prompt(所以拿它解释模型行为是假因果), "
        "但它**是**构念定义的真值。两件事不能混。")


def test_the_no_effect_claim_was_corrected():
    """★ 原表写「NEITHER 一定没影响」—— **说过头了**, 必须是被更正过的版本。"""
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "NEITHER 一定不影响模型的判读行为" in d, "★ 更正后的表述不见了"
    assert "可能影响构念定义与结论的可引用范围" in d, "★ 更正的后半句不见了"


def test_the_ablation_now_measures_the_gate_side_too():
    """★★★ 消融的 `prompt_changed` 曾**只测生产**, 于是把闸上承重的字段判成 INCONCLUSIVE。

    2026-09-07 的分类学消融: `negative_examples_prompt` → prompt_changed=false / INCONCLUSIVE。
    ★ 而 2026-09-09 实测它**改变验收闸的 prompt 且改变读数**(45.0%→12.5%)。
    ⇒ 那条判决是**在一台看不见它的仪器上**做出的。已更正, 并给探针加了闸侧测量。

    ★★ 教训: 一个叫 `prompt_changed` 的字段, 在一个**有两台仪器**的系统里, 是个**会骗人的名字**。
       本仓同族: 「豁免名单里的东西没人再看」「闸比它守的定义还窄」—— 这次是**字段名比它测的东西宽**。
    """
    import importlib
    import sys as _s
    _s.path.insert(0, str(ROOT / "probes"))
    A = importlib.import_module("knot_taxonomy_ablation")
    assert hasattr(A, "gate_materials"), "★★ 消融探针缺 gate_materials —— 闸侧又变成测不到了"
    src = (ROOT / "probes/knot_taxonomy_ablation.py").read_text(encoding="utf-8")
    assert "★gate_prompt_changed" in src, "★ 闸侧测量字段不见了"
    assert "prod_s2_prompt_changed" in src, "★★ `prompt_changed` 必须有带限定的名字"

    abl = json.loads((ROOT / "tests/data/knot_taxonomy_ablation.json").read_text(encoding="utf-8"))
    ne = [r for r in abl["rows"] if r.get("field") == "negative_examples_prompt"]
    assert ne and "★★★verdict_corrected_2026-09-09" in ne[0], "★ 更正记录不见了"
    assert "验收闸上 LOAD_BEARING" in ne[0]["★★★verdict_corrected_2026-09-09"]["★新判"]
    assert "★★★scope_defect_found_2026-09-09" in abl, "★ 作用域缺陷的记录不见了"

    # ★ 现算复核: 删掉该字段, 闸材料确实变
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    import copy
    t = copy.deepcopy(taxo)
    for kn in t["knots"]:
        kn.pop("negative_examples_prompt", None)
    assert A.gate_materials(t) != A.gate_materials(taxo), (
        "★★★ 删掉 negative_examples_prompt 竟然不改变闸材料 —— 更正的前提没了, 请复核")


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_doc"]
    import copy

    bad = copy.deepcopy(_doc())
    bad["per_field"]["knots[].hard_discriminant"] = "BOTH"
    g["_doc"] = lambda: bad
    try:
        test_hard_discriminant_is_in_the_NEITHER_bucket()
        raise SystemExit("★ 反向验证失败: hard_discriminant 改成 BOTH 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_doc"] = saved

    bad2 = copy.deepcopy(_doc())
    bad2["★★★两种判法不一致的字段(不静默择一, 摆出来)"] = {}
    g["_doc"] = lambda: bad2
    try:
        test_disagreements_are_shown_not_silently_resolved()
        raise SystemExit("★ 反向验证失败: 抹掉不一致清单后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_doc"] = saved

    # ★ 灵敏度自证: 台账的自校验**真的会拦**一个错答案
    import taxonomy_field_reach_ledger as L
    real = L._read_by_source
    L._read_by_source = lambda: {"gate": set(), "prod": set()}
    try:
        L.main()
        raise SystemExit("★★ 灵敏度自证失败: 源码判据被清空后台账仍然落盘")
    except AssertionError:
        n += 1
    finally:
        L._read_by_source = real
        L.main()          # 复原正确的产物
    return n


if __name__ == "__main__":
    test_the_ledger_is_recomputed_not_copied()
    test_the_seven_independently_verified_fields_agree()
    test_hard_discriminant_is_in_the_NEITHER_bucket()
    test_disagreements_are_shown_not_silently_resolved()
    test_it_says_what_it_is_not()
    test_every_NEITHER_field_is_classified_on_the_second_axis()
    test_the_no_effect_claim_was_corrected()
    test_the_ablation_now_measures_the_gate_side_too()
    n = _reverse_checks()
    b = _doc()["buckets"]
    b2 = _doc()["★★★NEITHER_的第二个轴"]
    print(f"test_cce_taxonomy_field_reach: OK ("
          f"BOTH {len(b.get('BOTH', []))} · GATE_ONLY {len(b.get('GATE_ONLY', []))} · "
          f"PROD_ONLY {len(b.get('PROD_ONLY', []))} · **NEITHER {len(b.get('NEITHER', []))}** | "
          f"七个字段与独立实现一致 | ★★★hard_discriminant 钉在 NEITHER(那条假因果的来源) | "
          f"两法不一致的字段摆出来不静默择一 | 「不是消融, 只给下界」的限度在 | "
          f"★★★NEITHER 第二个轴: 构念边界 {b2['★统计']['规定构念边界']} · "
          f"结论用途 {b2['★统计']['影响结果用途']} · **真正测量无关仅 {b2['★统计']['均不']}** | "
          f"★★★消融的 prompt_changed 曾**只测生产**(把闸上承重的负例判成 INCONCLUSIVE), 已更正并加闸侧测量 | "
          f"{n} 条反向验证判红(含台账自校验的**灵敏度自证**))")
