#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产规则送达完整性闸 —— 按 web GPT 第六轮给的四条机械条件重建。

★ 它替代我先前那个探针的**方法**, 不只是扩大范围。GPT 指出的致命点:

  「**必需集合从规范端生成。** 不能从构造器『实际读取了什么』反推应该送达什么,
    否则**被遗漏的字段也会从检查清单里消失**。」

  我先前的 cce_necessary_condition_reach 正是从构造器源码反推 —— 它能发现
  hard_discriminant 缺失, **只是因为我事先就知道要去看它**。换一个我没想到的字段, 它一样漏。

★ 同样按 GPT 的要求, 这里也**不再把「零硬编码截断」当闸**:
  把 60 换成变量、或换成 token 裁剪, 那种闸就放行了。闸要查的是**内容是否完整送达**,
  不是**代码里有没有出现字面量 60**。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))

# ── ① 必需集合**从规范端生成** ────────────────────────────────────────────
# 规范端 = knot_taxonomy 本身。凡是**判定所需**的条款, 逐条列出并给出它为什么必需。
# ★ 这张表不是「构造器读了什么」, 是「判一个结需要什么」。
#   新增字段若属判定所需, 必须显式加进来 —— 空集合会被 test 判红(防 all([]) 空过)。
REQUIRED_PER_KNOT = {
    "signature":          "appraisal 四层签名 —— 构念定义本身",
    "behavior":           "行为例示 —— **仅例示**, 不得越过必要条件",
    "hard_discriminant":  "**判别式/必要条件** —— 把构念区分转成文本可核验的判据",
}
REQUIRED_GLOBAL = {
    "definition_of_knot": "结的定义 —— 决定什么算一个结",
    "identity_criterion": "同一性判据 —— 决定两实例是否同结",
}


def _outbound(builder):
    """② **检查最终生产请求**, 不是探针仿造的 prompt。
    用真实构造器 + 真实序列化路径, 在出站边界接一个**不发网络请求**的接收器。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_knot_classify as C
    fake_s1 = {"tops": {}, "appraisal": {}}
    return builder(C, TAXO, "PROBE_TEXT_DO_NOT_SEND", fake_s1)


def production_stage2_request():
    def b(C, taxo, text, s1):
        return C._build_stage2_prompt(taxo, text, s1)
    return _outbound(b)


def gate_material():
    """★★★ 2026-09-11 根因修法: 原先这里 `except KeyError: return None` ——
    没有 MINIMAX_API_KEY 时**整个验收闸一侧静默降级成 UNKNOWN**, 送达审计只剩一半,
    而调用方看到的是一份**外观完整**的表。**这正是我为 accuracy/ 修过、却没推广开的同一个缺陷。**

    ⇒ 改走已建好的离线装置(先设假环境变量再 import), 并**在网络绊线里完成加载** ——
      既拿到真实的闸材料, 又就地证明加载过程**一次连接都没新建**。降级分支**删除**, 不保留。
    """
    sys.path.insert(0, str(ROOT / "probes"))
    import accuracy_offline_harness as H
    with H._Tripwire() as tw:              # ★ 加载期间任何新建连接 = 直接抛, 不是警告
        R = H.load()
    assert not tw.tripped, f"★★★ 读闸材料时发生了网络连接: {tw.tripped}"
    return R.KNOT_BRIEF + "\x00" + R.DECISION_TREE + "\x00" + R.NEGATIVE_EXAMPLES + "\x00" + R.DIST_TMPL


def _delivered(value, blob):
    """③ **逐条校验内容完整性** —— 比对**完整值**, 不是字段名, 也不是开头子串。
    返回 FULL / PARTIAL(送了一部分, 静默损失) / MISSING。"""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    if value in blob:
        return "FULL"
    # 前缀命中但整值不在 ⇒ 被截断/改写 = **静默损失**, 与完全没送达要分开记
    for cut in range(len(value) - 1, 9, -1):
        if value[:cut] in blob:
            return f"PARTIAL(送达 {cut}/{len(value)} 字, **丢失**: {value[cut:][:40]!r})"
    return "MISSING"


def build():
    prod = production_stage2_request()
    gate = gate_material()
    rows = []
    for k in TAXO["knots"]:
        for field, why in REQUIRED_PER_KNOT.items():
            rows.append({
                "对象": k["key"], "必需条款": field, "为什么必需": why,
                "→生产": _delivered(k[field], prod),
                "→验收闸": _delivered(k[field], gate),
            })
    for field, why in REQUIRED_GLOBAL.items():
        rows.append({
            "对象": "(全局)", "必需条款": field, "为什么必需": why,
            "→生产": _delivered(TAXO[field], prod),
            "→验收闸": _delivered(TAXO[field], gate),
        })

    miss_p = [r for r in rows if r["→生产"] != "FULL"]
    miss_g = [r for r in rows if r["→验收闸"] != "FULL"]
    partial = [r for r in rows if "PARTIAL" in r["→生产"] or (gate and "PARTIAL" in r["→验收闸"])]

    return {
        "block": "RULE_DELIVERY_COMPLETENESS",
        "★zero_api": "调真实构造器拼出**最终请求文本**后就地比对, **一次网络请求都不发**。",
        "★★★方法上的更正": (
            "必需集合**从规范端(knot_taxonomy)生成**, 不从构造器反推。"
            "先前的探针从构造器源码反推「它读了哪些键」—— 那样**被遗漏的字段会从检查清单里一起消失**, "
            "我上次能发现 hard_discriminant, **只是因为我事先就知道要看它**。"
        ),
        "必需集合(规范端)": {"每结": REQUIRED_PER_KNOT, "全局": REQUIRED_GLOBAL},
        "逐条": rows,
        "★★★未完整送达生产": [{k: r[k] for k in ("对象", "必需条款", "→生产")} for r in miss_p],
        "★★★未完整送达验收闸": [{k: r[k] for k in ("对象", "必需条款", "→验收闸")} for r in miss_g],
        "★★静默损失(送了一半)": [{k: r[k] for k in ("对象", "必需条款", "→生产", "→验收闸")} for r in partial],
        "★★★两台仪器要分开说_不许折叠成「谁都收不到」": (
            "GPT 指出我把两个主体折叠了。精确说法是: "
            "**hard_discriminant 这个字段两台都收不到**; 但**验收闸经决策树第4条拿到了它的压缩版**"
            "(「明确悬置决策(还没定/再看看+**犹豫理由**)」), **生产连压缩版都没有**。"
            "⇒ 不是「谁都收不到」, 是「**两台的缺口不一样大**」。"
        ),
        "★我给 web GPT 的前提里有一处是错的": (
            "我在提问里写「G = 验收闸…看**完整合同**: …hard_discriminant…」—— **不成立**。"
            "闸拿到的是决策树里的压缩版, 不是该字段。我据此给 6 个盲读者的也是**两台仪器都没有的合同**。"
            "⇒ 那一轮实验测的合同**不是任何一台在用的合同**。(该轮已因别的理由作废, 这条是**第三个**独立理由。)"
        ),
        "★本闸不产生的东西": [
            "**不产生**「模型正确理解并遵守了这些规则」 —— 它只证明我控制的**出站边界**上规则完整。行为验收是另一件事。",
            "**不产生**「必需集合已经完整」 —— 集合是我列的; 新增判定所需字段必须显式加入, 否则照样漏。",
        ],
    }


if __name__ == "__main__":
    r = build()
    print(json.dumps(r, ensure_ascii=False, indent=1))
