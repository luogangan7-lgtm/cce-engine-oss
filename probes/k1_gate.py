#!/usr/bin/env python3
"""K1 Reliability 闸（重构文档 §23）—— 同项重跑稳定性，四项判据。

为什么不放进 CI: 它要跑 n≥8 次完整链路(每次含 reader_baseline + s1 + s2 共约 16 次模型调用),
单次约 6 分钟、128 次调用。这是**研究闸**, 按需跑, 不是每 PR 跑。
CI 里跑的是它的离线孪生 tests/test_cce_knot_stability.py(聚合语义 + 变异测试)。

用法:
  python3 probes/k1_gate.py <artifacts_dir>     # 目录下含多个 cce-item-*/manifest.json
判据(2026-09-02 冻结的四项, 见下方「判据沿革」):
  ① n >= 8
  ② 出现率一致率 >= 7/8                      —— 每个结「都出现」或「都不出现」
  ③ 稳定出现的结: 逐对容差一致率 A(0.10) >= 0.95  —— 出现之后的数值可复现性
  ④ top-1 结一致率 >= 7/8                    —— 排名身份可复现性
四项各抓一种可观测症状, 互不重叠。

## 判据沿革（两次修正，都留档）

### 删除「完全相同的读数对 >= 6/28」—— 判据形态错误，不是仪器 FAIL
它测的不是 repeatability，而是**九维向量的 exact collision probability**
`P(V1=V2) = Σ_v P(V=v)^2`。这个量高度依赖：保留几位小数 · intensity 网格多细 ·
中位数会不会产生 0.325/0.335 这类新值 · 九维联合基数 · 有没有 rounding。
**把三位小数改成一位小数，它就可能从永久红变绿，而被测属性一个字没变。**
这就是形态错误的定义。

量级证据（实测 n=8，28 对）：相同坐标共 2x4+13x3+9x2+4x1 = 69 个，
单坐标 exact-match 率 69/252 = 27.38%；而要达到 6/28 = 21.43% 的全向量匹配率，
单维需约 (6/28)^(1/9) = **84.27%** —— 差 3.1 倍，不是调参能到的。
ISO 5725 对连续测量的 repeatability 定义是**结果的离散程度**，
且明确允许一个 test result 由一组 observations 算出（与「多 draw → 中位数」相容），
标准从不把逐字节完全相等当作 repeatability 的定义。

### 删除「单结强度极差 <= 0.10」—— 极差的严格度是观测数的函数
极差是极值序统计量，`R_{m+1} >= R_m` 是**数学恒等性质**：加一个观测，极差只增不减。
实测同一批数据抽子集（draw 数不变），rep 数 3→8 对应最大极差 0.288→0.390 单调上升
⇒ 同一台仪器，跑的 rep 越多越容易不达标，**判据在惩罚「多测量」**。
ASTM C670 对此有明确处理：若用 max−min 作验收量，其 critical multiplier **必须随
test-result 数改变**（2 个结果 2.8 → 3 个 3.3 → 4 个 3.6 → … → 8 个 4.3）。
固定一个 range cutoff 跨不同 rep 数使用，本来就不是正确的统计构造。

替换为 **逐对容差一致率**：A_j(δ) = #{a<b : |x_aj − x_bj| <= δ} / C(m_j, 2)。
δ=0.10 沿用既有容差；阈值 0.95 取自 ISO 5725/ASTM 的 repeatability limit 语义
（两个重复结果之差以约 95% 概率落在界内），**不用 r≈2.8·s_r 的正态近似** ——
因为「5 个 draw 的中位数」不能假定正态。二者都不是从本批数据拟合来的。

### ★ 只读闸后最终输出
A_j 必须读 rep 级最终 intensity，不是 draw_ledger、不是闸前数据。
这正是 D_var 被否决的那条（闸前算、闸后判）：若闸后确实逐字节相同，
output repeatability 就该 PASS；闸前内部波动属于另一个 robustness gate，不得冒充它。

### 2026-09-02 早些时候的修正「单结极差」的口径 —— 原实现把**缺席**编码成 intensity=0.0
  再与真实强度值一起算极差。后果: 一个结在 rep 之间「出现/不出现」翻转,
  会被记成一次巨大的**强度**变动, 而它其实是**出现率**问题。
  实测(K1 那批 8 rep): 报出来的最大极差 0.40 来自 reward —— 它 8 个 rep 里只出现 1 次。
  按点火 rep 重算后, 最大极差是 0.39 且来自 display(8/8 都出现) —— 数字几乎没变,
  **但病灶完全变了**。非单射的判据会误判病灶。
  处方来自 2026-08-18 已确立的 P1a 根因(support 闸二值化), 早于本轮数据, 不是拟合。
  ★ 第一版修法只拆不补, **把闸改弱了** —— 构造验证: 一个「出现率 4/4 翻转、
  强度恒定、top-1 不变」的仪器四项全过。原以为「完全相同的读数对」能兜住,
  实测那一例给 12/28 也过。所以必须把出现率接回来, 成为独立的第五项。
  阈值不新拍: 复用 §23 自己的 7/8, 与 top-1 一致率**同形同数** ——
  「同一个结的出现与否在 rep 间一致」与「同一份稿子的首结在 rep 间一致」是同一种要求。
  选定顺序: 先按对称性定 7/8, 再验证它抓得住构造出的反例, 最后才看真实数据。
退出码: 0 = 四项全过; 1 = 有不达标项; 2 = 输入不足(不可判, 既不判过也不判负)
"""
import json
import sys
import math
from itertools import combinations
from pathlib import Path

