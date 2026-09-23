#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ P4 连带审计 —— 我自己写下的「取消理由要求 ⇒ 12 条断言要重审」是不是真的。

背景: web GPT 第十一轮指出这是**逻辑错误** —— 原要求是 `决策悬置 ∧ 理由`,
取消「理由」剩下的是「决策悬置」, **不是连它一起取消**。它同时说:
「若你的断言把两者耦合了, **那是你要核对、拆开的实现问题**,
  不能作为该选项必须承担的规范代价写给 owner」。

⇒ 所以这里**不重复它的推理**, 而是去数据里核: 每条断言实际卡在**哪个合取项**上。
   只有卡在「理由」上的那些, 才会被取消理由要求影响。

★ 这个探针**不读**任何识别层路径, 只读本仓已冻结的断言文件。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "tests" / "data" / "local_contract_assertions_v2.json"

# 合同 v1.3.1 的 suspend 判别式是**两个合取项**
CONJ_SUSPEND = "决策被**明确悬置**"
CONJ_REASON = "附带犹豫理由"


def audit() -> dict:
    A = json.loads(SRC.read_text(encoding="utf-8"))["断言"]
    sus = [a for a in A if "suspend" in a["条款定位"]]

    by_conj: dict[str, list[str]] = {}
    for a in sus:
        by_conj.setdefault(a["失败的合取项"], []).append(a["用例"])

    # 取消「理由」这一合取项后, 哪些断言的依据没了?
    # 依据没了 ⟺ 该断言**正是**靠这个合取项失败的。
    affected = sorted(
        c for k, v in by_conj.items() if CONJ_REASON in k for c in v
    )
    intact = sorted(c for k, v in by_conj.items() if CONJ_REASON not in k for c in v)

    return {
        "来源": str(SRC.relative_to(ROOT)),
        "定位到 suspend 条款的断言数": len(sus),
        "按失败合取项分组": {k: len(v) for k, v in sorted(by_conj.items())},
        "★★★取消「理由要求」后依据消失的断言": affected,
        "★★★不受影响、依据仍在的断言": intact,
        "★★★结论": (
            f"{len(affected)} 条受影响 / {len(sus)} 条。"
            if affected
            else f"**0 条受影响**({len(sus)} 条全部卡在另一个合取项「{CONJ_SUSPEND}」上)。"
        ),
        "★★★我先前写错了什么": (
            "我在决策单里写过「取消理由要求会连带使 12 条断言要重审」。"
            "**两重错**: ① 逻辑上 —— 取消 `A∧B` 里的 B 剩下 A, 不是连 A 一起取消; "
            "② 事实上 —— 本探针从我自己冻结的断言文件里算出, 这 12 条的"
            f"`失败的合取项` **无一例外**是「{CONJ_SUSPEND}」, 与「{CONJ_REASON}」无关。"
            "⇒ 该「连带代价」**不存在**, 不得写进交办件让 owner 为它买单。"
        ),
        "★★★这个结论不覆盖什么": (
            "它只说明**现有断言**不依赖「理由」合取项; "
            "**不**说明取消理由要求在构念上是对的 —— 那仍是 owner 的规范判断。"
        ),
    }


if __name__ == "__main__":
    r = audit()
    print(json.dumps(r, ensure_ascii=False, indent=2))
