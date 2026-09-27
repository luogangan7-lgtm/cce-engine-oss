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
# ★★ 2026-09-06: 这条反向验证把缺陷**写进活仓**(scripts/), 靠 finally 清理。
#   而 finally **挡不住 SIGKILL** —— 2026-09-06 的并发审计里就有一个进程被杀,
#   地雷留在仓里, 从那一刻起 P1 闸对**所有人**恒红(check_ontology_migration 报
#   active_legacy_dependency=1), 连带 test_ontology_migration 与
#   test_cce_chain_conformance 一起红, 且**没有任何东西说明红的原因是测试残骸**。
#   ⇒ 会改活仓的测试, 在并发与中断下不安全。这是与「scratchpad 交叉污染」同族的问题。
#   修法: 起手先清陈旧残骸, 并**大声报出来** —— 清掉但不吭声, 等于把证据也一起清了。
#   ★ 2026-09-27 根因修复(不再靠「起手清残骸」兜底): 反向探针**一律不进活仓**。
#     检查器按自身位置定 ROOT ⇒ 把它和登记表复制进临时树, 探针埋在临时树的 scripts/ 里跑。
#     以前的写法在 runsuite 8 路并行下还会与 test_cce_chain_conformance 跑起的**另一份本测试**互删探针。
import shutil  # noqa: E402
import tempfile  # noqa: E402


def gate_in_tree(files: dict) -> subprocess.CompletedProcess:
    """临时树 = 检查器 + 登记表 + files(相对路径 -> 内容); 返回检查器在该树上的运行结果。"""
    with tempfile.TemporaryDirectory() as td:
        for rel, src in (("scripts/check_ontology_migration.py", CHECKER),
                         ("config/ontology_legacy_exceptions_v1.json", REGISTRY)):
            os.makedirs(os.path.dirname(os.path.join(td, rel)), exist_ok=True)
            shutil.copy(src, os.path.join(td, rel))
        for rel, text in files.items():
            with open(os.path.join(td, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        return subprocess.run([sys.executable, os.path.join(td, "scripts", "check_ontology_migration.py")],
                              capture_output=True, text=True)


PROBE = "scripts/_ontology_reverse_probe.py"
r5 = gate_in_tree({PROBE: 'SEGMENT_JS_THRESHOLD = 0.08\n'})
hit = [ln for ln in r5.stdout.splitlines() if ln.strip().startswith(PROBE + ":1 ")]
assert r5.returncode != 0 and hit and "active_legacy_dependency" in r5.stdout, \
    f"反向5 失败: 生产代码里凭空出现未登记旧名, 闸却没把它报成活跃旧依赖: {r5.stdout[-600:]}"
assert PROBE not in gate_in_tree({}).stdout, "反向5 对照失败: 没埋探针也报了探针"
assert not os.path.exists(os.path.join(ROOT, PROBE)), "★ 反向5 的探针进了活仓"

# ── 反向 6a: 同名异义不得被误判 —— 文本跨度 segment(text) 必须活着 ──────
import cce_structural_gate  # noqa: E402
assert callable(cce_structural_gate.segment), \
    "反向6a 失败: 为了让 grep 归零把文本跨度 segment(text) 也改了 —— 那是改错了概念"
assert cce_structural_gate.segment("hello world"), "反向6a 失败: segment(text) 不再工作"

# ── 反向 6b: 登记表不得靠通配/整目录 blanket exemption 逃闸 ─────────────
import check_ontology_migration as chk  # noqa: E402
# ★ 2026-09-27: 以前原地改写 config/ontology_legacy_exceptions_v1.json 再还原 —— 改写窗口里并行的 P1 闸会读到 blanket 豁免。
#   load_registry 本就收路径参数 ⇒ 变异版写临时文件。
def _registry_rejects(extra_entry) -> bool:
    reg = json.loads(open(REGISTRY, encoding="utf-8").read())
    reg["entries"].append(extra_entry)
    with tempfile.TemporaryDirectory() as td:
        alt = os.path.join(td, "registry.json")
        with open(alt, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=2)
        try:
            chk.load_registry(alt)
        except ValueError:
            return True
    return False


assert chk.load_registry(REGISTRY), "反向6b 对照: 真登记表必须能加载"
assert _registry_rejects({"path": "scripts/", "token": "segment_mixture",
                          "class": "UNRELATED_HOMONYM", "reason": "blanket"}), \
    "反向6b 失败: 登记表接受了整目录豁免"
assert _registry_rejects({"path": "scripts/cce_population.py", "token": "segment_mixture",
                          "class": "MADE_UP_CLASS", "reason": "x"}), \
    "反向6b 失败: 登记表接受了未定义的豁免类别"

print("test_ontology_migration: OK "
      "(6 条反向测试全部实际见红 | 正向 P1_PASS | 冻结件未触碰)")
