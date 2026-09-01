#!/usr/bin/env python3
"""§44 P2 新增六字段。每条都有反向断言 —— 只测「字段存在」是假检查。"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cce_window_chain as wc  # noqa: E402
from cce_population import (  # noqa: E402
    build_population_subject, compare_population_projections, partition_projection,
)

CONTRACT = json.load(open(os.path.join(ROOT, "config", "cce_subject_window_contract_v1.json"),
                          encoding="utf-8"))


def pop(dists, **kw):
    return build_population_subject(
        [{"actor_ref": f"m{i}", "distribution": d} for i, d in enumerate(dists)],
        coverage_scope="test", **kw)


def validate(subject):
    errs = []
    wc._validate_population_subject(subject, sorted(subject["member_distributions"]), errs,
                                    "population", subject.get("time_window"),
                                    subject.get("evidence_refs", []))
    return errs


BIMODAL = [{"a": .9, "b": .1}, {"a": .88, "b": .12}, {"a": .1, "b": .9}, {"a": .12, "b": .88}]
P = pop(BIMODAL)
assert not validate(P), validate(P)

# ── 1. field_structure ────────────────────────────────────────────────
fs = P["field_structure"]
assert fs["mode_count"] == 2 and fs["shape"] == "multi_mode"
assert pop([{"a": .9, "b": .1}, {"a": .89, "b": .11}])["field_structure"]["shape"] == "single_mode"
# 模态数 0 时不许报「单模态」—— 那是把「没测出结构」说成「结构是一个」
solo = pop([{"a": .9, "b": .1}, {"a": .1, "b": .9}])
assert solo["field_structure"]["shape"] == "no_supported_mode", solo["field_structure"]
assert solo["field_structure"]["mode_count"] == 0

# ── 2. mode_coverage: 分母不许是目标人群 ──────────────────────────────
mc = P["mode_coverage"]
assert mc["denominator"] == "known_member_count"
assert mc["not_denominator"] == "target_population_size"
assert mc["covered_member_share"] == 1.0 and mc["uncovered_member_count"] == 0
part = pop(BIMODAL + [{"a": .5, "b": .5}])
assert part["mode_coverage"]["uncovered_member_count"] == 1
assert part["mode_coverage"]["covered_member_share"] == 0.8

# ── 3. mode_activation: 刚过线的模态必须被标出来 ──────────────────────
ma = P["mode_activation"]
assert len(ma["modes"]) == 2
assert sorted(ma["minimally_supported_mode_ids"]) == sorted(r["mode_id"] for r in P["mode_mixture"]), \
    "两个模态都只有 2 个成员支撑, 必须全部进 minimally_supported"
assert ma["warning"], "有刚过线的模态却没有 warning"
wide = pop([{"a": .9, "b": .1}, {"a": .89, "b": .11}, {"a": .91, "b": .09}])
assert wide["mode_activation"]["minimally_supported_mode_ids"] == []
assert wide["mode_activation"]["warning"] is None

# ── 4. 契约必填: 缺一个就必须红 ───────────────────────────────────────
for field in ("field_structure", "mode_coverage", "mode_activation"):
    broken = copy.deepcopy(P)
    broken.pop(field)
    assert validate(broken), f"★ 反向失败: 产物缺 {field} 却通过了契约校验"
for field, key, bad in (("field_structure", "shape", "bimodal"),
                        ("field_structure", "mode_count", 99),
                        ("mode_coverage", "denominator", "target_population_size"),
                        ("mode_coverage", "not_denominator", None)):
    broken = copy.deepcopy(P)
    broken[field][key] = bad
    assert validate(broken), f"★ 反向失败: {field}.{key}={bad!r} 却通过了契约校验"
broken = copy.deepcopy(P)
broken["mode_activation"]["modes"] = broken["mode_activation"]["modes"][:1]
assert validate(broken), "★ 反向失败: mode_activation 漏了一个模态却通过了校验"

# ── 5. window_transition ──────────────────────────────────────────────
LATER = [{"a": .9, "b": .1}, {"a": .88, "b": .12}, {"a": .86, "b": .14}, {"a": .11, "b": .89}]
ev = compare_population_projections("w1", P, "w2", pop(LATER))
assert ev["kind"] == "cce.population_evolution.v2"
wt = ev["window_transition"]
assert wt["from"] == "w1" and wt["to"] == "w2"
assert set(wt["event_counts"]) == {"continue", "split", "merge", "create", "disappear"}
assert sum(wt["event_counts"].values()) == len(ev["events"])
assert wt["inference_scope"] == "descriptive_not_causal"

# ── 6. field_drift: 换人时必须标 confounded ───────────────────────────
same_members = ev["field_drift"]
assert same_members["membership"]["changed"] is False
assert same_members["confounded"] is False
other = build_population_subject(
    [{"actor_ref": f"x{i}", "distribution": d} for i, d in enumerate(LATER)],
    coverage_scope="test")
drift = compare_population_projections("w1", P, "w2", other)["field_drift"]
assert drift["membership"]["shared_n"] == 0 and drift["membership"]["changed"] is True
assert drift["confounded"] is True, \
    "★ 反向失败: 两窗口成员完全不同, 结构差却没标 confounded —— 会被读成人群变化"
assert "不可分" in drift["warning"]

# ── 7. partition_projection: 没框就投不了 ─────────────────────────────
nf = partition_projection(P, "r/HearingAids")
assert nf["status"] == "NOT_PROJECTABLE_NO_FRAME"
assert nf["projected_mode_shares"] is None, \
    "★ 反向失败: 无抽样框却给出了投影结果 —— 观测占比换个名字不是投影"
assert nf["needed"] == ["cell_totals", "member_cells"]

frame = {"cell_totals": {"c1": 1000, "c2": 500},
         "member_cells": {"m0": "c1", "m1": "c1", "m2": "c2", "m3": "c2"}}
pj = partition_projection(P, "r/HearingAids", frame=frame)
assert pj["status"] == "PROJECTED"
shares = sorted(pj["projected_mode_shares"].values())
# c1 每人代表 500, c2 每人代表 250 ⇒ 1000 : 500 ⇒ 2/3 : 1/3, 与观测的 .5:.5 不同
assert abs(shares[0] - 1 / 3) < 1e-9 and abs(shares[1] - 2 / 3) < 1e-9, shares
assert shares != sorted(pj["observed_mode_weights"].values()), \
    "★ 反向失败: 投影结果与观测占比完全相同, 说明放大系数根本没起作用"
assert abs(sum(pj["projected_mode_shares"].values())
           + pj["projected_unassigned_share"] - 1.0) < 1e-9

assert partition_projection(P, "x", frame={"cell_totals": {"c1": 10},
                                           "member_cells": {"m0": "c1"}}
                            )["status"] == "NOT_PROJECTABLE_UNMAPPED_MEMBERS"
assert partition_projection(P, "x", frame={"cell_totals": {},
                                           "member_cells": {m: "c9" for m in "m0 m1 m2 m3".split()}}
                            )["status"] == "NOT_PROJECTABLE_UNKNOWN_CELL_TOTAL"

# ── 8. 契约里真的写了这六条(不是只有代码里有) ─────────────────────────
for field in ("field_structure", "mode_coverage", "mode_activation"):
    assert field in CONTRACT["population_subject"], f"契约的 population_subject 没声明 {field}"
for field in ("window_transition", "field_drift"):
    assert field in CONTRACT["population_evolution"], f"契约的 population_evolution 没声明 {field}"
assert "partition_projection" in CONTRACT
assert set(CONTRACT["partition_projection"]["statuses"]) == {
    "PROJECTED", "NOT_PROJECTABLE_NO_FRAME",
    "NOT_PROJECTABLE_UNMAPPED_MEMBERS", "NOT_PROJECTABLE_UNKNOWN_CELL_TOTAL"}

# ── 9. §44 要求保留的七项一个都不许丢 ─────────────────────────────────
for kept in ("member_distributions", "member_weights", "population_mixture",
             "heterogeneity", "composition", "unassigned_weight", "uncertainty"):
    assert kept in P, f"★ P2 重构丢了必须保留的 {kept}"
assert "component_quantiles" in P["population_mixture"]

# ── 10. §44.9 P2 指定的反向测试: 删掉 member distributions 必须红 ──────
#    不是「聚合还能不能算出来」, 而是「会不会静默退化成均值」——
#    退化成均值正是这套 Population 本体从一开始要防的事。
for mutant, label in ((lambda p: p.pop("member_distributions"), "删掉"),
                      (lambda p: p.__setitem__("member_distributions", {}), "清空")):
    broken = copy.deepcopy(P)
    mutant(broken)
    errs = []
    wc._validate_population_subject(broken, sorted(P["member_distributions"]), errs,
                                    "population", broken.get("time_window"),
                                    broken.get("evidence_refs", []))
    assert errs, f"★ §44.9 P2 反向 gate 失败: {label} member_distributions 后聚合没有红 —— 静默退化成均值"

print("test_cce_population_field: OK "
      "(六字段全部落地且契约必填 | 缺字段/错声明各自见红 | "
      "换人必标 confounded | 无抽样框拒绝投影 | 保留项 7/7 | "
      "删member_distributions 见红)")
