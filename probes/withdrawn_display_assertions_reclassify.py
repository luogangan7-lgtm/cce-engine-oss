#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ 把 8 条被**一刀切**撤销的 display 断言逐条重分类。

## 背景
2026-09-10 的离线复核用一条正确的原则撤销了 8 条断言：
  可推导 ⟺ (甲)文本内属性 / (乙)文本内正面反证 / (丙)合同明文的二值前置;
  **不得**依据 (丁) 文本外事实的证据缺席。
撤销理由写的是同一句话，**8 条逐字相同**：「说话人未拥有亦未经历该产品 ⇒ 合取项不满足」。

## 本探针要回答的
那句理由对 8 条**是不是都成立**？—— 它把「未拥有」当成了**从沉默推出的**，
但逐条读原文, **6 条的文本里有正面陈述说它还没被取得**（「to actually order it」「to get them fitted」
「Won't be ordering」…）。**正面说了还没买 ≠ 没提买没买。** 前者是 (乙), 后者才是 (丁)。

## 判据（可操作化, 不是我的读后感）
一条 display 禁判断言落在 (乙) ⟺ **能在原文里指名一个片段**,
该片段**正面陈述**了「取得/配戴/使用尚未发生」。指不出片段 ⇒ 落 (丁) ⇒ 维持撤销。
★ 这条判据就是附件 B 的「**指不出原文片段的推断 = 没有证据**」, 在这里反向用一次。

★ **它依赖 P1**: 只有当 display 的对象域**限定为物**时,「该物尚未取得」才足以否掉合取项;
  若对象域**也允许已完成的选购过程**, 那么「过程已经历」是另一个候选对象, 6 条的反证**不再充分**。
  ⇒ 本探针的结论**以 P1=只含物 为前提**, 这一点写死在输出里。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "tests" / "data" / "local_contract_assertions_v2.json"

# ★ 每条给出**原文片段**(必须逐字出现在文本里, 代码会当场核)与它为什么是正面陈述。
POSITIVE_SPANS = {
    "C_已决定_延后执行_0": ("to actually order it",
                     "「to **actually order** it」—— 正面陈述下单这件事**尚待发生**, 不是没提。"),
    "C_已决定_延后执行_1": ("to get them fitted",
                     "「Waiting on my audiologist appointment **to get them fitted**」—— 正面陈述配机尚未发生。"),
    "C_已决定_延后执行_2": ("wait for my next day off to go in",
                     "「**wait** for my next day off **to go in**」—— 正面陈述尚未到店。"),
    "C_已决定_延后执行_3": ("until the new model ships",
                     "「Sitting on it **until the new model ships**」—— 正面陈述取得被推到某事之后。"),
    "C_★已决定_未来时间词_0": ("Won't be ordering",
                       "「**Won't be ordering** until next spring」—— 显式否定, 最强的一条。"),
    "C_★已决定_未来时间词_1": ("not until after the holidays",
                       "「Just **not until** after the holidays」—— 显式否定(承前省略 ordering)。"),
    # ↓ 这两条**指不出**这样的片段
    "C_明确放弃_0": (None,
                "「Not doing it. I'll manage without.」放弃的是**某个动作**, 文本**没有**正面说"
                "「我没有/没用过该产品」—— 一个已持旧机的人同样可以说「不折腾了, 将就用」。⇒ 落 (丁)。"),
    "C_明确放弃_1": (None,
                "「Given up on the whole idea, honestly.」同上: 放弃的是**打算**, "
                "未拥有只能靠沉默推出。⇒ 落 (丁)。"),
}


