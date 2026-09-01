#!/usr/bin/env python3
"""守住「旧九环节链已从入口移除」—— 这是一个**复发三次**的事故的结构性修复。

## 复发史（记忆库有据）
- 2026-08-13：拿旧 s0-s8 当尺子问「过了 cce 全链没有」
- 2026-08-14：把 s8 写进判注
- 2026-08-14：帖15 九条 run 全部跑在旧链上，还误报「9/9 全绿」

三次同形，因为**退役只写进了文档和记忆，代码里那条路一直是通的**：
`.github/prepare.py` 允许 `mode=post`，`CHAINS["post"]` 就在那里。
2026-09-01 从入口直接删除。本文件保证它不会悄悄回来。

## 真正的不变量
不是「post 不存在」这一条，而是 **prepare.py 的模式白名单 == CHAINS 的键集**。
两者任一侧单独增删都会红 —— 上一次正是它们不一致（契约无 post、入口有 post）
持续数周而无人发现。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_full_run import CHAINS  # noqa: E402

PREPARE = (ROOT / ".github" / "prepare.py").read_text(encoding="utf-8")
FULLRUN = (ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8")

# ── ① 入口白名单 == CHAINS 键集（核心不变量）────────────────────────────────
m = re.search(r'if mode not in \(([^)]*)\):', PREPARE)
assert m, "★ prepare.py 的模式白名单形状变了，本守卫失效 —— 修它，别删它"
allowed = set(re.findall(r'"([a-z_]+)"', m.group(1)))
assert allowed == set(CHAINS), (
    f"★ 入口白名单 {sorted(allowed)} != CHAINS 键 {sorted(CHAINS)}。\n"
    "  两者必须逐个相等：入口允许而 CHAINS 没有 ⇒ 运行时崩；\n"
    "  CHAINS 有而入口不允许 ⇒ 死代码，正是 post 那条路的形态（持续数周无人发现）。")

# ── ② 退役链不得回来 ────────────────────────────────────────────────────────
assert "post" not in CHAINS, \
    '★ "post"(旧九环节 s0-s8)于 2026-08-13 退役、2026-09-01 从入口删除。它回来了。'
RETIRED = ("s5_audience", "s6_alignment", "s7_ruler", "s8_pairwise_bet")
live = {l.split('"')[1] for l in FULLRUN.splitlines() if l.startswith("@stage(")}
for r in RETIRED:
    assert r not in live, f"★ 退役段 {r} 又被注册成 @stage —— 引擎不再产生任何下注/对齐判决"

# ── ③ 现存 stage 必须全部被某个 profile 用到（防再长出孤儿段）──────────────
import json  # noqa: E402
contract = json.loads((ROOT / "config" / "cce_submission_contract_v1.json").read_text(encoding="utf-8"))
used = {s for p in contract["profiles"].values() for s in p["stages"]}
orphan = {s for s in live if s not in used}
assert not orphan, \
    (f"★ 这些 stage 没有任何 profile 用到：{sorted(orphan)}。"
     "孤儿段就是下一个 s5-s8 —— 要么接进契约，要么删掉。")

# ── ④ 整链驱动不得有第二份副本 ──────────────────────────────────────────────
dups = [p for p in ROOT.rglob("cce_full_run.py") if p != ROOT / "scripts" / "cce_full_run.py"]
assert not dups, \
    (f"★ 整链驱动出现副本：{[str(d.relative_to(ROOT)) for d in dups]}。"
     "config/cce_full_run.py 曾与 scripts/ 版差 401 行且无人引用，"
     "而它自己 docstring 写着「唯一入口」。库里已否决「双份维护不可收敛」。")

print(f"test_cce_retired_chain_removed: OK (白名单=CHAINS键 {sorted(allowed)} / "
      f"退役段 0 个 / 孤儿段 0 个 / 驱动无副本)")
