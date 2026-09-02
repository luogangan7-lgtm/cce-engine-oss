#!/usr/bin/env python3
"""§23 / §44.9 P4 的 K1 闸反向测试。

§23 原话:「反向测试(这道闸必须能观察到失败): 把两份**内容不同**的稿子按同组提交,
若闸判「稳定」则闸本身失效 —— 它必须对真实差异报红。**不做这一步的 K1 等同于没有 K1。**」

这个文件就是那一步。0 次 API 调用 —— 判据是纯函数, 用构造读数直接喂。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from k1_gate import CRIT, judge  # noqa: E402

SHA = "a" * 64
OTHER = "b" * 64


def rows(knot_sets, sha=SHA):
    return [{"cid": f"c{i}", "sha": sha if isinstance(sha, str) else sha[i],
             "knots": ks, "intensity": {}, "top1": ks[0][0]}
            for i, ks in enumerate(knot_sets)]


STABLE = [["reward", 0.90], ["audit", 0.10]]

# ── 正向: 8 次完全相同 -> 四项全过 ────────────────────────────────────
code, rep = judge(rows([STABLE] * 8))
assert code == 0 and rep["verdict"] == "PASS", rep
assert rep["failed"] == []
assert len(rep["checks"]) == 5, "2026-09-02 起是五项判据"
assert all(o["agree"] == 8 for o in rep["occurrence"].values())

# ── 反向 1(§23 指定): 两份内容不同按同组提交 -> 不许判「稳定」 ─────────
DIFFERENT = [["inertia", 0.85], ["belonging", 0.15]]
mixed = [STABLE, DIFFERENT] * 4
code, rep = judge(rows(mixed, sha=[SHA, OTHER] * 4))
assert code == 2 and rep["verdict"] == "UNJUDGEABLE", \
    f"★ 反向失败: 两份不同稿子按同组提交, 闸没有拒判: {rep}"
assert "不是同项重跑" in rep["reason"]

# ── 反向 2: 指纹缺失不等于指纹相同 ────────────────────────────────────
#    实测过的真洞: 8 份 manifest 全缺 text_sha256 时 {None} 长度也是 1,
#    闸打印「输入指纹唯一 ✅」并照常判 —— 一个从没看过指纹的绿。
blind = rows(mixed)
for r in blind:
    r["sha"] = None
code, rep = judge(blind)
assert code == 2 and "缺 text_sha256" in rep["reason"], \
    f"★ 反向失败: 全部缺指纹时闸仍然可判 —— 缺指纹被当成了指纹相同: {rep}"
half = rows([STABLE] * 8)
half[3]["sha"] = None
assert judge(half)[0] == 2, "★ 反向失败: 只要有一份缺指纹就该拒判"

# ── 反向 3: 四项判据逐条可观察到失败 ──────────────────────────────────
# n 不够
assert judge(rows([STABLE] * 7))[0] == 2

# 单结极差超线: 同一 top1, 但权重摆动 0.37 (正是 §23 记录的历史基线)
drifty = [[["reward", 0.90], ["audit", 0.10]], [["reward", 0.53], ["audit", 0.47]]] * 4
code, rep = judge(rows(drifty))
assert code == 1 and any("极差" in f for f in rep["failed"]), rep
assert rep["ranges"]["reward"] > CRIT["range_max"]

# top-1 一致率不够: 8 次里 4 次换了首位
code, rep = judge(rows([STABLE, [["audit", 0.60], ["reward", 0.40]]] * 4))
assert code == 1 and any("top-1" in f for f in rep["failed"]), rep

# 完全相同读数对不够: 每次权重都微动, top1 不变、极差在线内
jitter = [[["reward", 0.90 + i * 0.005], ["audit", 0.10 - i * 0.005]] for i in range(8)]
code, rep = judge(rows(jitter))
assert code == 1 and any("完全相同读数对" in f for f in rep["failed"]), rep
assert rep["ranges"]["reward"] <= CRIT["range_max"], "构造有误: 这一例应只有「相同读数对」不达标"

# ── 反向 4: 四项必须**全过**才算通过, 不是多数过 ──────────────────────
assert judge(rows(drifty))[1]["verdict"] == "FAIL"
three_ok = [[["reward", 0.90], ["audit", 0.10]]] * 7 + [[["reward", 0.70], ["audit", 0.30]]]
code, rep = judge(rows(three_ok))
assert code == 1, f"★ 反向失败: 三项过一项不过却判通过: {rep}"

# ── 反向 5(2026-09-02 新增): 缺席不得被编码成 intensity=0.0 ────────────
#    这是原实现的真 bug: 一个结在 rep 之间「出现/不出现」翻转, 被记成一次巨大的
#    **强度**变动。判据因此非单射 —— 同时被出现率翻转和强度漂移触发, 会误判病灶。
STRONG = [["reward", 0.90], ["audit", 0.10]]
ABSENT = [["audit", 0.10]]                      # reward 整个不出现
flip = rows([STRONG, ABSENT] * 4)
code, rep = judge(flip)
assert rep["range_scope"] == "fired_reps_only"
# reward 点火 4 次且**每次都是 0.90** ⇒ 它的强度完全没有变动。
# 旧口径把 4 个缺席记成 0.0, 会报极差 0.90 —— 把「出现率翻转」说成「强度极不稳」。
_fired = [v for r in flip for k, v in r["knots"] if k == "reward"]
assert len(_fired) == 4 and max(_fired) == min(_fired) == 0.90
assert rep["ranges"]["reward"] == 0.0, \
    f"★ 反向失败: reward 每次点火都是 0.90, 强度极差必须是 0; 实测 {rep['ranges'].get('reward')} " \
    "—— 说明缺席仍被当成 0.0 算进了强度极差"
assert "reward" not in rep["intensity_unmeasured_knots"], "点火 4 次, 应可测"
assert {k: rep["occurrence"]["reward"][k] for k in ("fired_reps", "n_reps", "flip", "agree")} \
    == {"fired_reps": 4, "n_reps": 8, "flip": True, "agree": 4}
assert "reward" in rep["occurrence_flipping_knots"]
# ★ 但出现率不稳定没被放过 —— 它由「完全相同读数对」承担
# ★ 这里原本写的是「由『完全相同读数对』兜住」, **构造验证证伪了它**: 那一项给 12/28 也过。
#   只拆不补就是把闸改弱, 所以补了第五项。下面钉住的是修好之后的行为。
assert any("出现率一致" in f for f in rep["failed"]), \
    "★ 反向失败: 出现率 4/4 翻转却没有任何一项抓住 —— 拆掉重复计数之后必须把它接回来"
assert rep["occurrence"]["reward"]["agree"] == 4

# 反向 6: 点火 <2 rep 的结不得当成「很稳」──────────────────────────────
rare = rows([STRONG] + [ABSENT] * 7)
_, rep2 = judge(rare)
assert "reward" in rep2["intensity_unmeasured_knots"] and "reward" not in rep2["ranges"], \
    "★ 反向失败: 只点火 1 次的结算不出极差, 必须标「未被测量」而不是默认通过"
assert rep2["occurrence"]["reward"]["fired_reps"] == 1

# 反向 7: 每个 rep 都点火时, 新旧口径必须给出**同一个**极差 ────────────
#    否则修正就不只是「拆掉出现率」, 而是顺手改了别的东西。
same = rows([[["reward", 0.90], ["audit", 0.10]],
             [["reward", 0.50], ["audit", 0.10]]] * 4)
_, rep3 = judge(same)
assert rep3["ranges"]["reward"] == 0.40 and not rep3["occurrence"]["reward"]["flip"], \
    "★ 反向失败: 常火结的极差在修正前后应完全一致"

# ── 判据阈值与 §23 逐字一致 ───────────────────────────────────────────
assert CRIT == {"n_min": 8, "identical_pairs_min": 6, "range_max": 0.10,
                "top1_agree_min": 7, "occurrence_agree_min": 7}
# ★ 第五项的阈值必须与 top-1 那项**同数** —— 它是按对称性复用的, 不是新拍的
assert CRIT["occurrence_agree_min"] == CRIT["top1_agree_min"]

# 反向 8: 出现率一致率恰好卡在 7/8 必须过, 6/8 必须红 ──────────────────
ok7 = rows([[["audit", 0.9], ["reward", 0.5]]] * 7 + [[["audit", 0.9]]])
assert judge(ok7)[1]["occurrence"]["reward"]["agree"] == 7
assert not any("出现率" in f for f in judge(ok7)[1]["failed"]), "7/8 应当过"
bad6 = rows([[["audit", 0.9], ["reward", 0.5]]] * 6 + [[["audit", 0.9]]] * 2)
assert judge(bad6)[1]["occurrence"]["reward"]["agree"] == 6
assert any("出现率" in f for f in judge(bad6)[1]["failed"]), "6/8 应当红"

# 反向 9: 恒不出现的结算「一致」, 不算「不稳定」 ────────────────────────
never = rows([[["audit", 0.9]]] * 8)
r9 = judge(never)[1]
assert "reward" not in r9["occurrence"], "从未出现的结压根不进 occurrence"
assert not any("出现率" in f for f in r9["failed"])

print("test_cce_k1_gate: OK "
      "(§23 指定的反向测试已补 | 不同内容按同组 -> 拒判 | 缺指纹 != 指纹相同 | "
      "四项逐条可观察到失败 | 三过一不过仍判 FAIL | "
      "缺席不再编码成 0.0, 且出现率仍被「相同读数对」抓住)")
