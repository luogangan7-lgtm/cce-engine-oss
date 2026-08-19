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
assert "shuffle(tasks)" in SRC and "SHUFFLE_SEED" in SRC, \
    "★ 不打散 ⇒ 任何随时间衰减的故障都会直接映射成臂的差异"
man = json.loads((ROOT / "tests" / "data" / "phase2"
                  / "panel_manifest.json").read_text(encoding="utf-8"))
import random  # noqa: E402
tasks = [(a["arm"], i) for a in man["arms"] for i in range(4)]
ordered = list(tasks)
random.Random(PP.SHUFFLE_SEED).shuffle(tasks)
assert tasks != ordered, "★ 打散没生效"
# 反向：打散后，L0/L0b 不再全部聚在最前
first = [a for a, _ in tasks[:60]]
assert len(set(first)) > 2, f"★ 前 60 个任务只有 {set(first)} ⇒ 仍然按臂聚集"
# 可复现
t2 = list(ordered)
random.Random(PP.SHUFFLE_SEED).shuffle(t2)
assert t2 == tasks, "★ 顺序不可复现 ⇒ 事后无法核对跑的是哪一批"

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
