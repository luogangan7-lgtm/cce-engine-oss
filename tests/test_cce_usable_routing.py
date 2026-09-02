#!/usr/bin/env python3
"""usable 读数必须由 K1 判定驱动 —— 不是靠一句散文 caveat。

## 起因(2026-09-02 发现的系统内部自相矛盾)
出站闸按 K1 判定**硬拦** [[knot_intensity:]] 的引用;
而 cce_full_run.usable_readouts 把同一份 intensity **无条件**放进 usable ——
usable 的定义是「允许进入下游/Population Field」「只有 usable 里的东西允许被引用」。
它靠的是一句「必须带 n 与不确定性一起引用」。

本项目已确立: **散文式 caveat 在这个项目已被证伪**
(13 条 Notion 读数都标了「不可单独使用」, 照样被当读数引用)。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_full_run as fr  # noqa: E402
import cce_k1_status as ks  # noqa: E402

K1V = json.load(open(os.path.join(ROOT, "tests", "data", "phase2",
                                  "k1_reliability_verdict.json"), encoding="utf-8"))


def run(manifest_s2, inst="565470cf26c16d01"):
    fr.MANIFEST.clear()
    fr.MANIFEST.update({"s1_readout": {"tops": {"desire": "a", "need": "b",
                                                "emotion": "c", "action": "d"}},
                        "s2_knots": manifest_s2})
    fr.qualified({"cce": {"stage2": {"instrument": {"instrument_hash": inst, "spec": {}}}}})
    return fr.MANIFEST["qualified_readout"]


S2 = {"knots": [["reward", 0.5], ["audit", 0.5]], "intensity": {"reward": 0.8},
      "n": 5, "top1_mode_share": 1.0, "top1_mode": "reward", "max_range": 0.39,
      "playbook_primary": "pb", "instrument": {"instrument_hash": "h"}}

# ── 1. 当前 K1 判定下: intensity 扣发, top1 保留 ───────────────────────
out = run(dict(S2))
assert "s2.distribution.top1" in out["usable_keys"]
assert not any("intensity" in k for k in out["usable_keys"]), \
    "★ K1 的强度层判据不达标, intensity 不得出现在 usable 里"
for k in ("s2.distribution.intensity", "s2.distribution.knot_weight",
          "s2.families", "s2.drive_brake"):
    assert k in out["withheld"], f"★ {k} 建在 intensity 上, 必须一起扣发"
assert "K1" in out["withheld"]["s2.distribution.intensity"], \
    "★ 扣发理由必须指向 K1 判定, 不能是一句泛泛的话"

# ── 2. ★ 单一真相源: 出站闸与 usable 路由读同一个判定文件 ──────────────
import cce_strategy_gate as sg  # noqa: E402
assert os.path.abspath(sg.K1_VERDICT) == os.path.abspath(ks.K1_VERDICT), \
    "★ 两个消费者必须读同一份判定 —— 两份 reader 会悄悄漂移"

# ── 3. 缺判定 != 判定通过 ──────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    absent = os.path.join(td, "nope.json")
    st = ks.layer_status(absent, instrument_hash=K1V["instrument_hash"])
    assert not st["intensity"]["usable"] and not st["top1"]["usable"]
    assert "缺判定不等于判定通过" in st["intensity"]["reason"]

# ── 4. 闸由判定驱动, 不是恒拦 ──────────────────────────────────────────
#    恒拦的闸和恒放的闸一样没有信息量 —— 伪造一个 PASS 判定验证它确实会放行。
with tempfile.TemporaryDirectory() as td:
    passing = os.path.join(td, "pass.json")
    v = json.loads(json.dumps(K1V))
    for c in v["checks"]:
        c["pass"] = True
    v["verdict"], v["failed"] = "PASS", []
    json.dump(v, open(passing, "w"), ensure_ascii=False)
    st = ks.layer_status(passing, instrument_hash=K1V["instrument_hash"])
    assert st["intensity"]["usable"] and st["top1"]["usable"], \
        "★ K1 全过时必须放行 —— 否则这个闸恒拦, 没有信息量"

# ── 5. 判据改名 -> 路由必须红, 不得静默放行 ────────────────────────────
with tempfile.TemporaryDirectory() as td:
    renamed = os.path.join(td, "renamed.json")
    v = json.loads(json.dumps(K1V))
    for c in v["checks"]:
        c["name"] = c["name"].replace("逐对容差一致", "某个新名字")
    json.dump(v, open(renamed, "w"), ensure_ascii=False)
    st = ks.layer_status(renamed, instrument_hash=K1V["instrument_hash"])
    assert not st["intensity"]["usable"] and "判据变了" in st["intensity"]["reason"], \
        "★ 判据改名后路由必须扣发并说明, 不得因为找不到那一项就静默放行"

# ── 6. 分层: top-1 与 intensity 必须能分别开关 ─────────────────────────
with tempfile.TemporaryDirectory() as td:
    t1bad = os.path.join(td, "t1.json")
    v = json.loads(json.dumps(K1V))
    for c in v["checks"]:
        c["pass"] = ("top-1" not in c["name"])
    json.dump(v, open(t1bad, "w"), ensure_ascii=False)
    st = ks.layer_status(t1bad, instrument_hash=K1V["instrument_hash"])
    assert st["intensity"]["usable"] and not st["top1"]["usable"], \
        "★ 两层必须独立 —— 一层不达标不该拖累另一层"

# ── 7. ★ 那句散文 caveat 必须已经不在了 ────────────────────────────────
src = open(os.path.join(ROOT, "scripts", "cce_full_run.py"), encoding="utf-8").read()
assert "分布类读数始终可用" not in src, \
    "★ 「始终可用」那句散文 caveat 必须删掉 —— 它正是被证伪的那种做法"
assert "layer_status(instrument_hash=" in src, \
    "★ usable 路由必须真的调用 K1 判定, **且把本次运行的仪器传进去**"

# ── 7b. ★ 标定不可跨仪器搬 —— 缺仪器标识 != 仪器相同 ───────────────────
#    K1 判定是在**某一台**仪器上做的。gen2→gen3 已确立: prompt 变了标定不可搬。
#    路由若不比对仪器, 就会拿 gen4 的判定去管一个 gen5 的 run。
GEN4 = K1V["instrument_hash"]
assert GEN4 == "565470cf26c16d01"
assert ks.layer_status(instrument_hash=GEN4)["top1"]["usable"], "同仪器时 top1 应放行"

st_other = ks.layer_status(instrument_hash="eb487df50f5aec31")   # gen5
assert not st_other["top1"]["usable"] and not st_other["intensity"]["usable"], \
    "★ 反向失败: 拿 gen4 的 K1 判定去管 gen5 的 run 却放行了 —— 标定不可跨仪器搬"
assert "不可跨仪器搬" in st_other["top1"]["reason"]

st_missing = ks.layer_status(instrument_hash=None)
assert not st_missing["top1"]["usable"] and not st_missing["intensity"]["usable"], \
    "★ 反向失败: 没给仪器标识就放行 —— **缺仪器标识不等于仪器相同**"
assert "缺仪器标识不等于仪器相同" in st_missing["top1"]["reason"]

# 端到端: qualified 段必须把**本次运行**的仪器传进路由, 不是省略
o4 = run(dict(S2), inst=GEN4)
o5 = run(dict(S2), inst="eb487df50f5aec31")
assert "s2.distribution.top1" in o4["usable_keys"]
assert "s2.distribution.top1" not in o5["usable_keys"], \
    "★ 反向失败: qualified 段没把本次运行的仪器传给路由"
assert len(o5["withheld"]) > len(o4["withheld"])

# ── 8. 派生量的实测必须落成仓内产物, 且标明 exploratory ────────────────
#    文档与提交信息引用了它的数字, 数字必须能回查到源头。
DL = json.load(open(os.path.join(ROOT, "tests", "data", "phase2",
                                 "derived_layer_reliability.json"), encoding="utf-8"))
assert DL["new_calls"] == 0 and DL["n_draw"] == 5 and DL["n_rep"] == 10
q = DL["per_quantity"]
w = [v for k, v in q.items() if k.startswith("weight.")]
i = [v for k, v in q.items() if k.startswith("intensity.")]
mm = [v for k, v in q.items() if k.startswith("mass.")]
assert min(w) > min(i), \
    f"★ 核心发现: weight 比 intensity 更稳(归一化抵消共模噪声), 实测 {min(w)} vs {min(i)}"
assert max(mm) <= min(i), \
    f"★ mass 取 max 应当更抖, 实测 mass 上界 {max(mm)} vs intensity 下界 {min(i)}"
assert sum(1 for v in w if v >= DL["agreement_min"]) == 3 and len(w) == 4
assert DL["quadrant"]["degenerate"] is True and len(DL["quadrant"]["values"]) == 1, \
    "★ quadrant 的 1.000 是零方差退化, 必须标出来 —— 否则会被当成「它很可靠」"
assert "不是信度证据" in DL["quadrant"]["★note"]
assert "exploratory" in DL["★status"] and "1 个文本" in DL["★status"]
assert "不按这里的数放行" in DL["★status"], \
    "★ 必须写明生产路由不采信这批 exploratory 数, 否则下一个人会拿它去放行 weight"
assert "推翻了" in DL["★finding"]

print(f"test_cce_usable_routing: OK "
      f"(intensity 及其派生量 4 项全部扣发 · top1 层保留 | "
      f"出站闸与 usable 路由同一真相源 | 缺判定不放行 · 伪造 PASS 会放行(非恒拦) | "
      f"判据改名必红 · 两层可独立开关 | 散文 caveat 已删 | "
      f"派生量实测已落盘(weight 比 intensity 稳 · mass 更差 · quadrant 退化) | "
      f"跨仪器/缺仪器标识 各自扣发)")
