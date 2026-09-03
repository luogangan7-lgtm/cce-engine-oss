#!/usr/bin/env python3
"""链路符合性核对自身的反向测试。

一张「全绿的链路对照表」是本项目最危险的产物形态 —— 它看起来像交付, 实际可能
只是一张没人验证过的图。所以这张表自己必须能被打红。
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_chain_conformance as cc  # noqa: E402

SPEC = json.load(open(cc.MAP, encoding="utf-8"))

# ── 正向 ───────────────────────────────────────────────────────────────
ok, errors, stats = cc.check()
assert ok, f"基线必须绿: {errors}"
assert stats["chain_total"] == 15, "§48 最简总图是 15 段"
assert stats["chain_implemented"] == 15 and stats["chain_tested"] == 15
assert stats["phases_total"] == 8, "§44 是八阶段 P0–P7"
assert stats["phases_pass"] == 8

# ★ 关键: gate 全过 ≠ 八个 Phase 都做完了
# 2026-09-03: P3 进生产(profile media_ingest, 全链回放 complete=true) ⇒ 6/8 → 7/8。
# 仍未完成的只剩 P4 —— 它是**已测不达标**, 不是没做。
assert stats["phases_done"] == 7, \
    f"内容已建的应当是 7/8 (只剩 P4, 它是已测不达标), 实测 {stats['phases_done']}"
undone = [p for p in SPEC["phases"] if not p["status"].startswith("DONE")]
assert {p["phase"] for p in undone} == {"P4 九结 Research"}

# ★ P3 虽以 DONE 开头, 但它是**带具名扣发**的 DONE —— 「进生产」!= 「全部读数可用」
_p3 = [p for p in SPEC["phases"] if p["phase"].startswith("P3")][0]
assert _p3["status"] == "DONE_WITH_SCOPED_WITHHOLDING", _p3["status"]
assert "抽出来了 != 抽得准" in _p3["why"], \
    "★ 抽取质量未测这件事必须留在 P3 的说明里, 不能因为进了生产就抹掉"
assert "不得声称图片全链可用" in _p3["why"], \
    "★ 图片链仍 missing —— 视频档进生产不得顺带把图片说成可用"

# ★ P4 已真实判定且结果是 FAIL —— 不许因为它的 gate 命令退出 0 就显示成 ✓
#   2026-09-03: v2 多文本判定后 owner 授权自裁, 状态转为**决定**而非通过。
#   ★ 「决定了」不等于「过了」—— 状态名里必须留住这个区别。
p4 = [p for p in SPEC["phases"] if p["phase"] == "P4 九结 Research"][0]
assert p4["status"] == "DECIDED_KNOT_READOUT_TOP1_ONLY", p4["status"]
assert not p4["status"].startswith("DONE"), "★ K1 从未通过, 状态不许以 DONE 开头"
_legend = SPEC["status_legend"] if "status_legend" in SPEC else next(
    v for v in SPEC.values() if isinstance(v, dict) and "DONE_WITH_RECORDED_LOSS" in v)
assert "不是通过" in _legend[p4["status"]], "★ 状态词典必须写明这是决定不是通过"
# 裁定的实质: 结层白名单只剩 top1
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import KNOT_READOUT_ALLOWLIST  # noqa: E402
assert KNOT_READOUT_ALLOWLIST == {"top1"}, KNOT_READOUT_ALLOWLIST
mv = p4["measured_verdict"]
# 2026-09-02 判据修正后是五项: 2 项过 / 3 项不过
assert mv["verdict"] == "FAIL" and mv["criteria_count"] == 4
assert len(mv["passed"]) + len(mv["failed"]) == 4 and len(mv["failed"]) == 2
assert "三版判决都是 FAIL" in mv["criterion_fix"], "★ 改判据不得改判决, 这一点必须写明"
assert "两个真实质量问题 + 两条坏 gate" in mv["classification"]
assert os.path.exists(os.path.join(ROOT, mv["artifact"]))
real = json.load(open(os.path.join(ROOT, mv["artifact"]), encoding="utf-8"))
assert real["verdict"] == mv["verdict"], "★ 对照表里的判决与实际产物不一致"
assert "不是" in p4["why"] and "K1 过了" in p4["why"], \
    "★ 必须写明「gate 命令退 0 ≠ K1 过了」—— 这正是最容易被读错的地方"
for p in undone:
    assert p.get("why"), f"{p['phase']} 不是 DONE 却没写「还差什么」"
assert SPEC["phases"][3].get("not_built"), "P3 必须逐条列出未建的内容"

# 状态词必须都在语义表里, 不许现编
for p in SPEC["phases"]:
    assert p["status"] in SPEC["status_semantics"], f"未定义的状态词: {p['status']}"

# ── 反向 1: 声明的实现文件不存在 -> 红 ─────────────────────────────────
def with_spec(mutate, run_gates=False):
    """结构类反向测试默认不真跑 gate —— 跑它对这些断言没信息量,
    却让一次断言变成 72 次子进程测试(实测 109 秒)。"""
    with tempfile.TemporaryDirectory() as td:
        alt = os.path.join(td, "spec.json")
        s = json.loads(json.dumps(SPEC))
        mutate(s)
        json.dump(s, open(alt, "w"), ensure_ascii=False)
        saved, cc.MAP = cc.MAP, alt
        try:
            return cc.check(run_gates=run_gates)
        finally:
            cc.MAP = saved

ok2, errs2, _ = with_spec(lambda s: s["chain_stages"][0]["implemented_in"].append("scripts/nope.py"))
assert not ok2 and any("缺文件" in e for e in errs2), "★ 反向失败: 实现文件不存在却绿"

# ── 反向 2: 某段没有测试 -> 红 ─────────────────────────────────────────
ok3, errs3, _ = with_spec(lambda s: s["chain_stages"][6].__setitem__("tested_by", []))
assert not ok3 and any("没有测试" in e for e in errs3), "★ 反向失败: 链路某段零测试却绿"

# ── 反向 3: 标 DONE 却没有可跑的 gate -> 红 ────────────────────────────
ok4, errs4, _ = with_spec(lambda s: s["phases"][0].pop("gate_command"))
assert not ok4 and any("没有可跑的 gate" in e for e in errs4), \
    "★ 反向失败: 标 DONE 而没有 gate 却绿 —— 那就是「感觉差不多了」"

# ── 反向 4: gate 命令本身红 -> 整表红 ──────────────────────────────────
ok5, errs5, st5 = with_spec(lambda s: s["phases"][0].__setitem__("gate_command", "exit 3"),
                            run_gates=True)  # 这一条必须真跑
assert not ok5 and st5["phases"]["P0 地基"] == "FAIL", "★ 反向失败: gate 红了整表却绿"

# ── 反向 5: 不是 DONE 却不写「还差什么」-> 红 ──────────────────────────
# ★ 动态找第一个非 DONE 的, 不写死下标 —— 原来写死 phases[3](P3),
#   P3 一进生产这条反向就失效了(它变成 DONE, 摘 why 不再触发规则)。
#   **反向用例指着一个会变的下标, 它就会随被测对象一起失效。**
_undone_i = next(i for i, ph in enumerate(SPEC["phases"])
                 if not ph["status"].startswith("DONE"))
ok6, errs6, _ = with_spec(lambda s: s["phases"][_undone_i].pop("why"))
assert not ok6 and any("没写 why" in e for e in errs6), \
    "★ 反向失败: 半成品状态可以不交代还差什么"

# ── 反向 6: 标 NOT_STARTED 却带 gate 命令 -> 红(二选一, 不许两头占) ────
def _both(s):
    s["phases"][2]["status"] = "NOT_STARTED"
ok7, errs7, _ = with_spec(_both)
assert not ok7 and any("二选一" in e for e in errs7), \
    "★ 反向失败: 既标未开始又挂着一条会绿的 gate"

# ── 反向 7: 真删一个实现文件 -> 红 (不是只改 spec) ─────────────────────
victim = os.path.join(ROOT, "scripts", "cce_mechanism.py")
bak = victim + ".conformance_bak"
shutil.move(victim, bak)
try:
    ok8, errs8, _ = cc.check(run_gates=False)
    assert not ok8 and any("cce_mechanism.py" in e for e in errs8), \
        "★ 反向失败: 真的删掉一个实现文件, 对照表却还是绿的"
finally:
    shutil.move(bak, victim)
assert cc.check(run_gates=False)[0], "还原后必须恢复绿"

print(f"test_cce_chain_conformance: OK "
      f"(链路 15/15 实现且有测试 | Phase gate 8/8 过, 但内容已建只有 {stats['phases_done']}/8 —— "
      "P3/P4 用 ◐ 与 ✓ 区分 | 7 条反向各自见红)")
