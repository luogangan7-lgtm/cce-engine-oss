#!/usr/bin/env python3
"""§44.10「内容 A/B 不可判」的可执行形式。

★ 核心断言: 功效不足时**拿不到**任何判决 —— 拿得到就等于允许把
「没测出差异」说成「没有差异」, 那正是这条闸存在的理由。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_ab_power import (required_n, verdict, assert_powered,          # noqa: E402
                          UnderpoweredError, HISTORICAL_MAX_VIEWS_PER_POST)

# ── 公式方向性 ────────────────────────────────────────────────────────
n_small = required_n(0.30, 0.50)      # 大效应
n_big = required_n(0.30, 0.34)        # 小效应
assert n_big > n_small * 10, f"效应越小所需 n 越大: {n_small} vs {n_big}"
assert required_n(0.3, 0.5, power=0.90) > required_n(0.3, 0.5, power=0.80)
assert required_n(0.3, 0.5, alpha=0.01) > required_n(0.3, 0.5, alpha=0.05)
try:
    required_n(0.4, 0.4); raise AssertionError("两臂相同应当拒绝")
except ValueError:
    pass

# ── ★ 功效不足 -> NOT_POWERED, 且**不含**任何「无差异」措辞 ───────────
v = verdict(p1=0.0034, p2=0.0075, n_per_arm=1000)
assert v["verdict"] == "NOT_POWERED", v
assert not v["powered"]
# ★ 只查**结论位**, 不查解释位: 解释里出现「没有差异」是为了警告不许这么读,
#   把解释一起禁掉会逼着人删掉警告本身 —— 那是把闸调成反向。
conclusion_fields = {k: x for k, x in v.items() if not k.startswith("★")}
blob = str(conclusion_fields)
for banned in ("无差异", "没有差异", "no difference", "not significant", "不显著"):
    assert banned not in blob, f"★ 结论位出现了 {banned!r} —— 会被读成检验结果"
# 而解释位**必须**把这句警告说出来
assert "在数据上长得一模一样" in v["★why"], "★ 必须写明两者为何不可区分, 否则没人知道为什么拦"

# ── 功效足够也只是「允许做」, 不是结果 ────────────────────────────────
v2 = verdict(p1=0.30, p2=0.50, n_per_arm=10**5)
assert v2["verdict"] == "POWERED_MAY_TEST" and "不是检验结果" in v2["★note"]

# ── assert_powered: 功效不足必须**抛**, 不许返回 ──────────────────────
try:
    assert_powered(p1=0.0034, p2=0.0075, n_per_arm=1000)
    raise AssertionError("★ 功效不足却拿到了返回值 —— 那这条闸等于不存在")
except UnderpoweredError as e:
    assert "本函数**不给**判决" in str(e)

# ── ★ §44.10 的 24,500 不许作为常数进入代码 ──────────────────────────
import cce_ab_power as _M
_src = open(_M.__file__, encoding="utf-8").read()
import re as _re
_consts = _re.findall(r"^[A-Z_]+\s*=\s*(\d+)", _src, _re.M)
assert "24500" not in _consts, "★ 24,500 不可复算(§44.10 未定义 R), 不得写死"
assert "不可复算" in _M.__doc__, "★ 复算不出来这件事必须写在模块里, 不能只在提交信息里"

# ── ★ 天花板: 所需 n 超过历史最高浏览时必须点明 ──────────────────────
# 下面这对率是**示例**, 不是 §44.10 的 R —— R 没有定义, 我不冒充它。
need = required_n(0.0034, 0.0075)
v3 = verdict(p1=0.0034, p2=0.0075, n_per_arm=HISTORICAL_MAX_VIEWS_PER_POST)
if need > HISTORICAL_MAX_VIEWS_PER_POST:
    assert "★ceiling" in v3 and "触达量级" in v3["★ceiling"], v3
    assert not v3["reachable_today"]

# ── 没有「宽容模式」这个逃生口 ────────────────────────────────────────
import cce_ab_power as M
src = open(M.__file__, encoding="utf-8").read()
for escape in ("force=", "lenient", "skip_power", "ignore_power"):
    assert escape not in src, f"★ 出现逃生口 {escape} —— 宽容模式就是这条闸不存在"

print(f"test_cce_ab_power: OK (示例率 0.34%/0.75% 每臂需 {need}, "
      f"历史最高 {HISTORICAL_MAX_VIEWS_PER_POST} | "
      f"★ §44.10 的 24,500 不可复算(全文未定义 R), 未写死 | "
      "功效不足硬抛且输出零「无差异」措辞 | 无宽容模式逃生口)")
