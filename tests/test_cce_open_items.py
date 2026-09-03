#!/usr/bin/env python3
"""未完成清单必须来自真相源, 且不许被悄悄清空。

2026-09-03 owner 两次点破我越界声报(「可以投产了」/ 收尾语气)。
⇒ 「还差什么」不由我口述, 由 scripts/cce_open_items.py 从各真相源现算。
本测试守两件事: ① 它确实在算, 不是硬编码 ② 三类不许混。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_open_items import items, BLOCKED, OPEN, DECIDED  # noqa: E402

rs = items()
assert rs, "★ 未完成清单为空 —— 要么真的全做完了(那就得有证据), 要么算错了"
kinds = {r["类"] for r in rs}
assert kinds <= {BLOCKED, OPEN, DECIDED}, kinds
for r in rs:
    assert r["项"] and r["证据"], f"★ 每项必须带证据: {r}"

# ── ★ 它必须**真的在算** —— 改一个真相源, 清单要跟着变 ──────────────
import json
import tempfile
import shutil
import cce_open_items as M

_bak = tempfile.mkdtemp()
_p = os.path.join(ROOT, "config", "cce_chain_conformance.json")
shutil.copy2(_p, _bak)
try:
    d = json.load(open(_p, encoding="utf-8"))
    for ph in d["phases"]:
        if ph["phase"].startswith("P0"):
            ph["status"] = "NOT_STARTED"
    json.dump(d, open(_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mutated = M.items()
    assert any("P0" in r["项"] for r in mutated), \
        "★ 改了 chain_conformance 清单却没变 —— 它没在算, 是硬编码的"
finally:
    shutil.copy2(os.path.join(_bak, os.path.basename(_p)), _p)
    shutil.rmtree(_bak, ignore_errors=True)

# ── 三类的语义边界不许糊 ──────────────────────────────────────────────
blocked = [r for r in rs if r["类"] == BLOCKED]
assert blocked, "★ 至少 SESOI 与内容 A/B 是卡在外部资源上的"
for r in blocked:
    assert any(w in r["证据"] for w in ("人类评分者", "浏览", "素材", "触达")), \
        f"★ 标 BLOCKED 必须说清卡在**什么外部资源**上: {r}"
decided = [r for r in rs if r["类"] == DECIDED]
assert decided, "★ 已裁定不做的要留着防重开"

print(f"test_cce_open_items: OK (共 {len(rs)} 项 · "
      f"OPEN {sum(1 for r in rs if r['类']==OPEN)} / "
      f"BLOCKED {len(blocked)} / DECIDED {len(decided)} | "
      "改真相源清单会跟着变(非硬编码) | BLOCKED 各自写明卡在什么资源上)")
