#!/usr/bin/env python3
"""文档↔代码对照表自己的反向测试。

一张「全部对上了」的对照表是本项目最危险的产物形态之一 —— 它看起来像核对过,
实际可能只是一份没人验证的声明。所以这张表必须能被打红,
而且**「有闸」这句话本身**必须可验证: GATE 声明要指向真实文件 + 证据串 + 会跑过的测试。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_doc_reconcile as dr  # noqa: E402

SPEC = json.load(open(dr.SPEC, encoding="utf-8"))

# ── 正向 ───────────────────────────────────────────────────────────────
ok, errors, live = dr.check(run_tests=False)
assert ok, f"基线必须绿: {errors}"
assert sum(live.values()) == 25, "§43 是 25 条铁律"
assert live["GATE"] == 14 and live["FIELD_ONLY"] == 6 and live["PROSE_ONLY"] == 5

# ★ 核心数字: 11/25 条铁律没有任何东西会因违反它而变红
unguarded = live["FIELD_ONLY"] + live["PROSE_ONLY"]
assert unguarded == 11, f"无闸的铁律应为 11 条, 实测 {unguarded}"

# ── GATE 声明必须真的可验证(不是自称) ──────────────────────────────────
for n, v in SPEC["iron_laws"].items():
    if v["kind"] != "GATE":
        continue
    f = os.path.join(ROOT, v["file"])
    assert os.path.exists(f), f"铁律{n} 声明的 {v['file']} 不存在"
    assert v["evidence"] in open(f, encoding="utf-8").read(), \
        f"★ 铁律{n} 的证据串 {v['evidence']!r} 不在 {v['file']} 里 —— 「有闸」是假的"
    assert os.path.exists(os.path.join(ROOT, v["test"])), f"铁律{n} 的测试不存在"

# ── 反向 ───────────────────────────────────────────────────────────────
def alt(mutate, run_tests=False):
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "spec.json")
        s = json.loads(json.dumps(SPEC))
        mutate(s)
        json.dump(s, open(p, "w"), ensure_ascii=False)
        return dr.check(p, run_tests=run_tests)

# 1. 把一条 PROSE_ONLY 谎报成 GATE(不给证据) -> 红
ok1, e1, _ = alt(lambda s: s["iron_laws"]["4"].update({"kind": "GATE"}))
assert not ok1 and any("没写" in x for x in e1), "★ 标 GATE 却不给证据必须红"

# 2. GATE 指向不存在的文件 -> 红
ok2, e2, _ = alt(lambda s: s["iron_laws"]["6"].update({"file": "scripts/nope.py"}))
assert not ok2 and any("不存在" in x for x in e2)

# 3. ★ GATE 的证据串在文件里找不到 -> 红("有闸"这句话是假的)
ok3, e3, _ = alt(lambda s: s["iron_laws"]["6"].update({"evidence": "这句话不在文件里"}))
assert not ok3 and any("「有闸」这句话是假的" in x for x in e3), \
    "★ 证据串对不上必须红 —— 否则可以随便声称有闸"

# 4. FIELD_ONLY 不写「什么都不会失败」的说明 -> 红
ok4, e4, _ = alt(lambda s: s["iron_laws"]["21"].pop("note"))
assert not ok4 and any("必须写明" in x for x in e4)

# 5. summary 与实际不符 -> 红(防止改了分类忘了改汇总)
ok5, e5, _ = alt(lambda s: s["iron_law_summary"].update({"GATE": 20}))
assert not ok5 and any("不符" in x for x in e5)

# 6. 少一条铁律 -> 红
ok6, e6, _ = alt(lambda s: s["iron_laws"].pop("25"))
assert not ok6 and any("25 条" in x for x in e6)

# 7. 章节判定不带理由 -> 红
ok7, e7, _ = alt(lambda s: s["section_divergences"][0].pop("note"))
assert not ok7 and any("必须带 note" in x for x in e7)

# 8. ★ 抹掉「未覆盖哪些章节」-> 红
ok8, e8, _ = alt(lambda s: s.update({"★not_covered": "全部核完了"}))
assert not ok8 and any("未覆盖" in x for x in e8), \
    "★ 必须写明本次没核哪些章节 —— 上次就是把一节当成了全集"

# ── 章节判定必须与实际一致(抽查两条最重的) ─────────────────────────────
d = {x["section"]: x for x in SPEC["section_divergences"]}
assert not os.path.exists(os.path.join(ROOT, "contracts")), \
    "§39 判「文档过时」的前提是没有 contracts/ 目录"
assert os.path.exists(os.path.join(ROOT, "config", "cce_ledgers_v1.json")), \
    "§42 判「符合」的前提是四条账已声明"
assert "必须" in d["§42 四条独立 Ledger"]["note"], \
    "★ §42 用的是「必须分开」, 是规范不是建议 —— 这一点必须写明"
# 2026-09-02: §42 已补上准入闸, 判定改为「符合」—— 但「符合」必须有闸支撑
assert d["§42 四条独立 Ledger"]["verdict"] == "符合"
g = d["§42 四条独立 Ledger"]["gate"]
assert os.path.exists(os.path.join(ROOT, g["file"])) and os.path.exists(os.path.join(ROOT, g["test"]))
ok9, e9, _ = alt(lambda s: s["section_divergences"][1].pop("gate"))
assert not ok9 and any("必须给出真实存在的 gate" in x for x in e9), \
    "★ 判「符合」却不给闸必须红 —— 否则「符合」就是自称"

print(f"test_cce_doc_reconcile: OK "
      f"(§43 25 条: GATE {live['GATE']} / FIELD_ONLY {live['FIELD_ONLY']} / "
      f"PROSE_ONLY {live['PROSE_ONLY']} ⇒ **{unguarded} 条无闸** | "
      f"14 条 GATE 的证据串全部实存 | 8 条反向各自见红 | "
      f"§39 文档过时 · §42 代码欠账 各自有实据)")
