#!/usr/bin/env python3
"""铁律 23 的闸: 九结是 candidate ontology, 「未验」标注不许被静默删掉。

★ 为什么必须双向:
  单向(只断言 caveat 在)会腐烂成**永久谎言** —— G-K1/2/3 真跑过之后
  caveat 还在, 就变成了对已验收结论的错误降级。
  所以第二个方向同样是硬断言: status 不再说未验 -> caveat 必须消失。

这条测试本身就是「可注入的失败在上一层」的实例: 无法给 G-K1 注入一次真失败,
但可以给**状态字段**注入, 断言探测器确实响。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_knot_classify import caveats, CANDIDATE_CAVEAT, BASE_CAVEATS  # noqa: E402

TAXO = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))

# ── 0. ★ 冻结重构前的字面量 ────────────────────────────────────────────
#    抽函数是「纯重构」的前提是**输出逐字未变**。断言 live[1:] == BASE_CAVEATS
#    是同义反复(拿新常量比新常量), 比不出漂移。这三行是 2026-09-03 重构**之前**
#    main() 里写死的原文, 出处可核: cce_core_manifest.refactor_log 里 2026-09-03 那条的
#    from_sha=cc7c1f8c8dcd67b5, 即 git 2355eef 的 scripts/cce_knot_classify.py。
PRE_REFACTOR = [
    "结分类学 v1: G-K1/G-K2/G-K3 验收未跑,引用须带「未验」",
    "全占比: knots 是带权组合,禁把单个 top 当断言",
    "第1级情绪层禁单top(4模型面板判);行动层无分辨率(三重合证),两处以分布/appraisal为准",
]
assert caveats(TAXO) == PRE_REFACTOR, "★ 重构改变了输出 —— 那就不是纯重构, 必须换代而非记 refactor_log"

# ── 1. 现网配置: 未验 -> 必须带 caveat, 且排在首位 ──────────────────────
live = caveats(TAXO)
assert CANDIDATE_CAVEAT in live, "★ 现网 taxonomy 标未验, 输出却没有「未验」caveat"
assert live[0] == CANDIDATE_CAVEAT, "「未验」必须在首位 —— 排到末尾等于埋掉"
assert live[1:] == list(BASE_CAVEATS), "基础 caveat 不得被顺带改掉"

# ── 2. ★ 反向一: 状态说未验, 却把 caveat 摘了 -> 必须能被这条测试抓到 ──
#    (Kontrolle: 证明探测器真的会响, 而不是恒绿)
probe = caveats({"status": "验收 gate G-K1 未跑"})
assert CANDIDATE_CAVEAT in probe, "★ 探测器失效: 未验状态下 caveat 没出现"

# ── 3. ★ 反向二: 状态不再说未验 -> caveat 必须消失(防永久谎言) ─────────
verified = caveats({"status": "v1 已验收: G-K1 κ=0.71 / G-K2 通过 / G-K3 通过"})
assert CANDIDATE_CAVEAT not in verified, (
    "★ G-K1/2/3 已验收, 「未验」caveat 却还在 —— 这是对已验收结论的错误降级")
assert verified == list(BASE_CAVEATS)

# ── 4. status 字段缺失 = 不知道验没验, 按未验处理? 不 —— 显式暴露 ───────
#    缺字段既不能当已验(会去掉未验标注), 也不该沉默。当前实现走「不带 caveat」,
#    这里把它钉死成**已知行为**, 将来改判据必须先改这条断言。
assert caveats({}) == list(BASE_CAVEATS), (
    "status 缺失时的行为变了 —— 这是判据变更, 必须显式改本断言而不是让它跟着漂")

print("✅ test_cce_knot_caveat: 铁律 23 有闸 | "
      f"未验->带标注(首位) · 已验->标注消失 · 缺字段行为已钉死 | "
      f"现网 status={TAXO['status'][:24]}...")
