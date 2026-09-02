#!/usr/bin/env python3
"""K1 判据（2026-09-02 冻结的四项）的反向测试。

§23 原话:「反向测试(这道闸必须能观察到失败): 把两份**内容不同**的稿子按同组提交,
若闸判「稳定」则闸本身失效。**不做这一步的 K1 等同于没有 K1。**」

四项各抓一种可观测症状, 互不重叠:
  ① n >= 8                        证据量
  ② 出现率一致 >= 7/8              结是否存在的稳定性
  ③ A(0.10) >= 0.95 (稳定出现的结) 出现之后的数值可复现性
  ④ top-1 一致 >= 7/8              排名身份的可复现性
"""
import itertools
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from k1_gate import CRIT, judge  # noqa: E402

SHA, OTHER = "a" * 64, "b" * 64


def rows(knot_sets, sha=SHA):
    return [{"cid": f"c{i}", "sha": sha if isinstance(sha, str) else sha[i],
             "knots": ks, "intensity": {}, "top1": ks[0][0]}
            for i, ks in enumerate(knot_sets)]


STABLE = [["reward", 0.90], ["audit", 0.10]]

# ── 正向: 8 次完全相同 -> 四项全过 ────────────────────────────────────
code, rep = judge(rows([STABLE] * 8))
assert code == 0 and rep["verdict"] == "PASS" and rep["failed"] == []
assert len(rep["checks"]) == 4, "2026-09-02 冻结为四项"
assert rep["agreement"] == {"reward": 1.0, "audit": 1.0}
assert rep["reads"] == "post_gate_final_rep_output", \
    "★ 必须读闸后最终输出 —— D_var 正是因「闸前算、闸后判」被否决"

# ── 反向 1(§23 指定): 两份内容不同按同组提交 -> 不许判「稳定」 ─────────
DIFFERENT = [["inertia", 0.85], ["belong", 0.15]]
code, rep = judge(rows([STABLE, DIFFERENT] * 4, sha=[SHA, OTHER] * 4))
assert code == 2 and "不是同项重跑" in rep["reason"]

# ── 反向 2: 指纹缺失 != 指纹相同 ───────────────────────────────────────
blind = rows([STABLE, DIFFERENT] * 4)
for r in blind:
    r["sha"] = None
assert judge(blind)[0] == 2 and "缺 text_sha256" in judge(blind)[1]["reason"]
half = rows([STABLE] * 8)
half[3]["sha"] = None
assert judge(half)[0] == 2, "只要有一份缺指纹就该拒判"
assert judge(rows([STABLE] * 7))[0] == 2, "n=7 不可判"
# ★ n 这一项在 checks 里**结构上永远为 True**(不可判在 judge 开头就 return 2 了)。
#   它是展示项不是闸。真正的拦截由 early-return 承担 —— 下面钉住的是那个 early-return。
_n_check = [c for c in judge(rows([STABLE] * 8))[1]["checks"] if c[0].startswith("n >= 8")][0]
assert "展示项" in _n_check[0], "★ 永远为真的项必须在名字里标明, 不许冒充判据"
for _bad in (5, 6, 7):
    assert judge(rows([STABLE] * _bad))[0] == 2, f"n={_bad} 必须由 early-return 拒判"

# ── 反向 3: 容差一致率 —— 逐条可观察到失败 ─────────────────────────────
# 每个 rep 都点火, 但数值分散超出 δ=0.10
spread = rows([[["reward", 0.90], ["audit", 0.10]],
               [["reward", 0.50], ["audit", 0.10]]] * 4)
code, rep = judge(spread)
assert code == 1 and any("容差一致" in f for f in rep["failed"])
assert rep["agreement"]["reward"] < CRIT["agreement_min"]
assert rep["agreement"]["audit"] == 1.0, "audit 恒定, 不该被牵连"

# 恰好卡在 δ 边界上: 差 0.10 算「在容差内」
edge = rows([[["reward", 0.50]], [["reward", 0.60]]] * 4)
assert judge(edge)[1]["agreement"]["reward"] == 1.0, "|差| == δ 必须算通过"
over = rows([[["reward", 0.50]], [["reward", 0.61]]] * 4)
assert judge(over)[1]["agreement"]["reward"] < 1.0, "|差| > δ 必须算不通过"

# ── 反向 4: 出现率翻转 —— 强度恒定、top-1 不变时仍必须被抓住 ───────────
#    这是上一版只拆不补时漏掉的洞, 构造验证过。
flip = rows([[["audit", 0.90], ["reward", 0.50]], [["audit", 0.90]]] * 4)
code, rep = judge(flip)
assert code == 1 and any("出现率" in f for f in rep["failed"]), \
    "★ 出现率 4/4 翻转必须被抓住"
assert rep["knot_status"]["reward"] == "NOT_EVALUATED_PRESENCE_UNSTABLE"
assert "reward" not in rep["agreement"], \
    "★ 出现率不稳时不得评估强度 —— 更绝不填 0.0"

