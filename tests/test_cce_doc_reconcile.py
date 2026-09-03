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
assert sum(live[k] for k in dr.KINDS) == 25, "§43 是 25 条铁律"
assert live["GATE"] == 25 and live["FIELD_ONLY"] == 0 and live["PROSE_ONLY"] == 0

# ★ 核心数字: 还有几条铁律违反了不会红
unguarded = live["FIELD_ONLY"] + live["PROSE_ONLY"]
assert unguarded == 0, f"25 条铁律现已全部有闸, 实测仍有 {unguarded} 条无闸"
# ★ 19 条 GATE != 19 套保护: 5/9/11 是同一条 Ledger 准入闸的三个面
# ★ 25 条 GATE != 25 套保护: 5/9/11 与 4/8 共用 Ledger 准入闸, 3 与 2 共用组装器
assert live["SHARED"] == 5 and live["INDEPENDENT"] == 20, \
    f"独立机制应为 20 套(GATE 25 - 共用 5), 实测 {live['INDEPENDENT']}"
# 2026-09-02: 铁律 21 升 GATE; 2026-09-03: 5/9/11(Ledger 准入闸) 与 23(caveat 双向断言) 同升
assert SPEC["iron_laws"]["21"]["kind"] == "GATE"
for n in ("21", "5", "9", "11", "23", "1", "2", "3", "4", "8", "25"):
    assert SPEC["iron_laws"][n]["kind"] == "GATE"
    assert SPEC["iron_laws"][n].get("upgraded_from"), \
        f"★ 铁律{n} 升级必须留痕: 它此前是什么档、为什么当时不算闸"

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

# 1. 谎报成 GATE 却不给证据 -> 红
#    25 条已全部是 GATE ⇒ 构造一条无证据的 GATE 来验这条检查还活着
def _bare_gate(s):
    s["iron_laws"]["4"] = {"law": "State ≠ Behavior", "kind": "GATE"}
ok1, e1, _ = alt(_bare_gate)
assert not ok1 and any("没写" in x for x in e1), "★ 标 GATE 却不给证据必须红"

# 2. GATE 指向不存在的文件 -> 红
ok2, e2, _ = alt(lambda s: s["iron_laws"]["6"].update({"file": "scripts/nope.py"}))
assert not ok2 and any("不存在" in x for x in e2)

# 3. ★ GATE 的证据串在文件里找不到 -> 红("有闸"这句话是假的)
ok3, e3, _ = alt(lambda s: s["iron_laws"]["6"].update({"evidence": "这句话不在文件里"}))
assert not ok3 and any("「有闸」这句话是假的" in x for x in e3), \
    "★ 证据串对不上必须红 —— 否则可以随便声称有闸"

# 4. FIELD_ONLY 不写「什么都不会失败」的说明 -> 红
# 25 条已全部升 GATE ⇒ 现场没有 FIELD_ONLY 可用, 构造一条来验这条检查还活着
def _mk_field_only(s):
    s["iron_laws"]["1"] = {"law": "Raw ≠ Observation", "kind": "FIELD_ONLY"}
    s["iron_law_summary"]["GATE"] -= 1; s["iron_law_summary"]["FIELD_ONLY"] += 1
ok4, e4, _ = alt(_mk_field_only)
assert not ok4 and any("必须写明" in x for x in e4), \
    "★ FIELD_ONLY 不写「什么都不会失败」仍必须红 —— 全升 GATE 后这条检查不能就此失效"

# 4b. ★ 谎称与另一条共用机制(实际不是同一个文件) -> 红
ok4b, e4b, _ = alt(lambda s: s["iron_laws"]["9"].update({"shares_mechanism_with": "23"}))
assert not ok4b and any("共用是假的" in x for x in e4b), \
    "★ 共用机制的声明必须可核 —— 否则可以拿一套闸认领任意多条铁律"

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

# ── §45 矩阵 37 项 ─────────────────────────────────────────────────────
m45 = SPEC["section_45_matrix"]
assert sum(v["declared"] for v in m45.values() if isinstance(v, dict) and "declared" in v) == 37
assert m45["① 已具备或接近具备"]["verdict"] == "文档属实" and m45["① 已具备或接近具备"]["verified"] == 11
assert m45["② 部分具备"]["verdict"] == "文档属实"
assert m45["③ 当前缺失或未生产化"]["verdict"] == "文档过时"
a3 = m45["③ 当前缺失或未生产化"]["actual"]
assert a3["仍缺"] + a3["部分"] + a3["已实现"] == 13
assert len(m45["③ 当前缺失或未生产化"]["still_missing"]) == a3["仍缺"] == 7
assert len(m45["③ 当前缺失或未生产化"]["now_implemented"]) == a3["已实现"] == 5
a4 = m45["④ 研究未定"]["actual"]
assert a4["仍未定"] + a4["已定"] == 7 and len(m45["④ 研究未定"]["settled"]) == 2
# ★ 核对方法必须留在产物里 —— 我在这一节里连踩三次「命中 != 实现」
assert "命中 != 实现" in m45["★method"] and "__pycache__" in m45["★method"], \
    "★ 三次踩坑的过程必须留痕, 否则下次还会拿 grep 命中当证据"

