#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合同空缺: 「已决定但尚未取得」这一格, 九结**没有一个**能满足其必要条件。

★ 零 API。由冻结合同的 hard_discriminant 逐结推出。

★ 起因: 上线配置在这一格上被判 3 个 display 违例。我原以为问题是「模型不遵守规则」,
  逐结核完发现: **合同在这一格上没有归宿** —— 模型是在九个都不合适的盒子里被迫挑一个。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
K = {k["key"]: k for k in TAXO["knots"]}

CELL = "已决定但尚未取得(已锁定型号/已作出购买决定, 但因发薪日/预约/福利周期/发货而尚未拿到)"
TEXTS = [
    "Settled on the Oticon. Just holding off till payday to actually order it.",
    "Made the call — going Phonak. Waiting on my audiologist appointment to get them fitted.",
    "I've picked the Costco ones. Just need to wait for my next day off to go in.",
    "Decision's made, it's the Widex. Sitting on it until the new model ships so I get the discount.",
    "Locked in on the Phonak. Won't be ordering until next spring when my benefits reset.",
    "Going with the Oticon for sure. Just not until after the holidays for budget reasons.",
]

VERDICT = {
 "pain_seek": ("FAIL", "落点意图要求「描述症状/场景/已试步骤并**求可行解**」。六条**全无求解请求**, 也不描述待解症状。"),
 "injustice": ("FAIL", "要求「存在明确的**归责对象**且诉求是问责或讨说法, 情绪带愤慨」。六条全无。"),
 "belong":    ("FAIL", "要求「落点意图=确认我和你们是一类人(自报身份/呼应他人经历以入群)」。六条全无。"),
 "audit":     ("FAIL", "**二值前置**「文本里必须有直接指向你/某个具体的人的质询句」。六条全无 ⇒ 合同明写「没有 → 不是 audit」。"),
 "suspend":   ("FAIL", "要求「决策被**明确悬置**」。六条首句均显式声明**已决定**(Settled/Made the call/I've picked/Decision's made/Locked in/for sure)。"),
 "inertia":   ("FAIL", "要求「明知应行动而**明确表示不行动/维持现状**」。六条**都表明将行动**(将下单/将配机), 方向相反。"),
 "display":   ("★待复核", "★★★ 2026-09-10 离线复核**撤销此条**: 合同是「已拥有**或**已经历」的**析取**, "
                       "文本正面否定了第一支(尚未取得), 但对第二支**沉默** —— **沉默不是否定**; "
                       "合同也**没有**为「已经历」立二值前置。⇒ 依据的是**文本外事实的证据缺席**, **推不出**。"
                       "(原推导保留:) 要求「谈论对象是**自己已拥有或已经历**的」。六条**都尚未取得**。"
                       "★ 且 display 自己的条文明写「若谈的是**期望中未得之物**→itch」—— **合同把这一格路由到 itch**。"),
 "itch":      ("FAIL", "★★★ 合同把它路由过来了, 但 itch 自己的必要条件**排除它**: "
                       "itch 要求「**不采取行动**不问价不求购买路径」, 而六条**都已锁定型号并计划购买**。"
                       "⇒ **display → itch 是一条断掉的路由**。"),
 "reward":    ("FAIL(经两步)", "**二值前置**「必须有致谢句或闭合句(thanks/that helps/问题解决了/就这样吧)」—— "
                       "举的四个例子**全是会话性闭合**, 而六条给的是**决策性声明**, 是否算闭合句**本身就未定**。"
                       "★ 但**即使勉强算满足**, 合同下一句立刻说「满足前置后再看: 若同时含**型号**/参数/步骤/时间线/体感细节 → "
                       "**display 而非 reward**」—— 六条**全部含型号**(Oticon/Phonak/Costco/Widex) ⇒ 合同**再次把它路由到 display**, "
                       "而 display 已 FAIL。⇒ **reward 这条路走不通, 且走不通的方式是回到已经失败的那一格**。"),
}


