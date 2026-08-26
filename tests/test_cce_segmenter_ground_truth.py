#!/usr/bin/env python3
"""结构闸对已知填充的**还原**能力 —— 外审建议的零调用检验。

外审原话(2026-08-26): 「你这批实验的 filler 是人工已知的。所以对每个 padded fixture
运行新 segmenter, 必须 extract(mixed_input) == 原始 L0 base。这可以作为 CI,
不用再调用 CCE。」

**当前答案是 0/24 —— 一条都还原不出。** 本测试把这个事实钉住, 不是把它藏起来:
2x2 的填充是**无标记的产品规格散文**(「The serial number is printed on the back
panel beneath the battery door.」), 而当前 segmenter 只摘**标记可证**的段
(代码围栏/引用标记/整行只有链接) ⇒ 一个字都摘不掉。
⇒ 结构闸**没有**覆盖产生那 96% 不合格的机制。这是已知缺口, 见架构文档 §19.5.33。

但真正要紧的是第二条断言: **那 46 个不合格里没有一个是「自信的坏读数」**。
全部落在既有的两道安全网里(模型自己弃权 / k_valid<2 → WITHHOLD)。
⇒ 缺口是**可测性**问题(读不出), 不是**正确性**问题(读错)。
这个区分决定了要不要为它引入分类器 —— 别把两者混为一谈。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_structural_gate import structural_gate  # noqa: E402

D = ROOT / "tests" / "data" / "length_vs_dilution"
MAN = json.loads((D / "panel_manifest.json").read_text(encoding="utf-8"))
CKPT = [json.loads(l) for l in (D / "panel_checkpoint.jsonl").read_text(
    encoding="utf-8").splitlines() if l.strip()]

L0 = {a["base_id"]: a["text"] for a in MAN["arms"] if a["arm"] == "L0_unpadded"}
PADS = [a for a in MAN["arms"] if a["arm"] == "PAD"]
assert len(L0) == 24 and len(PADS) == 24

# ── ① 还原能力: 当前 0/24, 如实钉住 ────────────────────────────────────────
norm = lambda s: " ".join(s.split())
recovered = sum(1 for a in PADS
                if norm(structural_gate(a["text"])["subject_text"] or "") == norm(L0[a["base_id"]]))
assert recovered == 0, (
    f"★ 还原数从 0 变成 {recovered}/24。这可能是好事(加了语义分类器?), 但**必须重新报数**: "
    "架构文档 §19.5.33 与对 owner 的说法都写着「无标记的产品规格段当前漏摘」。")

# 漏摘是**全量**漏摘, 不是部分 —— 说明缺的是整整一类判据, 不是边角
dropped = [structural_gate(a["text"])["chars_dropped"] for a in PADS]
assert set(dropped) == {0}, \
    f"★ 当前应对 2x2 填充一字未摘, 实得 chars_dropped={sorted(set(dropped))}"

# ── ② ★ 真正要紧的: 那些不合格**全部安全失败**, 没有一个是自信的坏读数 ─────
pad_rows = [r for r in CKPT if r["arm"] == "PAD"]
unqual = [r for r in pad_rows if not r.get("qualified")]
assert len(pad_rows) == 96 and len(unqual) == 46, \
    f"fixture 变了: {len(pad_rows)} reps / {len(unqual)} 不合格"
abstained = [r for r in unqual if r.get("abstained")]
withheld = [r for r in unqual if not r.get("abstained")]
assert len(abstained) == 30, f"弃权数变了: {len(abstained)}"
assert all(r.get("k_valid", 99) < 2 for r in withheld), \
    ("★★ 出现了 k_valid>=2 的不合格 —— 那才是**自信的坏读数**, 属正确性事故。"
     "此前 16 个非弃权不合格全部是 k_valid=1 ⇒ WITHHOLD, 属安全失败。")
assert len(withheld) == 16

# L0 基线: 同样的 base 不加填充时, 96 reps 只有 4 个不合格且全是弃权
l0_rows = [r for r in CKPT if r["arm"] == "L0_unpadded"]
l0_unq = [r for r in l0_rows if not r.get("qualified")]
assert len(l0_unq) == 4 and all(r.get("abstained") for r in l0_unq), \
    "★ L0 基线应为 4 个不合格且全部是弃权"

print(f"test_cce_segmenter_ground_truth: OK (还原 {recovered}/24 —— 已知缺口, 已钉住 | "
      f"PAD 不合格 {len(unqual)}/96 全部安全失败: 弃权 {len(abstained)} + "
      f"WITHHOLD {len(withheld)}, 零个自信坏读数)")
