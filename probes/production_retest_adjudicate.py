#!/usr/bin/env python3
"""完整流程重测的判决 —— 判据在看到读数之前写完。零 API。

★★★ 三条铁的:
① **没有事先定义允许的翻转率 ⇒ 不签发「信度合格」**。即使 22/22 不翻也只报事实。
② **不许把无合法读数的条目当作稳定**; 失败情况全部保留。
③ 同一模型名不足以排除运行条件变化 ⇒ 称「**两次实际运行之间的一致性**」, 不归因成纯采样噪声。
"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RAW = V / "production_retest" / "raw.json"
PRE = json.loads((ROOT / "tests/data/production_retest_reliability_prereg.json").read_text(encoding="utf-8"))


def main():
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    n_design = 22
    ok = [r for r in rows if r.get("top1_run2")]
    bad = [r for r in rows if not r.get("top1_run2")]
    same = sum(1 for r in ok if r["same"])
    q = same / len(ok) if ok else None

    # ★ 九类转移表(哪一类翻成了哪一类)
    trans = collections.Counter()
    for r in ok:
        if not r["same"]:
            trans[f"{r['top1_run1']} → {r['top1_run2']}"] += 1

    # ★ 零翻转时的精确上限(1 - 0.05**(1/n)); 有翻转时给 Clopper-Pearson 上限
    from math import comb
    def cp_upper(k, n, a=0.05):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            m = (lo + hi) / 2
            s = sum(comb(n, i) * m**i * (1 - m)**(n - i) for i in range(0, k + 1))
            if s > a: lo = m
            else: hi = m
        return (lo + hi) / 2
    flips = len(ok) - same
    upper = cp_upper(flips, len(ok)) if ok else None

    res = {
        "block": "PRODUCTION_RETEST_RELIABILITY_RESULT",
        "★prereg": "tests/data/production_retest_reliability_prereg.json",
        "★★口径": ("**两次实际运行之间的一致性** —— 同一模型名不足以排除运行条件变化, "
                   "**不归因成纯采样噪声**。且只跑 stage1+stage2 两段, **不是完整 CCE 链路**。"),
        "设计单元": n_design,
        "有两次合法完整读数的条目": len(ok),
        "★无合法读数(不计入 q, 也不当作稳定)": [{"id": r["id"], "cell": r["cell"],
                                                 "error": r.get("error")} for r in bad],
        "★★★主读数 q": {
            "值": round(q, 4) if q is not None else None,
            "算式": f"{same}/{len(ok)}",
            "翻转数": flips,
            "★翻转率的单侧95%精确上限": round(upper, 4) if upper is not None else None,
        },
        "★九类转移表": dict(trans) or "无翻转",
        "★数量硬断言": {"k 被静默降级的题": [r["id"] for r in rows
                                            if r.get("★k_assert") and r["★k_assert"] != "OK"]},
        "★★★不能签发的东西": (
            "**没有事先定义允许的翻转率 ⇒ 不签发「信度合格」。** "
            f"{'即使 22/22 不翻转, 也只报告这一事实, ' if flips == 0 else ''}"
            "**不报告「生产稳定性已建立」。**"),
        "★本轮定位": "**首条局部重测证据** —— 边界回归集上的重测, **不是**自然部署域的总体信度。",
        "★用已暴露题做重测的说明": (
            "本轮问的是「固定生产程序在这组固定文本上, 重复执行是否稳定」。"
            "题目已暴露**不使这个问题失去意义**; 它限制的是**外推范围**。"),
    }
    # ★ 采购 gate 的三档 —— 预注册里写死的, 各对应一个不同的下一步
    if q is None:
        res["★★★下一步(按预注册的三档)"] = "无有效读数, 扣发"
    elif q >= 0.9:
        res["★★★下一步(按预注册的三档)"] = (
            "**q 高(>=0.9)**: 「生产 1/8」这类单次读数可继续被引用为**局部**证据; "
            "闸材料候选实验值得排下一位。")
    elif q >= 0.7:
        res["★★★下一步(按预注册的三档)"] = (
            "**q 中(0.7~0.9)**: 单次读数须标注不稳定度; "
            "**任何基于单次生产读数的比较都要带这个数**。")
    else:
        res["★★★下一步(按预注册的三档)"] = (
            "**q 低(<0.7)**: **前面所有生产单次读数的比较全部降级**; "
            "闸材料候选实验**应推后** —— 先解决生产自己的稳定性。")
    res["★my_bet"] = {"赌的是": "q >= 0.80", "信心": "低(没有任何先验数据 —— 这正是买它的原因)",
                      "★结果": ("**赌对**" if q is not None and q >= 0.80
                                else "**赌错**" if q is not None else "未定")}
    (ROOT / "tests/data/production_retest_reliability_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "★无合法读数(不计入 q, 也不当作稳定)"},
                     ensure_ascii=False, indent=1))
    if bad:
        print(f"\n★★ 无合法读数 {len(bad)} 条(**不当作稳定**):",
              [r["id"] for r in bad])


if __name__ == "__main__":
    main()
