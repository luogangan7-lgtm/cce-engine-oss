#!/usr/bin/env python3
"""K1 判定的**单一真相源** —— 哪一层读数允许进入下游。

## 为什么需要它
2026-09-02 发现系统内部自相矛盾:
  · 出站闸(cce_strategy_gate)按 K1 判定**硬拦** [[knot_intensity:]] 的引用
  · 而 cce_full_run.usable_readouts 把 s2.distribution 里的 intensity
    **无条件**放进 usable —— usable 的定义是「允许进入下游/Population Field」
    「只有 usable 里的东西允许被引用」
同一份读数, 一条路上被拦、另一条路上宣布可引用。

它靠的是一句散文 caveat:「必须带 n 与不确定性一起引用」。
而本项目已确立: **散文式 caveat 在这个项目已被证伪**
(13 条 Notion 读数都标了「不可单独使用」, 照样被当读数引用)。
所以改成由判定驱动的**路由**, 不是再加一句话。

## 分层, 不是一刀切
K1 的判定本身是分层的: top-1 一致 8/8 达标, 逐对容差一致 A(0.1) 不达标。
所以 top-1 层可用、强度层不可用 —— 这正是铁律 24 要求分离的两件事。

## 缺判定 != 判定通过
找不到判定文件时一律扣发。这条规则与出站闸一致。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K1_VERDICT = os.path.join(ROOT, "tests", "data", "phase2", "k1_reliability_verdict.json")

# 判据名 -> 它管的是哪一层
INTENSITY_CRITERION = "逐对容差一致"
TOP1_CRITERION = "top-1 一致"


def _load(path=None):
    # ★ 路径在**调用时**解析, 不用默认参数绑定 —— 默认参数在 def 时就固定了,
    #   测试改不动它, 于是「换一份判定验证闸会跟着变」这类反向测试根本跑不了。
    path = path or K1_VERDICT
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _criterion(v, needle):
    for c in v.get("checks", []):
        if needle in c["name"]:
            return c
    return None


def layer_status(path=None):
    """返回 {层: {"usable": bool, "reason": str}}。path 省略时按调用时的 K1_VERDICT 解析。"""
    path = path or K1_VERDICT
    v = _load(path)
    if v is None:
        miss = {"usable": False,
                "reason": "缺 K1 判定 —— **缺判定不等于判定通过**, 一律扣发"}
        return {"intensity": dict(miss), "top1": dict(miss)}
    out = {}
    for layer, needle in (("intensity", INTENSITY_CRITERION), ("top1", TOP1_CRITERION)):
        c = _criterion(v, needle)
        if c is None:
            out[layer] = {"usable": False,
                          "reason": f"K1 判定里找不到「{needle}」这一项 —— 判据变了却没更新路由"}
        elif c["pass"]:
            out[layer] = {"usable": True,
                          "reason": f"K1「{c['name']}」达标: {c['value']}"}
        else:
            out[layer] = {"usable": False,
                          "reason": f"K1「{c['name']}」不达标: {c['value']} "
                                    f"(判定 {v.get('verdict')}, 见 {os.path.relpath(path, ROOT)})"}
    return out


def intensity_usable(path=None):
    s = layer_status(path)["intensity"]
    return s["usable"], s["reason"]


def top1_usable(path=None):
    s = layer_status(path)["top1"]
    return s["usable"], s["reason"]


if __name__ == "__main__":
    import sys
    st = layer_status()
    for k, v in st.items():
        print(f"{'✓' if v['usable'] else '✗'} {k:<10} {v['reason']}")
    sys.exit(0)