CRIT = {"n_min": 8,
        # ★ 2026-09-02 删除 identical_pairs_min 与 range_max, 理由见「判据沿革」。
        "tolerance_delta": 0.10,   # 沿用既有工程容差, 不是新拍
        "agreement_min": 0.95,     # ISO 5725 repeatability limit 的语义: 两次重复结果之差
                                   # 以约 95% 概率落在容差内。不是从本批数据拟合。
        "top1_agree_min": 7,
        # ★ 2026-09-02 新增第五项。不是新拍的数 —— 与 top1_agree_min 同形同数(7/8):
        #   「同一个结在 rep 之间的**出现与否**必须一致」与
        #   「同一份稿子在 rep 之间的**首结**必须一致」是同一种要求。
        #   加它的理由不是加严, 而是补洞: 单结极差改为只看点火 rep 之后,
        #   一个「出现率 4/4 翻转、强度恒定、top-1 不变」的仪器会**四项全过**(已构造验证)。
        #   原判据把出现率偷偷塞在强度极差里, 拆开就必须把它接回来。
        "occurrence_agree_min": 7}


def load(d: Path):
    out = []
    for f in sorted(d.rglob("manifest.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        s2 = (m.get("stages") or {}).get("s2_knots")
        if not s2:
            continue
        out.append({"cid": (m.get("submission") or {}).get("content_id"),
                    "sha": m.get("text_sha256"),
                    "knots": s2.get("knots"), "intensity": s2.get("intensity"),
                    "top1": (s2.get("knots") or [[None]])[0][0]})
    return out


def judge(rows):
    """四项判据的判定核心。抽出来是为了让 CI 能对它做反向测试 ——
    埋在 main() 里的判据等于没有测试。

    返回 (退出码, 报告 dict)。退出码 2 = 不可判(既不判过也不判负)。
    """
    if len(rows) < CRIT["n_min"]:
        return 2, {"reason": f"n={len(rows)} < {CRIT['n_min']}", "verdict": "UNJUDGEABLE"}
    # ★ 2026-09-01: 原来只查 len(set(sha)) == 1。8 份 manifest **全都缺** text_sha256 时
    #   集合是 {None}, 长度也是 1 —— 于是闸打印「输入指纹唯一 ✅」, 而它其实一个指纹都没看到。
    #   实测: 两组截然不同的读数按同组喂进去, 照样打这行绿。
    #   缺指纹 ≠ 指纹相同。没有指纹就是**不可判**, 不是可判且通过。
    missing = sum(1 for r in rows if not r.get("sha"))
    if missing:
        return 2, {"reason": f"{missing}/{len(rows)} 份缺 text_sha256 —— "
                             "无从证明这是同一项的重跑; 缺指纹不等于指纹相同",
                   "verdict": "UNJUDGEABLE"}
    shas = {r["sha"] for r in rows}
    if len(shas) != 1:
        return 2, {"reason": f"输入指纹不唯一({len(shas)} 种) —— 这不是同项重跑, 测量作废",
                   "verdict": "UNJUDGEABLE"}

    n = len(rows)
    keys = {k for r in rows for k, _ in (r["knots"] or [])}
    delta, amin = CRIT["tolerance_delta"], CRIT["agreement_min"]
    # 「稳定出现」= 出现率一致率达标且落在「出现」那一侧
    m_present = math.ceil(CRIT["occurrence_agree_min"] / 8 * n)

    occurrence, agreement, status = {}, {}, {}
    for k in sorted(keys):
        fired = [dict(r["knots"])[k] for r in rows if k in dict(r["knots"])]
        m = len(fired)
        agree = max(m, n - m)
        occurrence[k] = {"fired_reps": m, "n_reps": n, "flip": 0 < m < n,
                         "agree": agree, "agree_scaled": round(agree / n * CRIT["n_min"], 4)}
        if m >= m_present:
            pairs = list(combinations(fired, 2))
            ok = sum(1 for a, b in pairs if abs(a - b) <= delta)
            agreement[k] = round(ok / len(pairs), 4)
            status[k] = "EVALUATED"
        elif m <= n - m_present:
            status[k] = "NOT_APPLICABLE_STABLY_ABSENT"
        else:
            # ★ 出现率不稳时**不评估**强度, 更绝不填 0.0 —— 那正是上一版的病灶
            status[k] = "NOT_EVALUATED_PRESENCE_UNSTABLE"

    worst_occ_key = min(occurrence, key=lambda k: occurrence[k]["agree_scaled"]) if occurrence else None
    worst_occ = occurrence[worst_occ_key]["agree_scaled"] if worst_occ_key else 8.0
    worst_agr_key = min(agreement, key=agreement.get) if agreement else None
    worst_agr = agreement[worst_agr_key] if worst_agr_key else 1.0

    tops = [r["top1"] for r in rows]
    top1_agree = max(tops.count(t) for t in set(tops))
    top1_scaled = top1_agree / n * CRIT["n_min"]

    checks = [
        # ★ 这一项**结构上永远为 True** —— n < n_min 在上面就 early-return 2(不可判)了,
        #   走到这里 n 必然达标。它是**展示项不是闸**, 真正的拦截在 judge 开头。
        #   突变测试证实: 把它改成恒真, 没有任何测试变红。如实标注, 不假装它是判据。
        ("n >= 8 (由 early-return 保证, 展示项)", n >= CRIT["n_min"], f"{n}"),
        (f"出现率一致 >= {CRIT['occurrence_agree_min']}/8", worst_occ >= CRIT["occurrence_agree_min"],
         f"{occurrence[worst_occ_key]['agree']}/{n} (折算 {worst_occ:.1f}/8)  最差项 {worst_occ_key}"
         if worst_occ_key else "无结"),
        (f"逐对容差一致 A({delta}) >= {amin}", worst_agr >= amin,
         (f"{worst_agr:.1%}  最差项 {worst_agr_key}  ({len(agreement)}/{len(keys)} 个结可评估)"
          if worst_agr_key else f"无稳定出现的结可评估 ({len(keys)} 个结全部出现率不稳或稳定缺席)")),
        (f"top-1 一致 >= {CRIT['top1_agree_min']}/8", top1_scaled >= CRIT["top1_agree_min"],
         f"{top1_agree}/{n} (折算 {top1_scaled:.1f}/8)"),
    ]
    failed = [c[0] for c in checks if not c[1]]

    flips = sorted(k for k, o in occurrence.items() if o["flip"])
    return (0 if not failed else 1), {
        "verdict": "PASS" if not failed else "FAIL", "n": n, "checks": checks,
        "failed": failed, "agreement": agreement, "knot_status": status,
        "tolerance_delta": delta, "agreement_min": amin,
        "tops": tops, "sha": shas.pop(),
        # ★ 2026-09-02 更正过时注释: 出现率**是**独立判据(第 ② 项), 有阈值 7/8。
        #   旧注释写「不设阈值, 由完全相同读数对承担」—— 那条判据已删, 且当时那个理由
        #   本来就被构造反例证伪过(出现率 4/4 翻转时它给 12/28 也过)。
        "occurrence": occurrence,
        "occurrence_flipping_knots": flips,
        "occurrence_threshold": "UNCALIBRATED —— 未前登记, 不进 verdict",
        # 点火 <2 rep 的结: 强度信度**未被测量**, 不是「很稳」
        "stably_absent_knots": sorted(k for k, v in status.items()
                                      if v == "NOT_APPLICABLE_STABLY_ABSENT"),
        "presence_unstable_knots": sorted(k for k, v in status.items()
                                          if v == "NOT_EVALUATED_PRESENCE_UNSTABLE"),
        "reads": "post_gate_final_rep_output"}


def main() -> int:
    rows = load(Path(sys.argv[1]))
    code, rep = judge(rows)
    if code == 2:
        print(f"⚠️ 不可判: {rep['reason']}")
        return 2
    print(f"K1 Reliability · n={rep['n']} · 输入指纹唯一 {rep['sha']} ✅\n")
    for name, ok, val in rep["checks"]:
        print(f"  {'✅' if ok else '❌'} {name:<28} {val}")
    print(f"\n  逐结容差一致率 A({rep['tolerance_delta']}): "
          f"{ {k: f'{v:.0%}' for k, v in sorted(rep['agreement'].items(), key=lambda x: x[1])} }")
    if rep["stably_absent_knots"]:
        print(f"  稳定缺席(强度不适用): {rep['stably_absent_knots']}"
              f" —— 它们的信度**未被测量**, 不得说「九结体系整体通过」")
    if rep["presence_unstable_knots"]:
        print(f"  出现率不稳(强度未评估, 绝不填 0.0): {rep['presence_unstable_knots']}")
    if rep["occurrence_flipping_knots"]:
        flip = {k: "%d/%d" % (rep["occurrence"][k]["fired_reps"], rep["n"])
                for k in rep["occurrence_flipping_knots"]}
        print(f"  出现率在 rep 间翻转的结: {flip}  [{rep['occurrence_threshold']}]")
    print(f"  top-1 各次: {rep['tops']}")
    print(f"\n  → {'K1 通过' if not rep['failed'] else 'K1 未通过, 不达标项: ' + ', '.join(rep['failed'])}")
    return code


if __name__ == "__main__":
    sys.exit(main())
