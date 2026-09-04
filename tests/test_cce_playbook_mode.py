#!/usr/bin/env python3
"""playbook 众数占比判定 —— INCONCLUSIVE, 且**必须留在不可用**。

## 这条测试守的不是「结果好不好」, 是「差一个也是差」
预注册: 8 个文本, 达标 >= 7。**实测 6。** ⇒ 不得采纳。
★ 三件事一律不做, 各有断言钉住:
  ① 重跑换一个好点的抽样 ② 事后下调阈值 ③ 把 v1 与 v2 合并凑够数

## 但改善是真的, 也要如实记
同样 8 个文本: 旧判据(逐对容差一致 >=0.95)达标 **4/8**, 新判据(众数占比 >=7/8)达标 **6/8**。
非退化也变好: v1 里 6/8 个文本众数是 0.0, 本轮最多 5/8 共用同一众数。
**改善没到线 != 改善不存在。** 两句都要说。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import playbook_mode_usable, playbook_hit_usable  # noqa: E402

P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "playbook_mode_verdict.json"), encoding="utf-8"))
S = json.load(open(os.path.join(P, "playbook_mode_prereg.json"), encoding="utf-8"))
V1 = json.load(open(os.path.join(P, "playbook_hit_verdict.json"), encoding="utf-8"))
INST = "565470cf26c16d01"

# ── 判据与选文都是测量前冻结的 ────────────────────────────────────────
assert V["★decision_rule_frozen_at"] == S["prereg_written_at"]
assert V["instrument_hash"] == INST == S["instrument"]["must_equal"]
assert V["texts"] == 8 and all(p["n"] == 8 for p in V["per_text"].values())

# ── ★ 选文必须与前两轮全部错开(不许同批既调参又验收) ──────────────────
assert not (set(V["per_text"]) & set(V1["per_text"])), \
    "★ 与 playbook_hit v1 用了同一批文本"
_k1v2 = json.load(open(os.path.join(P, "k1_v2_multitext_verdict.json"), encoding="utf-8"))
assert not (set(V["per_text"]) & set(_k1v2["layers"]["intensity"]["per_text"])), \
    "★ 与 K1-v2 用了同一批文本"

# ── ★ 核心: 差一个也是差 ──────────────────────────────────────────────
assert V["decision"] == "INCONCLUSIVE", V["decision"]
assert V["meeting_criterion"] == 6 and V["required"] == 7, V
ok, why = playbook_mode_usable(instrument_hash=INST)
assert not ok and "未到线" in why, why
assert not playbook_hit_usable(instrument_hash=INST)[0], "★ 旧的标量形式也仍不可用"

# ── ★ 阈值不许事后下调 ────────────────────────────────────────────────
assert S["criterion"]["mode_share_min"] == 0.875 and S["criterion"]["texts_meeting_min"] == 7, \
    "★ 预注册的阈值被改了 —— 那是事后调判据"
assert "★threshold_chosen_after_seeing_v1_data" in S["design_change"], \
    "★ 阈值是看过 v1 数据后定的, 这件事必须留在预注册里"
assert "不得采纳" in V["★what_i_may_not_do"] and "合并" in V["★what_i_may_not_do"]

# ── 改善是真的, 也要留着 ──────────────────────────────────────────────
assert V1["meeting_criterion"] == 4, "★ v1 的 4/8 是对照基线"
assert V["meeting_criterion"] > V1["meeting_criterion"], \
    "★ 若新形式并不更好, 「改形式有改善」这句要撤回"
assert "改善没到线" in V["★what_improved"] or "但改善没到线" in V["★what_improved"]

# ── 非退化: 本轮过了, 地板效应的担心减轻 ──────────────────────────────
d = V["degeneracy"]
assert d["passes"] and d["distinct_modes"] >= 2 and d["texts_sharing_top_mode"] <= 7, d
assert d["texts_sharing_top_mode"] < 6, \
    f"★ 若又变成 6+/8 共用同一众数, 地板效应的担心要重新提出: {d}"

# ── 对齐线整体关闭这件事要写明 ────────────────────────────────────────
assert "对齐线" in V["★consequence"] and "先扩文本" in V["★consequence"], \
    "★ 后续方向(先扩文本不是加 rep)要留着 —— 那是成本曲线的教训"

print(f"test_cce_playbook_mode: OK (达标 {V['meeting_criterion']}/8 需 {V['required']} ⇒ "
      f"{V['decision']}, **差一个也是差** | 选文与前两轮全错开 | "
      f"改善属实(旧判据 4/8 → 新 6/8, 非退化由 6/8 同众数降到 "
      f"{d['texts_sharing_top_mode']}/8)但未到线 | 对齐线保持关闭)")
