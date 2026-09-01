#!/usr/bin/env python3
"""合规闸的守卫 —— 它拦的是发出去的内容，此前零测试。

## 为什么现在必须有
`cce_outbound_guard` 是 §48 链路第 9 段（DISTRIBUTION）的实现，也是 §44.9 的 P7
三闸之一。它 412 行、决定一份稿子能不能发，而到 2026-09-01 之前**没有一个测试**。

同日还实测出：`_load_env_utf8()` 引用未定义的 `ROOT`，`import cce_outbound_guard`
直接抛 NameError —— 该缺陷记在库里三周，因为命令行调用走的是另一条路（函数定义在
`__main__` 块 `sys.exit()` 之后，永不执行），所以生产没暴雷。
**一个没有测试的闸，连自己 import 不了都能瞒三周。**

## 三条不能弄反的语义
1. **如实否定必须豁免** —— 「我们没有 FDA 认证」是合规写法，不是违规。
   把它当违规拦下，会逼作者去掉唯一诚实的那句话。
2. **广告法层只对国内** —— `market='intl'` 时绝对化用语不拦；把它对国外也开，
   会拦掉大量正常英文表达。
3. **core/efficacy 层跨境都拦** —— 凭证幻觉与疗效宣称在哪个市场都不许。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# ★ 这一行本身就是回归测试：它曾经抛 NameError，且瞒了三周
import cce_outbound_guard as G  # noqa: E402

for fn in ("scan_draft", "is_clean", "list_profiles"):
    assert hasattr(G, fn), \
        (f"★ 模块缺少 {fn} —— 文件 docstring 写明用法是 "
         "`from cce_outbound_guard import scan_draft, is_clean`，那条路必须是通的")

CLEAN = "I wore mine for six months and the streaming finally got better."
CRED = "Our FDA-approved device cures hearing loss."
DENY = "We do not have FDA clearance and this cannot cure hearing loss."
ADLAW = "最好的助听器, 全国第一。"

# ── ① 凭证幻觉 + 疗效宣称：两个市场都必须拦 ────────────────────────────────
for market in ("cn", "intl"):
    assert not G.is_clean(CRED, market=market), \
        f"★ 凭证幻觉/疗效宣称在 market={market} 未被拦 —— core/efficacy 层是跨境硬线"

# ── ② 如实否定必须豁免（弄反的代价：逼作者删掉唯一诚实的那句）──────────────
assert G.is_clean(DENY), \
    ("★ 如实否定被当成违规拦下。「我们没有 FDA 认证」是合规写法。"
     "把它拦掉会逼作者去掉唯一诚实的那句话 —— 闸会主动制造不诚实。")
hits = G.scan_draft(DENY)
assert hits and all(h["negated"] for h in hits), \
    f"★ 否定检测失效：{[(h['canonical'], h['negated']) for h in hits]}"

# ── ③ 广告法层只对国内 ─────────────────────────────────────────────────────
assert not G.is_clean(ADLAW, market="cn"), "★ 绝对化用语在国内市场未被拦"
assert G.is_clean(ADLAW, market="intl"), \
    "★ 广告法层对 intl 也开了 —— 会拦掉大量正常英文表达"

# ── ④ 正向对照：干净稿必须放行（否则是永远红）──────────────────────────────
assert G.is_clean(CLEAN) and not G.scan_draft(CLEAN), \
    f"★ 干净稿被误拦：{G.scan_draft(CLEAN)}"

# ── ⑤ 违规记录必须可定位、可解释，而不只是一个布尔 ─────────────────────────
v = G.scan_draft(CRED)
assert v, "★ 违规稿扫不出任何命中"
for h in v:
    for k in ("canonical", "matched", "start", "end", "tier", "negated", "context"):
        assert k in h, f"★ 违规记录缺 {k} —— 只给布尔的闸没法让人改稿"
    assert h["tier"] in ("core", "efficacy", "adlaw_cn", "extended")
    assert CRED[h["start"]:h["end"]] == h["matched"], \
        f"★ start/end 定位与 matched 对不上：{h}"

# ── ⑥ 品类档案必须可枚举（P7 按 profile 装载疗效红线）──────────────────────
assert G.list_profiles(), "★ 一个品类档案都没有，profile 参数形同虚设"

print(f"test_cce_outbound_guard: OK (import 可用[曾抛 NameError 三周] / "
      f"凭证·疗效跨境双拦 / 如实否定豁免 / 广告法仅国内 / 干净稿放行 / "
      f"违规记录 7 字段可定位 / {len(G.list_profiles())} 个品类档案)")
