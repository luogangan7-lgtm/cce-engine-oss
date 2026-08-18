#!/usr/bin/env python3
"""Observation 层: 跨次信度的空缺必须在**数据里**显形, 不能只在注释里。

理由(2026-08-18): `confidence = 1 - mean(within_js)` 只覆盖同一次运行内 k 档温度的散布。
同一批实验里, 九结侧组内闸全绿而重跑结集一致率只有 0.50/0.50/0.33 ——
**组内稳不蕴含跨次稳**。而每条 observed response 只测一次, 跨次信度**结构上未被测量**。
下游若只看 confidence, 会把「组内稳」读成「这条读数可靠」。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_response_chain as RC  # noqa: E402

src = (ROOT / "scripts" / "cce_response_chain.py").read_text(encoding="utf-8")

# 1. 字段必须存在于 _measurement 的返回体里
assert '"across_run_reliability": None' in src, "跨次信度空缺必须以字段形式出现"
assert '"across_run_reliability_reason"' in src, "空缺必须带理由, 否则下游不知道它为什么是 None"

# 2. ★ 反向测试: 若有人把它填成一个数, 必须有依据 —— 这里钉住「不得默认填 1.0」
assert '"across_run_reliability": 1.0' not in src and '"across_run_reliability": 1' not in src, \
    "禁止默认填满分 —— 那正是 confidence 被误读的原因, 换个字段重犯一次没有意义"

# 3. confidence 的语义串必须仍在, 且明确写着 within-run
assert "within-run repeatability" in src
assert "not probability of truth" in src

# 4. 两个字段必须相邻出现(同一处返回体), 防止有人把空缺挪到别处淡化它
i_c, i_a = src.index('"confidence": repeatability'), src.index('"across_run_reliability"')
assert 0 < i_a - i_c < 1200, "空缺字段必须紧跟 confidence, 不许挪远"

# 5. 契约不得因新字段而拒绝 —— _require 是必填清单, 不是白名单
csrc = (ROOT / "scripts" / "cce_contract.py").read_text(encoding="utf-8")
assert "additionalProperties" not in csrc, \
    "若契约改成白名单模式, 本字段会被拒 —— 那时必须同步登记, 而不是删掉字段"

print("test_cce_observation_gap: OK (空缺入数据 / 禁止默认满分 / 位置锁定 / 契约兼容)")

# ── 6. 实测钉死: 字段的理由是「未测量」, 不是「已知不可靠」 ──────────────────
import json, statistics as _st  # noqa: E402
BL = ROOT / "tests" / "data" / "p2_stage1_baseline_20260818.json"
if BL.exists():
    bl = json.loads(BL.read_text(encoding="utf-8"))
    # 6a. ★ stage1 也没有「空读数」: 无人称文本距均匀的 JS 与真人文本相当
    j = bl["js_from_uniform"]
    hum = _st.mean(j["HUMAN_base"].values())
    fil = _st.mean(_st.mean(v.values()) for k, v in j.items() if k != "HUMAN_base")
    assert 0.8 < fil / hum < 1.25, f"无人称/真人 JS 比 ={fil/hum:.2f}, 应当相当"
    # 一张纯数字表被读出明确的欲望峰值 —— 这是「无空读数」最直观的证据
    assert j["filler_numeric"]["desire_vec"] > 0.15, j["filler_numeric"]
    # 6b. ★ across/within 全部 <1, 中位 ≈1/k —— **未检出**额外跨次漂移
    rr = [c["ratio"] for row in bl["within_vs_across"].values()
          for c in row.values() if c["ratio"]]
    assert max(rr) < 1.0, f"若出现 >1 的格, 「未检出漂移」的说法需重审: max={max(rr)}"
    assert 0.25 < _st.median(rr) < 0.55, f"中位应接近 1/k=0.33, 实得 {_st.median(rr):.2f}"
    # 6c. ★ 反向断言: 禁止在代码里用「confidence 高估」当保留字段的理由(无证据)
    assert "高估" not in src or "那条没有证据" in src, \
        "「confidence 高估」已被 run 32150369795 推翻, 不得再作为理由留在代码里"
    print("  实测已钉: stage1 无空读数(比值 %.2f) / across-within 中位 %.2f 未检出额外漂移"
          % (fil / hum, _st.median(rr)))
