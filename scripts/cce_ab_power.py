#!/usr/bin/env python3
"""内容 A/B 的功效闸 (§44.10 的可执行形式)。

## 为什么需要它
§44.10 已判定「内容 A/B 在触达量级提升之前不可判」, 但那只是文档里的一句话。
本项目已确立**散文式 caveat 没有保护力** —— 一句话拦不住下一个人发两版然后报个结论。

## 它防的是哪个错
不是「算错」, 是**把功效不足的『没显著差异』说成『没有差异』**。
样本量不够时, 两者在数据上长得一模一样, 只有功效计算能把它们分开。

## ★ §44.10 的「24,500」不可复算, 故不继承
文档原话是「分辨 R=0.34 与 R=0.75 需约 24,500 浏览/帖」, 但**全文没有定义 R 是什么**。
按 0.34%/0.75% 两比例、α=0.05、power=0.80 现算是每臂 5,058 —— 与 24,500 对不上,
而在缺 R 定义的情况下**无法判断是文档错还是我的解读错**。
本项目已栽过「引用一个自己复算不出来的数」(那次是 562 条), 所以这里不写死它:
`required_n()` 由**调用方声明的率**现算, 24,500 不作为常数进入代码。
历史触达上限 16,102 是文档里可追溯的实测值, 作为当前天花板登记。
"""
from __future__ import annotations

import math

# 单帖历史最高浏览量。出处: docs/CCE_full_architecture_workflow_parameters_v1.md §44.10
HISTORICAL_MAX_VIEWS_PER_POST = 16102

_Z = {0.10: 1.6449, 0.05: 1.9600, 0.01: 2.5758}      # 双侧
_ZB = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}      # 功效


class UnderpoweredError(ValueError):
    """功效不足却索要判决。★ 绝不降级为「返回不显著」。"""


def required_n(p1: float, p2: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """两比例检验每臂所需样本量。标准公式, 不做连续性校正(偏保守方向由使用者承担)。"""
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError(f"p 必须在 (0,1): {p1}, {p2}")
    if p1 == p2:
        raise ValueError("两臂率相同 —— 不存在「分辨它们所需的 n」")
    z_a, z_b = _Z[alpha], _ZB[power]
    num = (z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(num / (p1 - p2) ** 2)


def verdict(*, p1: float, p2: float, n_per_arm: int,
            alpha: float = 0.05, power: float = 0.80) -> dict:
    """A/B 判决的**唯一**出口。功效不足时给 NOT_POWERED, 永远不给「无差异」。"""
    need = required_n(p1, p2, alpha, power)
    powered = n_per_arm >= need
    out = {"required_n_per_arm": need, "actual_n_per_arm": n_per_arm,
           "powered": powered, "alpha": alpha, "power": power,
           "historical_max_views_per_post": HISTORICAL_MAX_VIEWS_PER_POST,
           "reachable_today": need <= HISTORICAL_MAX_VIEWS_PER_POST}
    if not powered:
        out["verdict"] = "NOT_POWERED"
        out["★why"] = (
            f"每臂需 {need}, 实有 {n_per_arm}。功效不足时「没测出显著差异」与「没有差异」"
            "在数据上长得一模一样 —— 本函数**不给**判决, 因为给了就会被读成后者。")
        if need > HISTORICAL_MAX_VIEWS_PER_POST:
            out["★ceiling"] = (
                f"所需 {need} 已超过本序列单帖历史最高浏览 {HISTORICAL_MAX_VIEWS_PER_POST} "
                "⇒ 这不是「多发几篇」能解决的, 是触达量级问题。§44.10: "
                "该路径在触达量级提升之前不应开启。")
        return out
    out["verdict"] = "POWERED_MAY_TEST"
    out["★note"] = "功效足够**只是允许做检验**, 不是检验结果。"
    return out


def assert_powered(**kw) -> dict:
    """要判决就必须先过功效。★ 不给「宽容模式」—— 宽容模式就是这条闸不存在。"""
    v = verdict(**kw)
    if not v["powered"]:
        raise UnderpoweredError(v["★why"] + v.get("★ceiling", ""))
    return v
