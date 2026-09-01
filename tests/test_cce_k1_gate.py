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

# ── 判据阈值与 §23 逐字一致 ───────────────────────────────────────────
assert CRIT == {"n_min": 8, "identical_pairs_min": 6, "range_max": 0.10, "top1_agree_min": 7}

print("test_cce_k1_gate: OK "
      "(§23 指定的反向测试已补 | 不同内容按同组 -> 拒判 | 缺指纹 != 指纹相同 | "
      "四项逐条可观察到失败 | 三过一不过仍判 FAIL)")
