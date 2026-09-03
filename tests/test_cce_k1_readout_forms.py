#!/usr/bin/env python3
"""结层读数形式的白名单闸 + 探索性分析的定位。

★ 这条测试同时钉两件事:
  ① 白名单**默认拒发** —— 新发明一个 form 不会自动可用
  ② 探索性数据**只能关门不能开门** —— 它是看完 v2 结果之后才做的,
     拿它开门就是「用同一批输入既调参又验收」
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from cce_k1_status import (knot_readout_usable, KNOT_READOUT_ALLOWLIST,   # noqa: E402
                           KNOT_READOUT_EXCLUDED)
from k1_readout_forms import analyse                                       # noqa: E402

INST = "565470cf26c16d01"

# ── 白名单只有 top1, 且它确有预注册判定支撑 ──────────────────────────
assert KNOT_READOUT_ALLOWLIST == {"top1"}, KNOT_READOUT_ALLOWLIST
ok, why = knot_readout_usable("top1", instrument_hash=INST)
assert ok and "top-1" in why, why

# ── 默认拒发: 没登记过的 form 也不可用 ────────────────────────────────
ok, why = knot_readout_usable("我随手发明的形式", instrument_hash=INST)
assert not ok and "缺预注册判定不等于可用" in why, why

# ── 被排除的每一项都必须写明理由(不许只写 False) ──────────────────────
for form in ("intensity", "weight", "band3", "rank_rho", "top2_set"):
    ok, why = knot_readout_usable(form, instrument_hash=INST)
    assert not ok, f"★ {form} 不该可用"
    assert KNOT_READOUT_EXCLUDED[form].strip(), f"{form} 排除理由为空"
    assert any(c.isdigit() for c in KNOT_READOUT_EXCLUDED[form]), \
        f"★ {form} 的排除理由里没有数 —— 「不行」必须带实测值, 否则下一个人会重试"

# ── 探索性分析可重跑, 且结论方向不变 ──────────────────────────────────
r = analyse()
assert r["★status"] == "EXPLORATORY_NOT_PREREGISTERED"
assert "不得用来采纳" in r["★usable_for"], "★ 探索性数据的用途必须写死在产物里"
assert r["texts"] == 5 and all(n == 8 for n in r["reps_per_text"].values()), r["reps_per_text"]
F = r["forms"]
assert F["top1"]["meets_0.95_on_all_texts"], "★ top-1 若不再全过, 白名单要重估"
for form in ("cardinal", "band3", "rank_rho", "top2_set"):
    assert not F[form]["meets_0.95_on_all_texts"], f"★ {form} 若过了, 结论要重写而不是沿用"
# ★ 最关键的一条: 粗档相对基数的改善小到不值得再花钱
gain = F["band3"]["mean"] - F["cardinal"]["mean"]
assert gain < 0.05, f"★ 粗档改善 {gain:.3f} 变大了 —— 「粗档不是逃生路」这个结论要重估"

print(f"test_cce_k1_readout_forms: OK (白名单 {sorted(KNOT_READOUT_ALLOWLIST)} 默认拒发 | "
      f"排除 {len(KNOT_READOUT_EXCLUDED)} 项且各带实测值 | "
      f"粗档相对基数仅 +{gain:.3f} ⇒ 不是逃生路 | "
      "探索性数据只关门不开门)")
