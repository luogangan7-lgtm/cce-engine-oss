#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产 P 到底收没收到 suspend 的**必要条件** —— 零 API, 纯现算。

★ 这个探针存在的理由:
  2026-09-09 我把「仅收藏被判 suspend」定性为「**违反既有必要条件**」。
  但那个必要条件(hard_discriminant 里的「附带犹豫理由」)在 taxonomy_field_reach_ledger
  里早就标着 **NEITHER —— 谁都收不到**。账本是我自己建的, 事实一直在上面,
  **我却没拿它去推翻建立在它之上的结论**。
  ⇒ 这个探针把那条连线**钉成闸**, 让同型错误下次直接判红。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
SRC = (ROOT / "scripts/cce_knot_classify.py").read_text(encoding="utf-8")


def prod_stage2_fields():
    """生产 stage2 的 knots_brief 实际取了 taxonomy 的哪些键 —— 从源码现读, 不靠记忆。"""
    m = re.search(r"def _build_stage2_prompt.*?knots_brief\s*=\s*(.*?)\n\s{4}levers", SRC, re.S)
    assert m, "★ 找不到 _build_stage2_prompt 的 knots_brief 构造 —— 源码结构变了, 这个探针失效"
    blob = m.group(1)
    return sorted(set(re.findall(r"k\[['\"](\w+)['\"]\]", blob))), blob


def suspend_line():
    k = [x for x in TAXO["knots"] if x["key"] == "suspend"][0]
    return (f"- {k['key']}({k['name']}|{k['family']}): 签名={json.dumps(k['signature'], ensure_ascii=False)}; "
            f"典型codes={json.dumps(k['typical_codes'], ensure_ascii=False)}; 行为={k['behavior'][:60]}")


def truncated_behaviors():
    """behavior[:60] 是**硬编码截断**。哪些结被切掉了内容?"""
    out = {}
    for k in TAXO["knots"]:
        b = k["behavior"]
        if len(b) > 60:
            out[k["key"]] = {"len": len(b), "★被丢掉": b[60:]}
    return out


def all_nine_knots_map():
    """★ 缺失不是 suspend 一处 —— **九个结的 hard_discriminant 全部不送达**。
    这张表是给 owner 判「换代值不值」的规模依据。"""
    rows, binary_gates, shared = [], [], {}
    for k in TAXO["knots"]:
        hd = k["hard_discriminant"]
        rows.append({"key": k["key"],
                     "送达生产的行为例示": k["behavior"][:60],
                     "★不送达的判别式": hd})
        if "前置(二值)" in hd:
            binary_gates.append({"key": k["key"], "★这是二值前置闸": hd[:90]})
    for token in ("收藏不买", "收藏", "比价", "明确不动"):
        owners = [k["key"] for k in TAXO["knots"] if token in k["behavior"]]
        if len(owners) > 1:
            shared[token] = owners
    return rows, binary_gates, shared


def itch_vs_suspend_what_production_still_has():
    """★ 反向自查: **不要过度声称**。生产虽收不到判别式, 但仍收到 signature ——
    它在 itch/suspend 之间**确实有区分度**。必须核完再说话。"""
    K = {k["key"]: k for k in TAXO["knots"]}
    a, b = K["itch"]["signature"], K["suspend"]["signature"]
    diff = {kk: {"itch": a[kk], "suspend": b[kk]} for kk in a if a[kk] != b[kk]}
    return {
        "signature 不同的键": diff,
        "★所以不能说": "**不能**说「生产手里没有任何区分信息」—— signature 6 个键里有 5 个不同。",
        "★★能说的是": (
            "生产拿到的区分信息只有 **appraisal 状态描述**(coping=不确定 vs 中; target_layer=consumption_goal vs identity), "
            "**没有把它转成可在文本上核验的判据**。hard_discriminant 的贡献恰恰是那次转换 —— "
            "「**附带犹豫理由**」是一条**文本可观察**的要求, 而「coping=不确定」要模型去**推断作者心理状态**。"
            "⇒ 缺的不是「信息」, 是**把构念判别转成文本判据的那一步**。"
        ),
    }


