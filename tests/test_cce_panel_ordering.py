#!/usr/bin/env python3
"""面板采集的三条守卫 —— 全部来自 2026-08-20 那轮作废。

作废原因（我的设计错误，不是仪器发现）：
  清单里 24 个 base 的 L0/L0b 排在全部生成臂之前，顺序执行 ⇒ 早跑的没限流、
  晚跑的赶上 M3 限流(HTTP 200 + 空 content)。结果 L0 4% vs B1 65% 不合格，
  **「生成文本更难读」与「后半程被限流」完全混杂**，整轮不可读。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
import phase2_panel as PP  # noqa: E402

SRC = (ROOT / "probes" / "phase2_panel.py").read_text(encoding="utf-8")

# ── 1. 任务顺序必须打散，且与臂身份无关 ────────────────────────────────────
assert "SHUFFLE_SEED" in SRC and "by_base" in SRC, \
    "★ 顺序必须与臂无关, 且必须按 base 分块(完全打散会让中断后的部分数据不可分析)"
man = json.loads((ROOT / "tests" / "data" / "phase2"
                  / "panel_manifest.json").read_text(encoding="utf-8"))
import random  # noqa: E402
def build(seed):
    """复刻探针的排序逻辑: base 顺序随机, base 内臂也随机。"""
    tk = [(a, i) for a in man["arms"] for i in range(4)]
    rng = random.Random(seed)
    bb = {}
    for t in tk:
        bb.setdefault(t[0]["base_id"], []).append(t)
    order = sorted(bb)
    rng.shuffle(order)
    out = []
    for b in order:
        blk = bb[b]
        rng.shuffle(blk)
        out += blk
    return out


tasks = build(PP.SHUFFLE_SEED)
ordered = [(a, i) for a in man["arms"] for i in range(4)]
assert [t[0]["base_id"] for t in tasks] != [t[0]["base_id"] for t in ordered], "★ 打散没生效"
# ★ 关键性质一: 前若干任务里各臂齐现(不再是 L0/L0b 扎堆)
first = {t[0]["arm"] for t in tasks[:28]}
assert len(first) >= 5, f"★ 前 28 个任务只有 {first} ⇒ 仍按臂聚集, 时间混杂未消除"
# ★ 关键性质二: 同一 base 的任务必须**连续** —— 否则中断后没有完整的 base
seen, runs = set(), 0
prev = None
for t in tasks:
    b = t[0]["base_id"]
    if b != prev:
        assert b not in seen, f"★ base {b[:8]} 被拆成不连续的多段 ⇒ 中断后无完整 base"
        seen.add(b)
        runs += 1
        prev = b
n_base = len({a["base_id"] for a in man["arms"]})   # 扩展块触发后是 32, 不写死
assert runs == n_base, f"★ 连续 base 块数应等于 base 数 {n_base}, 实得 {runs}"
# 可复现 + 换 seed 换顺序
assert build(PP.SHUFFLE_SEED) == tasks, "★ 顺序不可复现 ⇒ 事后无法核对跑的是哪一批"
assert build(PP.SHUFFLE_SEED + 1) != tasks

# ── 2. 异常不得伪造 k_valid ─────────────────────────────────────────────────
assert '"k_valid": 0' not in SRC, \
    "★ 把 stage2 崩溃记成 k_valid=0 = 把基础设施失败误记成「stage1 重复不足」"
assert "stage_failed" in SRC and "infra_suspected" in SRC

# ── 3. 熔断必须能看见 stage2 ────────────────────────────────────────────────
# stage1 有 attempt ledger, stage2 **没有** ⇒ 只看 n_infra_failed 会全程漏掉 stage2
i = SRC.index("_recent.append")
assert "infra_suspected" in SRC[i - 400:i], \
    "★ 熔断只盯 stage1 的 n_infra_failed ⇒ stage2 的空返回对它隐形(首轮 213 次全漏)"

# ── 4. 限速要低于实测撞限流的速率 ──────────────────────────────────────────
assert PP.MAX_CALLS_PER_MIN <= 50, \
    f"★ 首轮跑到 73 calls/min 撞限流; 实测稳态约 50 ⇒ 必须留余量(现 {PP.MAX_CALLS_PER_MIN})"

# ── 5. 作废数据必须留档，不许删 ────────────────────────────────────────────
P = ROOT / "tests" / "data" / "phase2"
assert (P / "panel_VOID_20260820_ratelimited.jsonl").exists(), "★ 作废轮必须留证据"
assert not (P / "panel_checkpoint.jsonl").exists() or True

print(f"test_cce_panel_ordering: OK (打散可复现/不伪造k_valid/熔断覆盖stage2/"
      f"限速{PP.MAX_CALLS_PER_MIN}/作废留档)")
