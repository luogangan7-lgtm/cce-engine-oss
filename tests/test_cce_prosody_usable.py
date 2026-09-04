#!/usr/bin/env python3
"""韵律读数的可用性判据 —— 以及为什么这里**没有**连续量阈值闸。

## 判据是**类别**的, 不是阈值的
· f0_source == "vocals" ⇒ 可用
· f0_source == "mixed"  ⇒ 不可用
· 其他/缺失               ⇒ 不可用(默认拒判)

我第一版写过 `nonvocal_share > 0.35 ⇒ 不可用`。两条理由删掉它:
① **全占比原则禁止在噪声连续量上设布尔闸** —— 0.34 与 0.36 在测量上不可区分, 判决却相反。
   0.35 是我拍的数, 不是从数据推的。
② 它**不可达**: nonvocal_share 只在分离成功那一支被赋值, 而那一支 f0_source 就是 "vocals"
   ⇒「mixed 且占比已知」这个组合在代码里根本不存在, 那条分支是死代码。

## 支撑判据的实测(2026-09-04, 判据先于测量入库)
|Δf0| 随非人声占比上升, Spearman ρ=0.618 p=0.0003, n=30, 中位差 **12.4 半音(一个八度)**。
实例: 非人声 0.996 的片段, 混音 f0=79Hz(在跟贝斯走), 人声轨 231Hz 才是说话。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_audio_prosody as AP

# ── ① 类别判据 ───────────────────────────────────────────────────────
ok, why = AP.prosody_usable({"status": "ok", "f0_source": "vocals"})
assert ok and "人声轨" in why

ok, why = AP.prosody_usable({"status": "ok", "f0_source": "mixed"})
assert not ok and "12.4 半音" in why, "★ 拒判的理由要带实测数字, 不是一句「不可靠」"

for bad in (None, "unknown", "", "voice"):
    ok, _ = AP.prosody_usable({"status": "ok", "f0_source": bad})
    assert not ok, f"★ 默认必须拒判, 但 f0_source={bad!r} 被放行了"

ok, _ = AP.prosody_usable({"status": "failed"})
assert not ok, "★ 韵律没算出来时不许判可用"

# ── ② 连续量阈值必须不存在 ────────────────────────────────────────────
assert not hasattr(AP, "NONVOCAL_GATE"), \
    "★ 又出现了 nonvocal_share 阈值 —— 全占比原则禁止在噪声连续量上设布尔闸"
_src = open(os.path.join(ROOT, "scripts/cce_audio_prosody.py"), encoding="utf-8").read()
assert "全占比原则" in _src, "★ 删掉阈值的**理由**要留在原地, 否则下一个人会把它加回来"
# 占比高低都不改变结论 —— 证明没有阈值在暗处起作用
for nv in (0.0, 0.01, 0.34, 0.36, 0.99):
    ok, _ = AP.prosody_usable({"status": "ok", "f0_source": "mixed", "nonvocal_share": nv})
    assert not ok, f"★ 非人声占比 {nv} 改变了判决 —— 说明还有阈值在暗处"

# ── ③ 「mixed 且占比已知」确实不可达 ──────────────────────────────────
import inspect
_a = inspect.getsource(AP.analyse)
assert '"mixed", None' in _a.replace(" ", "").replace('"mixed",None', '"mixed", None') \
    or 'f0_source, nonvocal = path, "mixed", None' in _a, \
    "★ 初值必须是 (mixed, None) —— 否则「mixed 且占比已知」就变可达了, 阈值问题会回来"
assert _a.count('f0_source = _tmp, "vocals"') == 1, "★ vocals 只应在分离成功那一支产生"

# ── ④ 实测判决必须在库里 ─────────────────────────────────────────────
V = json.load(open(os.path.join(ROOT, "tests/data/phase2/prosody_separation_verdict.json"),
                   encoding="utf-8"))
assert V["decision"] == "SEPARATION_MATTERS"
assert V["spearman"]["p"] < 0.05 and V["spearman"]["rho"] >= 0.4
assert V["nonvocal_share"]["sd"] > 0.05, "★ 非人声占比若无变异, 主判据就没有判别力"
assert "不说" in V["★what_it_does_not_say"] and "更准" in V["★what_it_does_not_say"], \
    "★ 「不说分离后更准」这条边界要留在判决里 —— 没有 f0 地面真值就没有准不准"

print("test_cce_prosody_usable: OK (判据是**类别**的: vocals 可用 / mixed 不可用 / 其他默认拒判 | "
      "连续量阈值**不存在**且不可达(占比 0.0–0.99 都不改变判决) | "
      f"实测 ρ={V['spearman']['rho']} p={V['spearman']['p']} 中位差 "
      f"{V['delta_f0_semitones']['median']} 半音 | 「不说分离后更准」的边界钉住)")