# ── 反向 5: 稳定缺席 != 稳定 ───────────────────────────────────────────
rare = rows([[["audit", 0.9], ["reward", 0.5]]] + [[["audit", 0.9]]] * 7)
code, rep = judge(rare)
assert rep["knot_status"]["reward"] == "NOT_APPLICABLE_STABLY_ABSENT"
assert "reward" not in rep["agreement"]
assert not any("出现率" in f for f in rep["failed"]), "1/8 出现 = 7/8 一致, 出现率这项应过"
assert "reward" in rep["stably_absent_knots"]

# ── 反向 6: top-1 不稳 ─────────────────────────────────────────────────
code, rep = judge(rows([STABLE, [["audit", 0.60], ["reward", 0.55]]] * 4))
assert code == 1 and any("top-1" in f for f in rep["failed"])

# ── 反向 7: 四项必须**全过**才算通过 ───────────────────────────────────
three_ok = rows([[["reward", 0.90], ["audit", 0.10]]] * 7 + [[["reward", 0.60], ["audit", 0.10]]])
code, rep = judge(three_ok)
assert code == 1, f"★ 三项过一项不过却判通过: {rep}"

# ── 反向 8: 出现率一致率恰好 7/8 过, 6/8 红 ───────────────────────────
ok7 = rows([[["audit", 0.9], ["reward", 0.5]]] * 7 + [[["audit", 0.9]]])
assert not any("出现率" in f for f in judge(ok7)[1]["failed"])
bad6 = rows([[["audit", 0.9], ["reward", 0.5]]] * 6 + [[["audit", 0.9]]] * 2)
assert any("出现率" in f for f in judge(bad6)[1]["failed"])

# ── 反向 9: 新判据不得有「极差」那种毛病(严格度随 rep 数漂移) ──────────
#    极差 R_{m+1} >= R_m 是数学恒等性质 ⇒ 判据在惩罚「多测量」。
#    A(δ) 与 出现率一致率 都是**比例**量, 必须不随 rep 数单调变严。
# 8 个递增值, 总跨度 0.07 < δ=0.10 ⇒ A(δ) 在任何 rep 数下都是 100%,
# 而极差从 0.01 一路涨到 0.07。这样两条量的行为差异才看得见。
_base = [[["audit", 0.90], ["reward", round(0.50 + 0.01 * i, 2)]] for i in range(8)]
def _worst_A(sub):
    out = 1.0
    for k in {kk for r in sub for kk, _ in r["knots"]}:
        f = [dict(r["knots"])[k] for r in sub if k in dict(r["knots"])]
        if len(f) >= 2:
            pr = list(itertools.combinations(f, 2))
            out = min(out, sum(1 for a, b in pr
                               if abs(a - b) <= CRIT["tolerance_delta"]) / len(pr))
    return out
_t = [statistics.fmean(_worst_A(list(c)) for c in itertools.combinations(rows(_base), R))
      for R in (4, 6, 8)]
assert _t == [1.0, 1.0, 1.0], f"★ 全部两两差 <= δ 时 A 应恒为 1.0, 不随 rep 数变 {_t}"
# 对照: 极差在同一批上确实单调变严(证明这条检验有分辨力, 不是恒真)
def _rng(sub):
    out = 0.0
    for k in {kk for r in sub for kk, _ in r["knots"]}:
        f = [dict(r["knots"])[k] for r in sub if k in dict(r["knots"])]
        if len(f) >= 2:
            out = max(out, max(f) - min(f))
    return out
_r = [statistics.fmean(_rng(list(c)) for c in itertools.combinations(rows(_base), R))
      for R in (4, 6, 8)]
assert _r[0] < _r[1] < _r[2], \
    f"★ 极差应当随 rep 数单调变严 {_r} —— 若不成立, 上面那条检验就没有分辨力"

# ── 阈值来源必须可追溯, 且已删除的两条不得复活 ─────────────────────────
assert CRIT == {"n_min": 8, "tolerance_delta": 0.10, "agreement_min": 0.95,
                "top1_agree_min": 7, "occurrence_agree_min": 7}
assert "identical_pairs_min" not in CRIT and "range_max" not in CRIT, \
    "★ 这两条已被判为形态错误, 不得复活"
assert CRIT["occurrence_agree_min"] == CRIT["top1_agree_min"], \
    "出现率阈值是按对称性复用 top-1 的数, 不是新拍"

print(f"test_cce_k1_gate: OK "
      f"(四项判据 · §23 反向测试 · 缺指纹!=指纹相同 · 容差边界 |差|==δ 算过 · "
      f"出现率翻转被抓且强度不评估 · 稳定缺席!=稳定 · 四项全过才通过 · "
      f"A(δ) 不随 rep 数漂移而极差会 · 删掉的两条不得复活)")
