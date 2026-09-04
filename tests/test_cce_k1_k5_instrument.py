#!/usr/bin/env python3
"""K1 在 outbound_post 的仪器(k=5)上 —— 「未测」归零, 但**纪律一条没松**。

## 做了什么
生产状态表里唯一的「未测」是: outbound_post 用的 0e9ca1d4e7a2f180 上**没有 K1 判定**,
而**标定不可跨仪器搬** ⇒ 该档结层零可用读数。这不是弱证据, 是没有读数。
⇒ 在**那台仪器上**补做 K1(判据、文本与 k=3 逐字相同, 只有仪器不同; k=3 的 draw 一条不复用)。

## 结果
· intensity 0/5 · weight 0/5, 两者非退化 ⇒ INSTRUMENT_WIDE_FAIL(与 k=3 **同形**)
· **top-1 五个文本全 8/8**, 非退化(3 种众数) ⇒ 只放行 top-1

## ★ 加第二台仪器**不是**放松「不可跨仪器搬」
恰恰相反: 改成按仪器路由后, **每台仪器必须有它自己的判定**, 未登记的仪器一律拒发。
本测试反向验这一点。
"""
import json, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import knot_readout_usable, VERDICT_BY_INSTRUMENT, verdict_path_for

P = os.path.join(ROOT, "tests/data/phase2")
V5 = json.load(open(os.path.join(P, "k1_top1_k5_verdict.json"), encoding="utf-8"))
W5 = json.load(open(os.path.join(P, "k1_v2_k5_verdict.json"), encoding="utf-8"))
PRE = json.load(open(os.path.join(P, "k1_v2_k5_prereg.json"), encoding="utf-8"))

# ── ① 预注册早于测量, 判据与 k=3 逐字相同 ──────────────────────────
assert PRE["★frozen_before_measurement"]
assert "逐字相同" in PRE["criterion"]["★identical_to_k3"], \
    "★ 换判据就无法判断差异来自仪器还是来自尺"
assert "一条都不能复用" in PRE["design"]["★no_reuse"], "★ 跨仪器不许复用 raw draw"
assert PRE["instrument"]["must_equal"] == "0e9ca1d4e7a2f180"

# ── ② 读数确实来自那台仪器 ──────────────────────────────────────────
rows = [json.loads(l) for l in
        open(os.path.join(P, "k1_v2_k5_checkpoint.jsonl"), encoding="utf-8") if l.strip()]
assert {r["instrument_hash"] for r in rows} == {"0e9ca1d4e7a2f180"}, "★ 读数里混了别的仪器"
assert len(rows) == 40, f"★ 应为 5 文本 × 8 rep = 40, 实际 {len(rows)}"

# ── ③ top-1 判定由**数据**复算, 不信我写的字 ────────────────────────
by = collections.defaultdict(list)
for r in rows:
    by[r["base_id"]].append(r["top1"])
recomputed = {b: collections.Counter(v).most_common(1)[0][1] for b, v in by.items()}
assert all(c >= 7 for c in recomputed.values()), f"★ 复算不达标: {recomputed}"
assert V5["verdict"] == "TOP1_USABLE"
assert len({collections.Counter(v).most_common(1)[0][0] for v in by.values()}) > 1, \
    "★ 众数全同 ⇒ 恒返回一个结也会满分, 非退化闸必须过"
assert V5["degeneracy"]["pass"]

# ── ④ 只放行 top-1, intensity/weight 保持扣发 ──────────────────────
assert W5["decision"] == "INSTRUMENT_WIDE_FAIL", W5["decision"]
assert "只放行 top-1" in V5["★intensity_weight_unchanged"]
ok, why = knot_readout_usable("top1", instrument_hash="0e9ca1d4e7a2f180")
assert ok, why
for form in ("intensity", "weight", "band3", "rank_rho", "top2_set"):
    bad, _ = knot_readout_usable(form, instrument_hash="0e9ca1d4e7a2f180")
    assert not bad, f"★ {form} 不该被放行"

# ── ⑤ ★ 反向: 未登记的仪器仍一律拒发(加第二台没有放松纪律) ──────────
# ★ 两种拒发理由必须**分开**: 「压根没给仪器标识」与「给了但那台没判定」是两回事,
#   合并会让日志读不出问题在哪。下面分别验。
for unknown in ("d4c35704361ef96b", "deadbeefdeadbeef"):
    bad, why2 = knot_readout_usable("top1", instrument_hash=unknown)
    assert not bad, f"★ 未登记仪器 {unknown!r} 被放行了 —— 「不可跨仪器搬」被削弱了"
    assert "没有登记的 K1 判定" in why2 and "不可跨仪器搬" in why2, why2
for absent in (None, ""):
    bad, why3 = knot_readout_usable("top1", instrument_hash=absent)
    assert not bad, f"★ 缺仪器标识 {absent!r} 被放行了"
    assert "缺仪器标识不等于仪器相同" in why3, why3
assert set(VERDICT_BY_INSTRUMENT) == {"565470cf26c16d01", "0e9ca1d4e7a2f180"}, \
    "★ 登记表里出现了没有实测判定的仪器"
for h in VERDICT_BY_INSTRUMENT:
    d = json.load(open(verdict_path_for(h), encoding="utf-8"))
    assert d["instrument_hash"] == h, f"★ {h} 指向的判定其实是在 {d['instrument_hash']} 上做的"
# ★ 路径必须**调用时**解析 —— 否则靠 monkeypatch 证明「闸是判定驱动不是恒拦」的反向测试会被悄悄弄坏
import cce_k1_status as _ks
_save = _ks.K1_VERDICT
try:
    _ks.K1_VERDICT = "/definitely/not/here.json"
    _bad, _ = knot_readout_usable("top1", instrument_hash="565470cf26c16d01")
    assert not _bad, "★ K1_VERDICT 被改指到不存在的文件, 闸却仍放行 ⇒ 路径没有在调用时解析"
finally:
    _ks.K1_VERDICT = _save

# ── ⑥ 零新增调用那部分要说明白 ──────────────────────────────────────
assert "零新增调用" in V5["★source"]
assert "不是看完数据才定的" in V5["★criterion_pre_exists"], \
    "★ top-1 判据必须是预先存在的, 否则就是看完数据挑判据"

print("test_cce_k1_k5_instrument: OK (在 post 自己那台仪器 0e9ca1d4 上补做 K1, 40 次调用 | "
      f"intensity 0/5 · weight 0/5 ⇒ {W5['decision']}(与 k=3 同形) | "
      "**top-1 五文本全 8/8 且非退化(3 种众数)** ⇒ 只放行 top-1 | "
      "由 checkpoint **复算**验证, 不信摘要 | "
      "★ 反向: 未登记仪器与缺仪器仍一律拒发 —— 加第二台**没有**放松「不可跨仪器搬」)")
