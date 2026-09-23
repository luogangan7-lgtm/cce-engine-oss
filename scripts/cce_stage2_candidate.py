#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产 stage2 prompt 的**候选**构造器 —— 不替换生产, 不被生产路径引用。

★ 存在的理由: 实测生产 stage2 只送 key/name/family/signature/typical_codes/behavior[:60],
  判定所需的**必要条件/排除条件/本体论定义/决策树**一概不送(见 cce_rule_delivery_completeness)。

★★★ 设计原则(来自 web GPT 第六轮):
  · 送的是**决策所需规则**, 不是把所有背景与元数据无差别塞进每次调用
  · behavior **完整保留**并**明确标注是例示, 不得自动越过必要条件**
  · **超预算显式阻断**(PROMPT_BUDGET_EXCEEDED), 不得自行裁尾/删负例/删决策树

★★★ 组件是**可分别开关**的, 不打包。原因见 INDEPENDENCE_COST:
  加决策树会让**生产与验收闸共享同一份判定顺序** ⇒ 闸对生产的一致性判决
  会有一部分变成同义反复。这是**要 owner 权衡的代价**, 不该被我捆在一次交付里。
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★ 预算: 超了就**阻断**, 不裁尾。数值是**保守占位**, 需 owner 按真实上下文窗定。
PROMPT_CHAR_BUDGET = 24000


class PromptBudgetExceeded(RuntimeError):
    """★ 显式阻断 —— 绝不静默裁尾。裁尾正是本项目要修的那个缺陷。"""


COMPONENTS = {
    "ontology":        "definition_of_knot + identity_criterion —— 「什么算一个结」",
    "discriminant":    "knots[].hard_discriminant —— **必要条件/判别式**, 本次缺陷的核心",
    "negative":        "knots[].negative_examples_prompt —— 排除条件",
    "full_behavior":   "behavior **不截断** + 显式标注为例示",
    "decision_tree":   "annotation_protocol.decision_tree_prompt —— 判定顺序与优先关系",
}

INDEPENDENCE_COST = (
    "★★★ `decision_tree` 这一项**有独立性代价**: 验收闸 G 的判定顺序**就是**这份 decision_tree_prompt。"
    "把它同时送进生产 P 之后, G 与 P **共享同一份判定顺序** ⇒ "
    "「G 与 P 一致」这件事有一部分变成**同义反复**, G 作为独立检查的效力下降。"
    "⇒ 本项**默认关闭**, 由 owner 显式决定是否开, 并在开启时同步声明 G 的判决口径变化。"
    "(其余四项没有这个问题: 它们此前 G 也没有。)"
)


def build(taxo, text, s1, components=("ontology", "discriminant", "negative", "full_behavior"),
          budget=PROMPT_CHAR_BUDGET):
    on = set(components)
    unknown = on - set(COMPONENTS)
    if unknown:
        raise ValueError(f"未知组件 {sorted(unknown)} —— 组件表是规范端的, 不许临时加")

    lines = []
    for k in taxo["knots"]:
        seg = (f"- {k['key']}({k['name']}|{k['family']}): "
               f"签名={json.dumps(k['signature'], ensure_ascii=False)}; "
               f"典型codes={json.dumps(k['typical_codes'], ensure_ascii=False)}")
        # ★ 完整 behavior, 且**当场标注它是例示** —— 不标注等于默许它被当判定条件
        beh = k["behavior"] if "full_behavior" in on else k["behavior"][:60]
        seg += f"\n    行为例示(**仅例示, 不是判定条件**)={beh}"
        if "discriminant" in on:
            seg += f"\n    ★判别式(**必要条件, 优先于行为例示**)={k['hard_discriminant']}"
        if "negative" in on:
            seg += f"\n    ★不用于(排除条件)={k.get('negative_examples_prompt', '')}"
        lines.append(seg)
    knots_brief = "\n".join(lines)

    head = ""
    if "ontology" in on:
        head = (f"【结的定义】{taxo['definition_of_knot']}\n"
                f"【同一性判据】{taxo['identity_criterion']}\n\n")

    tree = ""
    if "decision_tree" in on:
        tree = ("\n【★判定顺序(决策树, 逐级检查)】\n"
                + "\n".join(taxo["annotation_protocol"]["decision_tree_prompt"]) + "\n")

    levers = "、".join(taxo["levers_not_knots"].keys())
    priority = (
        "\n【★★★ 判定优先关系(硬规则)】\n"
        "1. **判别式是必要条件**: 判别式不成立 ⇒ **不得**判该结, 无论行为例示命中得多像。\n"
        "2. **行为例示不是充分条件**: 「这个人做了该结的人常做的事」**不能**单独支撑该结。\n"
        "3. 判别式里的**合取项要逐项独立满足** —— 同一处文本证据可同时支持两项, "
        "但**每一项都必须真的被支持**, 不能靠改述另一项来充数。\n"
    )

    prompt = f"""你是 CCE 结分类器。「结」= 人身上预装的动机配置(四层的具名绑定),满足: 人侧预装、有保质期(约75天)。
与「杠杆」严格区分(杠杆=内容侧制造、瞬时: {levers})。

{head}【九结(冻结 v{taxo['version']})】
{knots_brief}
{tree}{priority}
【补充判定槽】attribution(归责): self/other_agent/system/none。target_layer(闸门对象): consumption_goal/epistemic_trust/identity/fairness。
【多结】一个人可同时持多结(如 归属+惯性)。
【★强度独立打分, 不要归一】对每个结独立给 intensity ∈ [0,1]:
  0 = 该结在这段内容里完全没有迹象; 1 = 强烈且明确。
  **不同结的 intensity 互相独立, 不要求加起来等于 1**。
  只列 intensity > 0 的结; 没有迹象的结不要列。

【第 1 级引擎读出(参考,不是真值)】
四层首位: {json.dumps(s1['tops'], ensure_ascii=False)}
appraisal: {json.dumps(s1['appraisal'], ensure_ascii=False)}

【待分类内容】
{text}

只输出 JSON:
{{"knots":[{{"key":"<九结key之一>","intensity":0.0,"evidence_quote":"<原文引句>",
  "signature":{{"congruence":"","need_status":"","coping":"","time":"","attribution":"","target_layer":""}},
  "desire_code":"","need_code":"","freshness_days_hint":0}}],
 "levers_present":["内容里出现的杠杆(若有)"],"notes":"<一句话>"}}"""

    if len(prompt) > budget:
        raise PromptBudgetExceeded(
            f"候选 prompt {len(prompt)} 字 > 预算 {budget} —— **显式阻断, 不裁尾**。"
            f"要么提高预算(需 owner 定, 且要重新验收), 要么减少组件(要说明减了什么、为什么)。"
        )
    return prompt


if __name__ == "__main__":
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    s1 = {"tops": {}, "appraisal": {}}
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_knot_classify as C
    cur = C._build_stage2_prompt(taxo, "SAMPLE", s1)
    out = {"现行生产": len(cur)}
    for combo in (("ontology",), ("discriminant",), ("negative",), ("full_behavior",),
                  ("ontology", "discriminant", "negative", "full_behavior"),
                  ("ontology", "discriminant", "negative", "full_behavior", "decision_tree")):
        out["+".join(combo)] = len(build(taxo, "SAMPLE", s1, combo))
    print(json.dumps({"prompt 字数": out, "★默认组件": ["ontology", "discriminant", "negative", "full_behavior"],
                      "★decision_tree 默认关闭的理由": INDEPENDENCE_COST,
                      "预算": PROMPT_CHAR_BUDGET}, ensure_ascii=False, indent=1))
