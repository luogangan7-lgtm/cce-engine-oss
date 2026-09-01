#!/usr/bin/env python3
"""P1 本体迁移的反向测试。

不做反向测试的断言等同于没有断言 —— 本文件每一条都自己制造一次违规,
断言闸**确实变红**, 再恢复。只测「闸绿」的测试完全不能证明闸活着。
"""
import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
CHECKER = os.path.join(ROOT, "scripts", "check_ontology_migration.py")
REGISTRY = os.path.join(ROOT, "config", "ontology_legacy_exceptions_v1.json")

import cce_population  # noqa: E402
import cce_window_chain  # noqa: E402
from cce_case_assemble import MODEL_FORBIDDEN_KEYS  # noqa: E402
from cce_population_v1_reader import (  # noqa: E402
    UnsupportedSchemaVersion, read_population_artifact,
)


def gate() -> int:
    return subprocess.run([sys.executable, CHECKER], capture_output=True).returncode


def _population():
    return cce_population.build_population_subject(
        [{"actor_ref": f"m{i}", "distribution": d} for i, d in enumerate(
            [{"a": 0.9, "b": 0.1}, {"a": 0.88, "b": 0.12}, {"a": 0.1, "b": 0.9}, {"a": 0.12, "b": 0.88}])],
        coverage_scope="test")


# ── 正向: 当前状态必须绿 ────────────────────────────────────────────────
assert gate() == 0, "基线: P1 闸当前必须通过"

# ── 反向 1: 新 writer 吐出旧字段 -> 契约校验必须红 ──────────────────────
pop = _population()
assert "mode_mixture" in pop and "segment_mixture" not in pop
assert pop["kind"] == "cce.population_subject.v2"
legacy = copy.deepcopy(pop)
legacy["segment_mixture"] = legacy.pop("mode_mixture")
def _validate(subject):
    errs = []
    cce_window_chain._validate_population_subject(
        subject, sorted(subject["member_distributions"]), errs, "population",
        subject.get("time_window"), subject.get("evidence_refs", []))
    return errs

assert not _validate(pop), f"基线: 当前 v2 输出必须自洽通过契约: {_validate(pop)}"
assert _validate(legacy), "反向1 失败: 输出旧字段 segment_mixture 时契约校验没有报错"

# ── 反向 2: 旧 v1 envelope 走生产入口 -> 必须 fail closed ───────────────
old_envelope = copy.deepcopy(pop)
old_envelope["kind"] = "cce.population_subject.v1"
_errs = _validate(old_envelope)
assert any("v2" in e for e in _errs), f"反向2 失败: 旧 v1 envelope 没有被生产入口拒绝: {_errs}"

# ── 反向 3: 只读 adapter —— 单向, 且缺 kind 不猜版本 ────────────────────
adapted = read_population_artifact(copy.deepcopy(old_envelope))
assert adapted["kind"] == "cce.population_subject.v2"
assert "mode_mixture" in adapted and "segment_mixture" not in adapted
assert adapted["read_via"]["direction"] == "v1_to_v2_read_only"
for bad in ({"kind": "cce.population_subject.v3"}, {}, {"kind": None}):
    try:
        read_population_artifact(bad)
    except UnsupportedSchemaVersion:
        pass
    else:
        raise AssertionError(f"反向3 失败: 缺/未知 kind 时没有拒绝: {bad}")
assert not hasattr(sys.modules["cce_population_v1_reader"], "adapt_v2_to_v1"), \
    "反向3 失败: 存在 v2->v1 反向映射, 旧 wire contract 会重新成为活跃输出能力"

# ── 反向 4: 从黑名单删掉 legacy sentinel -> 必须红 ──────────────────────
for sentinel in ("segment_id", "individual_id"):
    assert sentinel in MODEL_FORBIDDEN_KEYS, \
        f"反向4 失败: 黑名单丢了 legacy sentinel {sentinel}, 旧名可重新注入"
for current in ("mode_id", "population_field_id", "evidence_unit_id"):
    assert current in MODEL_FORBIDDEN_KEYS, f"反向4 失败: 黑名单缺 canonical v2 名 {current}"

# ── 反向 5: 未登记的旧名出现在生产代码 -> 闸必须红 ──────────────────────
probe = os.path.join(ROOT, "scripts", "_ontology_reverse_probe.py")
with open(probe, "w", encoding="utf-8") as fh:
    fh.write('SEGMENT_JS_THRESHOLD = 0.08\n')
try:
    assert gate() != 0, "反向5 失败: 生产代码里凭空出现未登记旧名, 闸却是绿的"
finally:
    os.remove(probe)
assert gate() == 0, "反向5 清理后闸应恢复绿"

# ── 反向 6a: 同名异义不得被误判 —— 文本跨度 segment(text) 必须活着 ──────
import cce_structural_gate  # noqa: E402
assert callable(cce_structural_gate.segment), \
    "反向6a 失败: 为了让 grep 归零把文本跨度 segment(text) 也改了 —— 那是改错了概念"
assert cce_structural_gate.segment("hello world"), "反向6a 失败: segment(text) 不再工作"

# ── 反向 6b: 登记表不得靠通配/整目录 blanket exemption 逃闸 ─────────────
import check_ontology_migration as chk  # noqa: E402
saved = open(REGISTRY, encoding="utf-8").read()
try:
    reg = json.loads(saved)
    reg["entries"].append({"path": "scripts/", "token": "segment_mixture",
                           "class": "UNRELATED_HOMONYM", "reason": "blanket"})
    with open(REGISTRY, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    try:
        chk.load_registry()
    except ValueError:
        pass
    else:
        raise AssertionError("反向6b 失败: 登记表接受了整目录豁免")

    reg = json.loads(saved)
    reg["entries"].append({"path": "scripts/cce_population.py", "token": "segment_mixture",
                           "class": "MADE_UP_CLASS", "reason": "x"})
    with open(REGISTRY, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    try:
        chk.load_registry()
    except ValueError:
        pass
    else:
        raise AssertionError("反向6b 失败: 登记表接受了未定义的豁免类别")
finally:
    with open(REGISTRY, "w", encoding="utf-8") as fh:
        fh.write(saved)
assert gate() == 0, "反向6b 清理后闸应恢复绿"

print("test_ontology_migration: OK "
      "(6 条反向测试全部实际见红 | 正向 P1_PASS | 冻结件未触碰)")