def build() -> dict:
    A = json.loads(SRC.read_text(encoding="utf-8"))["断言"]
    # ★★★ 2026-09-13 修**锚点**: 第一版按「当前状态 != 已裁定」选 ——
    #   那只在**恢复尚未应用**时成立; 恢复一落盘, 那 6 条变回「已裁定」, 探针就再也选不到它们,
    #   于是它算出 恢复 0 / 维持 2, 而依赖它的闸当场判红(实测)。
    #   ⇒ 改按**沿革标记**选: 2026-09-10 被撤销的那 8 条, 现在各带一个标记
    #     (恢复的带 ★★★撤销与恢复沿革, 维持的带 ★★★维持撤销的理由), 两者都没有的
    #     则回落到「当前仍被撤销」——这样在**应用前后**都能选到同一批 8 条。
    MARKS = ("★★★撤销与恢复沿革", "★★★维持撤销的理由")
    w = [a for a in A
         if any(m in a for m in MARKS) or a["★★★断言状态"] != "已裁定"]
    assert len(w) == 8, (
        "★★★ 2026-09-10 被撤销的那批应当恰好 8 条, 实为 %d —— "
        "锚点失效或有人动了那批断言, 停" % len(w))
    rows, restore, keep = [], [], []
    for a in w:
        case = a["用例"]
        span, why = POSITIVE_SPANS.get(case, (None, "★ 未登记 —— 新增用例请先分类"))
        if span is not None:
            # ★ 片段必须**逐字**出现在原文里, 否则本探针自己在编
            assert span in a["文本"], (
                "★★★ 登记的片段 %r 不在原文里: %r —— 本探针在编证据, 立刻停" % (span, a["文本"]))
            basis, action = "乙 · 文本内正面反证", "恢复"
            restore.append(case)
        else:
            basis, action = "丁 · 文本外事实的证据缺席", "维持撤销"
            keep.append(case)
        rows.append({"用例": case, "文本": a["文本"], "输出谓词": a["输出谓词"],
                     "可推导性依据": basis, "原文片段": span, "为什么": why, "处置": action})
    return {
        "block": "WITHDRAWN_DISPLAY_ASSERTIONS_RECLASSIFY",
        "★前提": "**P1 = 只含物**(display 的对象域限定为产品/使用体验)。"
               "若 P1 取「含事」, 6 条的反证**不再充分** —— 已完成的选购过程会成为另一个候选对象。",
        "★判据": "落 (乙) ⟺ 能在原文里**指名一个正面陈述取得尚未发生的片段**; "
               "指不出 ⇒ 落 (丁) ⇒ 维持撤销。片段由代码**逐字核对**是否真在原文里。",
        "★原撤销理由哪里过宽": "8 条的撤销理由**逐字相同**(「说话人未拥有亦未经历该产品」), "
                       "即它是**按类**撤的, 不是逐条判的。而 6 条的文本里有正面陈述 ⇒ "
                       "**正面说了还没买 ≠ 没提买没买**。原则本身没错, 错在**一刀切地套**。",
        "逐条": rows,
        "★★★恢复": restore,
        "★维持撤销": keep,
        "★★★对 gen8 判决的影响": _gen8_impact(restore),
        "★这不覆盖什么": [
            "它**不**说那 6 条判得对 —— 只说它们**可由冻结合同推出**, 因而有资格进断言表。",
            "它**不**动那 10 个未裁定用例。",
            "它**不**构成替换生产的依据(DEV-001 偏离 · 旧缺陷未结案 仍在)。",
        ],
    }


def _gen8_impact(restore):
    p = ROOT / "tests" / "data" / "gen8_shipping_result.json"
    if not p.exists():
        return "★ 找不到 gen8 结果文件 —— 影响**未知**, 不回落到任何旧结论。"
    g = json.loads(p.read_text(encoding="utf-8"))
    v = g.get("★★★三个违例") or []
    cases = [x.get("用例") for x in v]
    back = [c for c in cases if c in restore]
    return {
        "gen8 原三违例": cases,
        "★★★其中落在恢复集里的": back,
        "结论": ("**gen8 改回 FAIL**(%d/%d 个原违例的断言依据恢复)" % (len(back), len(cases))
               if back else "gen8 判决不受影响"),
        "★谁的代价": "这是 **P1=只含物** 这个决定自己的代价, 不是外部坏消息。"
                 "选它就要接受候选代在本测试范围内**不通过**。",
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