def build():
    fields, blob = prod_stage2_fields()
    line = suspend_line()
    k = [x for x in TAXO["knots"] if x["key"] == "suspend"][0]

    hd = k["hard_discriminant"]
    ne = k["negative_examples_prompt"]
    # 必要条件的字面片段 —— 在生产实际拼出的那一行里搜
    NEED = "附带犹豫理由"
    LICENSE = "收藏不买"

    return {
        "block": "NECESSARY_CONDITION_REACH",
        "★zero_api": "读 taxonomy + 读 prompt 构造器源码 + 现拼那一行, 零调用。",
        "生产stage2实际取的taxonomy键": fields,
        "★生产对suspend实际看到的整行": line,
        "★★★必要条件是否送达": {
            "必要条件原文(hard_discriminant)": hd,
            "关键合取项": NEED,
            "在生产那一行里出现?": NEED in line,
            "hard_discriminant 字段被生产取用?": "hard_discriminant" in fields,
            "negative_examples_prompt 被生产取用?": "negative_examples_prompt" in fields,
            "决策树被生产取用?": "decision_tree" in SRC or "DECISION_TREE" in SRC,
        },
        "★★★许可条件是否送达": {
            "behavior 里的行为例示": LICENSE,
            "在生产那一行里出现?": LICENSE in line,
        },
        "★★★结论_按web-GPT第六轮的替换措辞": (
            "生产构造器将「收藏不买」作为**行为例示**发送给分类器, 但**未发送**相关必要条件及排除规则。"
            "已确认存在**规范性条款未送达生产执行路径**的缺陷。"
            "现有证据**不足以**将争议输出归因为模型违反已收到的必要条件; "
            "具体文本是否不符合完整合同, **须另行判断**。"
        ) if (LICENSE in line and NEED not in line) else "★ 前提不成立, 结论不适用 —— 重新检查",
        "★★★我原来写过头的话_已撤回": (
            "原文: 「P 没有违反一条它从未收到的条件, 它是按收到的材料判的」。"
            "★ 作为对**模型**的**指令遵循**归因, 这句是对的; "
            "作为对**整个生产系统**的**符合性**判断则**过强** —— "
            "**外部规范可以约束系统, 即使系统的某个内部组件没有收到它。**"
        ),
        "★★★三分不许合并": {
            "生产实现没有完整执行其声称采用的合同": "**成立**(源码 + 出站请求见证)",
            "模型收到必要条件后仍未遵守": "**撤回** —— 送达前提不成立",
            "某个输出不符合外部规范中的必要条件": "**不因未送达而自动撤销**, 须独立证明该文本确实不满足条件",
        },
        "★方法已被取代": (
            "本探针从**构造器源码反推**「它读了哪些键」—— GPT 指出这样**被遗漏的字段会一起从检查清单消失**, "
            "我能发现 hard_discriminant **只是因为事先就知道要看它**。"
            "⇒ 改用 scripts/cce_rule_delivery_completeness.py(**必需集合从规范端生成**), "
            "它随即查出本探针**结构上不可能查到**的两条: definition_of_knot 与 identity_criterion **两台仪器都没收到**。"
            "本探针保留, 但**降级为交叉核对**, 不再是主判据。"
        ),
        "★★这不是新事实": (
            "taxonomy_field_reach_ledger 早就把 hard_discriminant 标成 NEITHER。"
            "**事实一直在我自己建的账本上, 我没拿它去推翻建立在它之上的结论。** "
            "这是本轮的元教训, 比这条结论本身更值钱。"
        ),
        "★★另一处独立缺陷_硬编码截断": {
            "位置": "_build_stage2_prompt 里的 behavior[:60]",
            "被截断的结": truncated_behaviors(),
            "★为什么今天才看见": "我今天刚建的「零硬编码截断」闸只扫探针脚本, **没扫生产 prompt 构造器**。",
            "★★★但真正的问题不是覆盖面, 是**闸的定义本身太窄**(GPT)": (
                "把 60 换成变量、或换成 token 裁剪, 那种闸就放行了。"
                "闸该查的是**内容是否完整送达**, 不是**代码里有没有出现字面量 60**。已由 "
                "cce_rule_delivery_completeness 的 PARTIAL 判定取代。"
            ),
            "★这是**独立的第二个缺陷**, 不与「条款未进路径」合并关闭": (
                "遗漏 hard_discriminant = 条款**没进**生产路径; behavior[:60] = **已进入**路径的字段**被损坏**。"
                "修前者不会自动修后者 ⇒ 两个缺陷 ID、两个回归见证, 共用一个上位完整性闸。"
            ),
        },
        "★★★缺失的规模_九个结全都缺": {
            "逐结": all_nine_knots_map()[0],
            "★★其中是**二值前置闸**的(最强形态的必要条件, 同样不送达)": all_nine_knots_map()[1],
            "★★多个结共享同一行为例示(判别式不送达时无从分辨)": all_nine_knots_map()[2],
        },
        "★★★不要过度声称_itch与suspend的自查": itch_vs_suspend_what_production_still_has(),
        "★本探针不产生的东西": [
            "不产生「应当把 hard_discriminant 加进生产 prompt」的授权 —— 那会改 s2_prompt_sha256 ⇒ **换代**, 历史读数全部不可比, 需 owner 决定",
            "不产生「仅收藏该判什么」的答案 —— 材料没送达只说明**归因错了**, 不说明正确类别是什么",
            "不产生「生产分类器是对的」—— 只说明它没违反一条它看不到的规则",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
