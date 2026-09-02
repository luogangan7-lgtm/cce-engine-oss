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


def run(manifest_s2):
    fr.MANIFEST.clear()
    fr.MANIFEST.update({"s1_readout": {"tops": {"desire": "a", "need": "b",
                                                "emotion": "c", "action": "d"}},
                        "s2_knots": manifest_s2})
    fr.qualified({"cce": {"stage2": {"instrument": {"instrument_hash": "h", "spec": {}}}}})
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
    st = ks.layer_status(absent)
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
    st = ks.layer_status(passing)
    assert st["intensity"]["usable"] and st["top1"]["usable"], \
        "★ K1 全过时必须放行 —— 否则这个闸恒拦, 没有信息量"

# ── 5. 判据改名 -> 路由必须红, 不得静默放行 ────────────────────────────
with tempfile.TemporaryDirectory() as td:
    renamed = os.path.join(td, "renamed.json")
    v = json.loads(json.dumps(K1V))
    for c in v["checks"]:
        c["name"] = c["name"].replace("逐对容差一致", "某个新名字")
    json.dump(v, open(renamed, "w"), ensure_ascii=False)
    st = ks.layer_status(renamed)
    assert not st["intensity"]["usable"] and "判据变了" in st["intensity"]["reason"], \
        "★ 判据改名后路由必须扣发并说明, 不得因为找不到那一项就静默放行"

# ── 6. 分层: top-1 与 intensity 必须能分别开关 ─────────────────────────
with tempfile.TemporaryDirectory() as td:
    t1bad = os.path.join(td, "t1.json")
    v = json.loads(json.dumps(K1V))
    for c in v["checks"]:
        c["pass"] = ("top-1" not in c["name"])
    json.dump(v, open(t1bad, "w"), ensure_ascii=False)
    st = ks.layer_status(t1bad)
    assert st["intensity"]["usable"] and not st["top1"]["usable"], \
        "★ 两层必须独立 —— 一层不达标不该拖累另一层"

# ── 7. ★ 那句散文 caveat 必须已经不在了 ────────────────────────────────
src = open(os.path.join(ROOT, "scripts", "cce_full_run.py"), encoding="utf-8").read()
assert "分布类读数始终可用" not in src, \
    "★ 「始终可用」那句散文 caveat 必须删掉 —— 它正是被证伪的那种做法"
assert "layer_status()" in src, "usable 路由必须真的调用 K1 判定"

print(f"test_cce_usable_routing: OK "
      f"(intensity 及其派生量 4 项全部扣发 · top1 层保留 | "
      f"出站闸与 usable 路由同一真相源 | 缺判定不放行 · 伪造 PASS 会放行(非恒拦) | "
      f"判据改名必红 · 两层可独立开关 | 散文 caveat 已删)")
