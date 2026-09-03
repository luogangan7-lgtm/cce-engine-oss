#!/usr/bin/env python3
"""对齐守卫必须在**共用函数**里, 不在各调用方 —— 以及 need_ok 的饱和缺口。

## 为什么这条测试存在
2026-09-03 我先只改了 reply_loop, **漏掉 reply_batch** —— 同一份不可靠读数
在一条路上被扣住、另一条路上照发判决。爆炸半径不一致本身就是缺陷,
而这正是 2026-08-18 那条注释里已经写过的教训, 我又犯了一次。
⇒ 守卫下沉到 cce_align_v2.score, 所有调用方自动继承。

## need_ok 是另一回事, 不许和上面混为一谈
实测(归档 run 32114744002, 同一文本对 8 rep): 触达率恒为 1.000, 极差 0 ——
但那是**顶到天花板**(3 个显著维全部触达), 而显著维个数自己在 2–4 之间跳。
天花板上的稳定说明不了它在 0.5 判决线附近的行为。
★ 既不能说它稳, 也不能说它坏 —— 登记为「判决线附近未被测量」。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_align_v2 import score            # noqa: E402
from reply_loop import layer_reach, LAYERS  # noqa: E402

# ── 守卫在根部: 任何调用方拿到的都是扣发过的 ──────────────────────────
r = score({"audit": .6, "reward": .4}, {}, "x" * 300, theta=0.35, detect=False, mode="reply")
assert r["★usable"] is False, "★ weight 不可用时根部必须标 usable=False"
assert r["pass"] is None, "★ 不可用时 pass 必须是 None(不可判), 给任一布尔都是把噪声当结论"
assert "不得作为放行/拦截依据" in r["★why_not_usable"]

# ── 两个调用方都不许自己发布尔 ────────────────────────────────────────
for f in ("reply_loop.py", "reply_batch.py"):
    src = open(os.path.join(ROOT, "scripts", f), encoding="utf-8").read()
    assert "knot_ok = None" in src or "else None" in src, \
        f"★ {f} 在读数层不可用时仍会发 True/False"
# 根部必须**现问**, 不许写死
alsrc = open(os.path.join(ROOT, "scripts", "cce_align_v2.py"), encoding="utf-8").read()
assert "knot_readout_usable" in alsrc, "★ 守卫必须在 cce_align_v2 里现问可用性"
assert "不降级放行" in alsrc, "★ 可用性查不到时必须判不可用, 不是通过"
assert "根因修在这里而不是各调用方" in alsrc, \
    "★ 「修根不修症状」这个教训要留在原地 —— 我在这里犯过"

# ── need_ok: 饱和必须被标出来 ─────────────────────────────────────────
sat = layer_reach([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], LAYERS["need_vec"])
assert sat["饱和"] is True and "判决线" in sat["★饱和说明"], sat
mid = layer_reach([0.5, 0.5, 0.0] + [0.0] * (len(LAYERS["need_vec"]) - 3),
                  [0.5, 0.0, 0.0] + [0.0] * (len(LAYERS["need_vec"]) - 3),
                  LAYERS["need_vec"])
if mid["触达率"] not in (0.0, 1.0):
    assert mid["饱和"] is False and mid["★饱和说明"] is None, mid

# ── 「判决线附近未被测量」这件事必须写在代码里 ────────────────────────
rlsrc = open(os.path.join(ROOT, "scripts", "reply_loop.py"), encoding="utf-8").read()
assert "未被测量" in rlsrc and "既不能说它稳, 也不能说它坏" in rlsrc, \
    "★ 缺口必须留在原地 —— 「饱和处稳定」不等于「已验收」"

print("test_cce_align_root_guard: OK (守卫下沉到共用函数, 两个调用方自动继承 | "
      "不可用 -> pass=None | need_ok 饱和被标出且缺口登记为「判决线附近未被测量」)")
