#!/usr/bin/env python3
"""within_js 噪声底闸的离线测试。不需要 API key —— run_knot_classify 被桩替换。

存在理由(2026-08-18): within_js 是仪器的自测噪声底(K 次采样两两 JS 散度), 每次都算、
每次都写进 manifest, 但此前**没有任何 gate 使用它**; 唯一动作是阈值 0.25 的 flag,
实测 31 条里只触发 2 次 —— 接近永久绿。永久绿与永久红是同一种失效。

★ CI 遍历 tests/test_*.py 执行, 本文件末尾断言那个遍历机制还在。
"""
import json
import re
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("MINIMAX_API_KEY", "stub-not-used")

import cce_full_run as C  # noqa: E402

TH = C.WITHIN_JS_MAX


def run_s1(within, tops=None, k_ok=3):
    tops = tops or {"desire": "控制欲", "need": "N04_理解世界",
                    "emotion": "curiosity好奇", "action": "attend关注"}
    C.MANIFEST.clear()
    orig = C.run_knot_classify
    C.run_knot_classify = lambda tf, ctxs, k, out: {
        "stage1": {"within_js": within, "tops": tops, "k_ok": k_ok}, "stage2": {"knots": []}}
    try:
        C.s1({"text_file": "x", "context": "c", "k": 3, "outdir": "/tmp"})
        return C.MANIFEST["s1_readout"]
    finally:
        C.run_knot_classify = orig


CLEAN = {"desire_vec": 0.05, "need_vec": 0.08, "emotion_vec": 0.09, "action_vec": 0.06}

# ── 1. 噪声底以下: 四层 top 全保留 ──────────────────────────────────────────
r = run_s1(CLEAN)
assert r["over_noise_floor"] is None, r
assert r["tops_withheld"] is None, r
assert all(v is not None for v in r["tops"].values()), r

# ── 2. ★ 反向测试: 超过噪声底的那一层, top 必须被扣发 ──────────────────────
# 这是本闸存在的全部意义。它若对这种输入仍原样发 top, 就是假检查。
noisy = dict(CLEAN, need_vec=TH["need_vec"] + 0.05)
r = run_s1(noisy)
assert r["over_noise_floor"] == {"need_vec": round(noisy["need_vec"], 4)}, r
assert r["tops"]["need"] is None, "超噪声底的层必须扣发 top"
assert r["tops"]["desire"] is not None, "未超的层不受影响"
assert "need" in (r["tops_withheld"] or {}), r

# ── 3. 阈值必须是逐层的, 不是一个通用数 ────────────────────────────────────
# desire 阈值(0.120)低于 need 阈值(0.161) —— 同一个值在两层判定不同。
assert TH["desire_vec"] < TH["need_vec"], TH
probe = 0.14   # > desire 阈值, < need 阈值
r = run_s1(dict(CLEAN, desire_vec=probe, need_vec=probe))
assert r["tops"]["desire"] is None and r["tops"]["need"] is not None, \
    f"同一个 within_js={probe} 必须在 desire 判超、在 need 判不超, 否则阈值退化成通用数"

# ── 4. 边界: 恰等于阈值不算超(用 > 不用 >=), 明确写死避免以后漂移 ──────────
r = run_s1(dict(CLEAN, need_vec=TH["need_vec"]))
assert r["tops"]["need"] is not None, "恰等于阈值不扣发"
r = run_s1(dict(CLEAN, need_vec=TH["need_vec"] + 1e-6))
assert r["tops"]["need"] is None, "超过阈值即扣发"

# ── 5. ★ within_js 缺失是真失败, 不得静默放行 ─────────────────────────────
# k_ok<2 时算不出两两散度。没有噪声读数 = 没有可信度判断, 此时放行等于回到改前状态。
try:
    run_s1(None, k_ok=1)
    raise AssertionError("within_js 缺失时必须抛错")
except RuntimeError as e:
    assert "within_js 缺失" in str(e), e

# ── 6. 旧的 0.25 flag 保留但不再是唯一动作 ────────────────────────────────
r = run_s1(dict(CLEAN, emotion_vec=0.30))
assert r["high_divergence_flag"] == {"emotion_vec": 0.30}, r
assert r["tops"]["emotion"] is None, "0.30 同时超逐层阈值, top 也必须扣发"

# ── 7. 本文件必须在 CI 的硬编码执行清单里 ─────────────────────────────────
wf = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(encoding="utf-8")
# 2026-08-18: CI 原先是**硬编码的 11 行清单**, 新增测试忘了加进去就永不执行(假检查, 且无声)。
# 已改成遍历 tests/test_*.py + 数量下限自守。本断言随之从「我在清单里」
# 改成「遍历机制还在」—— 后者更强: 它保证的是**所有**测试都跑, 不只是我自己。
assert "for t in tests/test_*.py" in wf, \
    "CI 必须遍历 tests/test_*.py —— 退回硬编码清单会让新增测试永不执行"
assert re.search(r'test "\$n" -ge \d+', wf), \
    "遍历必须配数量下限自守 —— 否则路径写错会静默跑零个测试而 CI 全绿"

print("test_cce_within_js_gate: OK (逐层阈值 / 扣发 top / 边界 / 缺失即红 / CI 自防)")
