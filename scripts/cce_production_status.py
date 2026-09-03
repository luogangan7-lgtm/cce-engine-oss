#!/usr/bin/env python3
"""「CCE 能不能投产」不由一句话回答, 由这里逐项算出来。

## 为什么存在
2026-08-07 owner 指控「你一直欺骗我说跑了完整的 cce」, 指控成立。当时立的硬规则:
  · **禁用裸的「完整/全链路」字样** —— 必须给逐项清单(组件 + 跑/没跑 + 文件路径)
  · 任何「已验证/已通过」必须附 gate 名 + 数字 + 判据
  · **「未验」标注 + 继续越界使用 = 用免责声明掩护过度声报, 等同欺骗**

2026-09-03 我又犯了一次: 说「现在可以投产了」再挂一张 caveat 表。
⇒ 把这句话从「我说」改成「仓库算」。**三档: 可用 / 已测不达标 / 未测。**
★ 「未测」与「已测不达标」必须分开 —— not started is not green, 判过不合格也不是 not started。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

USABLE, FAILED, UNMEASURED = "可用", "已测·不达标", "未测"


def _j(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def rows() -> list[dict]:
    from cce_k1_status import knot_readout_usable
    inst = "565470cf26c16d01"
    v2 = _j("tests/data/phase2/k1_v2_multitext_verdict.json")
    panel = _j("tests/data/phase2/intensity_across_panel.json")
    cap = {c["id"]: c for c in _j("config/cce_capability_registry_v1.json")["capabilities"]}
    out = []

    # ── 读数层 ────────────────────────────────────────────────────────
    ok, why = knot_readout_usable("top1", instrument_hash=inst)
    out.append({"组件": "结层 top-1", "状态": USABLE if ok else FAILED,
                "证据": why, "文件": "scripts/cce_k1_status.py"})

    a = panel["agreement"]
    out.append({"组件": "结层 intensity", "状态": FAILED,
                "证据": (f"K1-v2 预注册判定 {v2['layers']['intensity']['passed_texts']}/"
                         f"{v2['layers']['intensity']['of']} 文本; "
                         f"面板复核 {panel['texts']} 文本 A 均值 {a['mean']}, "
                         f"达 0.95 仅 {a['texts_meeting_0.95']}/{panel['texts']}"),
                "文件": "tests/data/phase2/k1_v2_multitext_verdict.json"})
    out.append({"组件": "结层 weight", "状态": FAILED,
                "证据": (f"K1-v2 预注册判定 {v2['layers']['weight']['passed_texts']}/"
                         f"{v2['layers']['weight']['of']} 文本(面板无 weight, 无法复核)"),
                "文件": "tests/data/phase2/k1_v2_multitext_verdict.json"})

    # ── 对齐 ──────────────────────────────────────────────────────────
    sens = _j("tests/data/phase2/align_theta_sensitivity.json")
    out.append({"组件": "九结加权对齐分", "状态": FAILED,
                "证据": (f"θ={sens['theta']} 判决 {sens['verdict_flip_rate']:.1%} 被 weight 抖动翻转"
                         f"(该数是**下界**, 未含 dissolve_hit 噪声); 已随 weight 扣发"),
                "文件": "probes/align_theta_sensitivity.py"})
    out.append({"组件": "top-1 playbook_hit(现行对齐出口)", "状态": UNMEASURED,
                "证据": ("★ 它自身是 3 次 LLM 表决取中位数, **复现性从未测过**; "
                         "历史归档从未落过 reply_alignment 产物, 补不上 ⇒ 要测必须新花钱"),
                "文件": "scripts/reply_loop.py(top1_align)"})

    # ── 媒体 ──────────────────────────────────────────────────────────
    out.append({"组件": "媒体**存在**声明", "状态": USABLE,
                "证据": f"能力 {cap['media_presence_declaration']['status']}; 出站两档入口必填, FAIL_CLOSED",
                "文件": ".github/prepare.py"})
    out.append({"组件": "媒体**内容**测量", "状态": UNMEASURED,
                "证据": ("组件已在 276 个真实视频上跑过, 但 ①未接进生产链(component_only) "
                         "②抽样 80 个里 zh69/ko7/en2 —— **与英文助听器论坛不是一个域**"),
                "文件": "scripts/cce_video_parse.py"})

    # ── s1 分布层 ─────────────────────────────────────────────────────
    out.append({"组件": "s1 四层分布", "状态": USABLE,
                "证据": "同侧 K=3 JS 0.02–0.09(信度已测); 不受 K1 判定影响",
                "文件": "scripts/cce_knot_classify.py(stage1)"})
    return out


def main() -> int:
    rs = rows()
    print("=" * 74)
    print("CCE 投产逐项清单 —— 「能不能投产」不是一句话, 是这张表")
    print("=" * 74)
    w = max(len(r["组件"]) for r in rs)
    for r in rs:
        mark = {"可用": "✓", "已测·不达标": "✗", "未测": "?"}[r["状态"]]
        print(f" {mark} {r['组件']:<{w}}  {r['状态']}")
        print(f"     {r['证据']}")
        print(f"     └─ {r['文件']}")
    n = {s: sum(1 for r in rs if r["状态"] == s) for s in (USABLE, FAILED, UNMEASURED)}
    print("-" * 74)
    print(f"可用 {n[USABLE]} · 已测不达标 {n[FAILED]} · **未测 {n[UNMEASURED]}**")
    print("★ 「未测」不是「弱证据」, 是没有读数。它与「已测不达标」是两种状态, 修法也不同。")
    print("★ 引擎跑得动(70/70 测试绿·七闸 PASS) != 这些读数能用。两件事不许合并成「可以投产」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
