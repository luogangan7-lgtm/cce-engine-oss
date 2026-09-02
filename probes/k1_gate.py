#!/usr/bin/env python3
"""K1 Reliability 闸（重构文档 §23）—— 同项重跑稳定性，四项判据。

为什么不放进 CI: 它要跑 n≥8 次完整链路(每次含 reader_baseline + s1 + s2 共约 16 次模型调用),
单次约 6 分钟、128 次调用。这是**研究闸**, 按需跑, 不是每 PR 跑。
CI 里跑的是它的离线孪生 tests/test_cce_knot_stability.py(聚合语义 + 变异测试)。

用法:
  python3 probes/k1_gate.py <artifacts_dir>     # 目录下含多个 cce-item-*/manifest.json
判据(§23 K1):
  n ≥ 8 · 完全相同的读数对 ≥ 6/8 · 单结强度极差 ≤ 0.10 · top-1 结一致率 ≥ 7/8
  + 出现率一致率 ≥ 7/8 (2026-09-02 补, 见下)

★ 2026-09-02 修正「单结极差」的口径 —— 原实现把**缺席**编码成 intensity=0.0
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
from itertools import combinations
from pathlib import Path

CRIT = {"n_min": 8, "identical_pairs_min": 6, "range_max": 0.10, "top1_agree_min": 7,
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
    ser = [json.dumps(r["knots"], sort_keys=True) for r in rows]
    pairs = list(combinations(range(n), 2))
    identical = sum(1 for i, j in pairs if ser[i] == ser[j])
    # 归一到 /8 的口径(§23 表格按 8 次表述), 用比例换算避免 n≠8 时口径漂移
    ident_scaled = identical / len(pairs) * (CRIT["n_min"] * (CRIT["n_min"] - 1) / 2)

    keys = {k for r in rows for k, _ in (r["knots"] or [])}
    # ★ 只在该结**实际点火**的 rep 上算强度极差。缺席 != 强度为 0。
    #   点火 rep < 2 的结算不出极差 —— 那是「该结的强度信度**未被测量**」,
    #   不是「它很稳」。这两者混同正是此前把 0.40 记在 reward 头上的原因。
    ranges, occurrence, unmeasured = {}, {}, []
    for k in keys:
        fired = [dict(r["knots"])[k] for r in rows if k in dict(r["knots"])]
        occurrence[k] = {"fired_reps": len(fired), "n_reps": n,
                         "flip": 0 < len(fired) < n}
        if len(fired) >= 2:
            ranges[k] = round(max(fired) - min(fired), 4)
        else:
            unmeasured.append(k)
    max_range = max(ranges.values()) if ranges else 0.0

    tops = [r["top1"] for r in rows]
    top1_agree = max(tops.count(t) for t in set(tops))
    top1_scaled = top1_agree / n * CRIT["n_min"]

    checks = [
        ("n ≥ 8", n >= CRIT["n_min"], f"{n}"),
        (f"完全相同读数对 ≥ {CRIT['identical_pairs_min']}/28",
         identical >= CRIT["identical_pairs_min"] / 28 * len(pairs),
         f"{identical}/{len(pairs)} (折算 {ident_scaled:.1f}/28)"),
        (f"单结强度极差 ≤ {CRIT['range_max']}", max_range <= CRIT["range_max"],
         f"{max_range}  最大项 {max(ranges, key=ranges.get) if ranges else '-'}"
         f"  (仅点火 rep; {len(ranges)}/{len(keys)} 个结可测)"),
        (f"top-1 一致 ≥ {CRIT['top1_agree_min']}/8", top1_scaled >= CRIT["top1_agree_min"],
         f"{top1_agree}/{n} (折算 {top1_scaled:.1f}/8)"),
    ]
    failed = [c[0] for c in checks if not c[1]]
    # 出现率一致率: 该结在 n 个 rep 里「都出现」或「都不出现」的多数占比。
    # 恒出现 / 恒不出现 都是稳定; 一半一半最不稳定。
    for k, o in occurrence.items():
        agree = max(o["fired_reps"], n - o["fired_reps"])
        o["agree"] = agree
        o["agree_scaled"] = round(agree / n * CRIT["n_min"], 4)
    worst_occ = min(occurrence.values(), key=lambda o: o["agree_scaled"]) if occurrence else None
    worst_occ_key = (min(occurrence, key=lambda k: occurrence[k]["agree_scaled"])
                     if occurrence else None)
    checks.append(
        (f"出现率一致 ≥ {CRIT['occurrence_agree_min']}/8",
         (worst_occ["agree_scaled"] >= CRIT["occurrence_agree_min"]) if worst_occ else True,
         (f"{worst_occ['agree']}/{n} (折算 {worst_occ['agree_scaled']:.1f}/8)  最差项 {worst_occ_key}"
          if worst_occ else "无结")))
    failed = [c[0] for c in checks if not c[1]]

    flips = sorted(k for k, o in occurrence.items() if o["flip"])
    return (0 if not failed else 1), {
        "verdict": "PASS" if not failed else "FAIL", "n": n, "checks": checks,
        "failed": failed, "ranges": ranges, "tops": tops, "sha": shas.pop(),
        # 出现率单独报, **不设阈值** —— 阈值必须前登记。
        # 它不进 verdict: 出现率不稳定已由「完全相同的读数对」那一项承担。
        "occurrence": occurrence,
        "occurrence_flipping_knots": flips,
        "occurrence_threshold": "UNCALIBRATED —— 未前登记, 不进 verdict",
        # 点火 <2 rep 的结: 强度信度**未被测量**, 不是「很稳」
        "intensity_unmeasured_knots": sorted(unmeasured),
        "range_scope": "fired_reps_only"}


def main() -> int:
    rows = load(Path(sys.argv[1]))
    code, rep = judge(rows)
    if code == 2:
        print(f"⚠️ 不可判: {rep['reason']}")
        return 2
    print(f"K1 Reliability · n={rep['n']} · 输入指纹唯一 {rep['sha']} ✅\n")
    for name, ok, val in rep["checks"]:
        print(f"  {'✅' if ok else '❌'} {name:<28} {val}")
    print(f"\n  逐结强度极差(仅点火 rep): {dict(sorted(rep['ranges'].items(), key=lambda x: -x[1]))}")
    if rep["intensity_unmeasured_knots"]:
        print(f"  ⚠️ 强度信度未被测量(点火 <2 rep): {rep['intensity_unmeasured_knots']}"
              f" —— 不得说「九结体系整体通过」")
    if rep["occurrence_flipping_knots"]:
        flip = {k: "%d/%d" % (rep["occurrence"][k]["fired_reps"], rep["n"])
                for k in rep["occurrence_flipping_knots"]}
        print(f"  出现率在 rep 间翻转的结: {flip}  [{rep['occurrence_threshold']}]")
    print(f"  top-1 各次: {rep['tops']}")
    print(f"\n  → {'K1 通过' if not rep['failed'] else 'K1 未通过, 不达标项: ' + ', '.join(rep['failed'])}")
    return code


if __name__ == "__main__":
    sys.exit(main())