# 反向: 判「文档过时」却不给 actual -> 红
okA, eA, _ = alt(lambda s: s["section_45_matrix"]["③ 当前缺失或未生产化"].pop("actual"))
assert not okA and any("必须给出 actual" in x for x in eA)
# 反向: 判「属实」但数对不上 -> 红
okB, eB, _ = alt(lambda s: s["section_45_matrix"]["① 已具备或接近具备"].update({"verified": 3}))
assert not okB and any("verified != declared" in x for x in eB)
# 反向: 抹掉核对方法 -> 红
okC, eC, _ = alt(lambda s: s["section_45_matrix"].update({"★method": "查了一下"}))
assert not okC and any("命中 != 实现" in x for x in eC)

# ── §1–§35 ────────────────────────────────────────────────────────────
s135 = SPEC["sections_1_35"]
f2 = {f["claim"][:20]: f for f in s135["checked"]["§2 当前生产基线"]["findings"]}
assert len(f2) == 6
# 2026-09-02: §2.1 那条此前「当前不成立」, owner 裁定摘除 cce.yml 的 cce_full_run 调用后已成立。
compat = [f for f in s135["checked"]["§2 当前生产基线"]["findings"] if "兼容工作流" in f["claim"]][0]
assert compat["verdict"] == "属实(2026-09-02 起)", \
    "★ 摘除已落地, 判定必须跟着改 —— 但要带日期, 不能假装它一直成立"
assert "两个章节独立查出" in compat["★note"], \
    "★ 同一处分歧被 §37 与 §2.1 两个章节独立查出 —— 这一点值得留痕"
assert "闸自己也暴露了一个 bug" in compat["★note"], \
    "★ 摘除时闸把注释里的 cce_full_run 也算成「能产」, 这个自伤必须留痕"
# 实查: 摘除是真的落地了, 不只是改了个判定
import sys as _s
_s.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_registry_gate import can_emit_complete as _emit  # noqa: E402
assert not _emit(".github/workflows/cce.yml"), "★ 判「属实」的前提是 cce.yml 真的不能产 complete 了"
assert sum(1 for p in json.load(open(os.path.join(ROOT, "config", "cce_workflow_registry_v1.json"),
                                     encoding="utf-8"))["workflows"] if _emit(p)) == 1, \
    "★ 摘除后只剩唯一生产入口"
assert s135["checked"]["§27 Evidence / Provenance Plane"]["verdict"] == "异名分散"
assert "generated_by" in s135["checked"]["§27 Evidence / Provenance Plane"]["detail"]
assert "不得" in s135["not_machine_checkable"]["★do_not_claim"]

# 反向: 不可机器核的部分不写理由 -> 红
okD, eD, _ = alt(lambda s: s["sections_1_35"]["not_machine_checkable"].pop("why"))
assert not okD and any("必须写明为什么" in x for x in eD)
# 反向: 判定既无 evidence 也无 note -> 红
def _strip(s):
    f = s["sections_1_35"]["checked"]["§2 当前生产基线"]["findings"][0]
    f.pop("evidence", None); f.pop("note", None)
okE, eE, _ = alt(_strip)
assert not okE and any("既无 evidence 也无 note" in x for x in eE)

print(f"test_cce_doc_reconcile: OK "
      f"(§43 25 条: GATE {live['GATE']} / FIELD_ONLY {live['FIELD_ONLY']} / "
      f"PROSE_ONLY {live['PROSE_ONLY']} ⇒ **{unguarded} 条无闸(25/25 全覆盖)** | "
      f"GATE {live['GATE']} 条但**独立机制仅 {live['INDEPENDENT']} 套**(5/9/11+4/8 共用 Ledger 准入闸, 2/3 共用组装器) | "
      f"{live['GATE']} 条 GATE 的证据串全部实存 | 9 条反向各自见红 | "
      f"§39 文档过时 · §36/§37/§42 已补闸 | "
      f"§45 37 项(①②属实·③④过时) · §1–§35 只核存在性声明节(§2 那条已由 owner 裁定摘除并落地))")
