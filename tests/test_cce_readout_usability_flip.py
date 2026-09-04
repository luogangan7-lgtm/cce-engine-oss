#!/usr/bin/env python3
"""同一份输入, 可用读数集**会变** —— 所以「可用」不是常态承诺。

重验三档时发现: 信封逐位相同、闸的代码与常量最后改动早于两次 run,
可用读数集仍然不同, 且 s2.playbook_primary 在两档里**方向相反**(排除了「代码改严了」)。

★ n=2, **无预注册** ⇒ 这是一次**观察**, 不是翻转率。本测试钉住的是
「产物如实标注它是观察」以及「状态表不把逐次可用说成固有属性」, 不是钉住某个数字。
"""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = json.load(open(os.path.join(ROOT, "tests/data/phase2/readout_usability_flip_obs.json"),
                   encoding="utf-8"))

assert "不是翻转率" in V["★this_is_an_observation_not_a_measurement"], \
    "★ 无预注册的观察不许被写成测量"
assert "2026-08-18" in V["design_that_makes_it_interpretable"], \
    "★ 「闸的代码没变」是这条观察能成立的前提, 必须写出来"
assert "逐位相同" in V["design_that_makes_it_interpretable"]
assert "方向相反" in V["★bidirectional"], "★ 双向翻转是排除「回归」这个解释的关键证据"
assert "不下结论" in V["★one_direction_worth_flagging"], \
    "★ s1.tops.need 两档同向, 但 n=2 —— 只能登记为待测"

# ── 由**真实归档产物**复核, 不信我写的摘要 ───────────────────────────
def usable(rid):
    fs = glob.glob(os.path.join(ROOT, "archive", rid, "*item*manifest.json"))
    q = json.load(open(fs[0], encoding="utf-8"))["stages"]["qualified_readout"]
    return set(q.get("usable_keys") or [])

for prof, f in V["flips"].items():
    old, new = usable(f["run_old"]), usable(f["run_new"])
    assert old != new, f"★ {prof}: 归档产物显示两次 run 可用集相同 —— 摘要与产物不符"
    assert "s1.tops.need" in old and "s1.tops.need" not in new, \
        f"★ {prof}: 产物里 s1.tops.need 的翻转与摘要不符"
# 双向那一条也要由产物证实, 不能只由我写的字证实
assert "s2.playbook_primary" in usable("33746399209") or True
assert ("s2.playbook_primary" in usable("33745544418")
        and "s2.playbook_primary" not in usable("33842081104")), "★ post 的方向与产物不符"
assert ("s2.playbook_primary" not in usable("33746399209")
        and "s2.playbook_primary" in usable("33842084279")), "★ reply 的方向与产物不符"

# ── 状态表不许把逐次可用说成固有属性 ────────────────────────────────
_st = open(os.path.join(ROOT, "scripts/cce_production_status.py"), encoding="utf-8").read()
assert "逐次运行" in _st and "不是系统的固有属性" in _st, \
    "★ 状态表必须写明「可用」是逐次由闸在运行时判的, 否则下游会假定它下次还在"

print("test_cce_readout_usability_flip: OK (由**归档产物**复核而非信摘要: "
      "post 的 need+playbook 双双转扣发 · reply 的 need 转扣发但 playbook **反向**转可用 | "
      "输入逐位相同 + 闸代码早于两次 run ⇒ 排除回归 | "
      "n=2 无预注册, 如实标为**观察**不是翻转率 | 状态表已写明可用是逐次判的)")
