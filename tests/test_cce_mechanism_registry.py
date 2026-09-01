#!/usr/bin/env python3
"""机制登记表的守卫 —— §44 Phase 6 的验收 gate，逐条可执行。

## §44.9 事先写好的 gate（不是我现在补的）
> **6 Mechanism** | 每条 mechanism 记录都能追到 evidence_refs，且至少一次 replication
> | 反向：造一条无 evidence 的 mechanism，注册必须被拒

## 为什么它值得存在
本仓库产出过十几条机制结论，但它们只以散文形态躺在架构文档的 33 个 §19.5 小节里。
实测后果（2026-09-01）：owner 问「CCE 到哪一步了」，只能靠 grep 逐条重新推导 ——
**已确立的东西不可查询，等于每次都要重新确立一遍。**

## 为什么 REJECTED 必须能登记
被否决的机制和被确立的机制同样值钱。库里 21 条 rejected 记录的存在理由就是
「下一个 agent 会重做已被否决的实验」——本项目实际发生过。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_mechanism import REGISTRY, STATUS, audit, validate  # noqa: E402

reg, bad = audit()
M = reg["mechanisms"]

# ── ① 全表复核：每条的 evidence 必须现在仍然存在 ────────────────────────────
assert not bad, (
    f"★ 登记表复核失败 —— 有记录的证据文件已不存在：{bad}\n"
    "  机制登记的全部价值就是可追溯；追不到的记录比没有记录更坏。")
assert M, "★ 登记表为空 —— 那这道 gate 从未被观察到通过"

# ── ② §44.9 的反向测试，逐字执行 ────────────────────────────────────────────
assert validate({"id": "x", "claim": "x", "status": "TESTED", "evidence_refs": []}), \
    "★ 无 evidence 的机制被接受 —— §44.9 的反向测试原文正是这一条"

assert validate({"id": "x", "claim": "x", "status": "TESTED",
                 "evidence_refs": ["tests/data/DOES_NOT_EXIST.json"]}), \
    "★ 指向不存在文件的 evidence_ref 被接受 —— 那等于允许引用想象中的 artifact"

assert validate({"id": "x", "claim": "x", "status": "ESTABLISHED",
                 "evidence_refs": ["tests/data/phase2/panel_analysis.json"],
                 "replications": []}), \
    "★ ESTABLISHED 零复现被接受 —— §44.9 明写「且至少一次 replication」"

assert validate({"id": "x", "claim": "x", "status": "TESTED", "preregistered": True,
                 "evidence_refs": ["tests/data/phase2/panel_analysis.json"]}), \
    "★ 声称前登记却拿不出冻结件被接受 —— 事后声称前登记是最坏的一种"

# ── ③ 正向对照：合规记录必须被放行（否则是永远红）──────────────────────────
assert not validate({"id": "probe", "claim": "x", "status": "TESTED",
                     "evidence_refs": ["tests/data/phase2/panel_analysis.json"]}), \
    "★ 合规记录被误拒 —— 永远红与永远绿是同一种失效"

# ── ④ 被否决的机制必须留在表里，且指向取代它的那条 ──────────────────────────
rejected = [m for m in M if m["status"] == "REJECTED"]
assert rejected, \
    ("★ 表里一条 REJECTED 都没有。被否决的方案不登记，下一个 agent 就会重做它 —— "
     "本项目实际发生过，库里 21 条 rejected 记录正是为此。")
for m in rejected:
    assert m.get("reject_reason"), f"★ {m['id']} 被否决却没写理由，等于没登记"
    if m.get("superseded_by"):
        assert any(x["id"] == m["superseded_by"] for x in M), \
            f"★ {m['id']} 指向的取代者 {m['superseded_by']} 不在表里"

# ── ⑤ ESTABLISHED 必须能被推翻：每条要给 falsifier ─────────────────────────
for m in M:
    if m["status"] == "ESTABLISHED":
        assert m.get("falsifier"), \
            (f"★ {m['id']} 标为 ESTABLISHED 却没写 falsifier。"
             "说不出「什么结果会推翻它」的结论，不是结论，是信念。")

n = {s: sum(1 for m in M if m["status"] == s) for s in STATUS}
print(f"test_cce_mechanism_registry: OK ({len(M)} 条 · "
      + " / ".join(f"{s}{n[s]}" for s in STATUS if n[s])
      + " · 四条反向全拒 · 合规放行 · ESTABLISHED 均带 falsifier)")