def build():
    fails = [k for k, (v, _) in VERDICT.items() if v.startswith("FAIL")]
    return {
        "block": "CONTRACT_GAP_DECIDED_NOT_OBTAINED",
        "★zero_api": "只读冻结合同的 hard_discriminant 逐结推导, 零调用。",
        "格": CELL, "涉及用例": len(TEXTS), "文本": TEXTS,
        "★★★结论": (
            f"九结中 **{len(fails)}/9** 判 FAIL —— **但 display 一格已被下调为「待复核」**(见下), "
            "故「合同对这一格完全没有归宿」这个更强的主张**当前不成立**, "
            "只能说「**除 display 的对象域问题待复核外, 其余八结的必要条件均不满足**」。"),
        "★★★★★2026-09-10 离线复核后_空缺主张**撤回**": (
            "复核结论: 合同**没有**限定 display 的对象域, 「已经历」那一支**否不掉**。"
            "⇒ **display 可能正是这一格的归宿** ⇒ 「九结全不满足 / 合同没有归宿」这个主张 **撤回**。"
            "★ 现在能说的只有: **合同对 display 的对象域欠定**, 这一格归不归 display **要 owner 定**。"
            "★★ 那条「display→itch 断掉的路由」也随之降级: 它只在「对象域限定为物」这一读法下成立。"),
        "★★★★web-GPT第八轮下调": (
            "「已拥有**或**已经历」是**析取**; 我只否定了第一支。若 display 的对象域经复核确实限定为"
            "「产品/使用体验」且六条不满足, 空缺主张恢复; 若「已经历」可覆盖「已完成的选购过程」, "
            "**display 就是这一格的归宿, 空缺不存在**。⇒ **这一条现在是待复核, 不是已确立。**"),
        "逐结": {k: {"判": v, "理由": r} for k, (v, r) in VERDICT.items()},
        "★★★合同内部有一条断掉的路由": (
            "display 的条文说「若谈的是**期望中未得之物**→itch」; "
            "itch 的条文说「**不采取行动**不问价不求购买路径」。"
            "这一格**既是未得之物**(满足 display 的转出条件), **又已采取行动**(不满足 itch 的转入条件) ⇒ "
            "**转出去了, 但那一头不接**。这不是模型的问题, 是**合同的问题**。"),
        "★★★这改变了「3 个 display 违例」的性质": (
            "我原来的读法是「规则已在 prompt 里, 模型仍不遵守」。"
            "逐结核完后更准确的读法是: **模型被要求在九个都不合适的盒子里挑一个**。"
            "★ 违例判定**仍然成立**(display 的必要条件确实不满足, 断言没推错); "
            "但**归因**要改: 不是「模型无视规则」, 而是「**合同在这一格上无解**」。"),
        "★合同其实允许弃权": (
            "ABANDONMENT: `empty_knots_is_abstain_v1` —— `{\"knots\": []}` 是**合法弃权**。"
            "⇒ 在合同下, 这六条的**可辩护行为可能是弃权**。"
            "★ 但生产 prompt **从未告诉模型**「没有任何结的必要条件成立时应当弃权」 —— "
            "它只说「只列 intensity > 0 的结; 没有迹象的结不要列」, 那是**关于强度**的话, 不是**关于判别式不满足**的话。"),
        "★★不产生的东西": [
            "**不产生**「这六条正确答案是弃权」—— 那需要 owner 的规范决定, 与「仅收藏」同类",
            "**不产生**「模型没错」—— 违例判定成立, 只是归因改了",
            "**不产生**「该给这一格新立一个结」—— 增结是重大本体论改动, 归 owner",
            "**不产生**「历史悬置_现已决定 那四条也有这个问题」—— 那四条**已购买** ⇒ display 的拥有条件满足, **无空缺**",
        ],
        "★与「仅收藏」是同一族": (
            "两者都是**合同在某一格上判不出来**: 「仅收藏」缺的是「证据不足时怎么办」的回退规则; "
            "这一格缺的是**一个能容纳它的结**(或同样的回退规则)。"
            "⇒ 建议**并入同一份交办件**, 不要让 owner 分两次做同型决定。"),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
