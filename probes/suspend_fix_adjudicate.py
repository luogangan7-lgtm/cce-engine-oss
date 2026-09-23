#!/usr/bin/env python3
"""修法确证的判决 —— 判据在看到读数之前写完。零 API。
预注册: tests/data/suspend_fix_confirmation_prereg.json (新题校验和 6627d70e135d0113)
"""
import json
import pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/suspend_fix_confirm/raw.json")


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def fisher(a, b, c, d, tail="upper"):
    """★★ 2026-09-08 修: 原实现只有**上尾** P(X>=a), 而调用处的标签写的是「V1<V0」——
    **报出来的是补集**(MiniMax 报 0.9998, 正确的下尾是 0.00129)。
    ★ 判据本身不吃这个 p(C1 用的是 V1 命中率 <=0.20), 所以**判决未受影响, 已逐项核对**;
      但一个方向相反的统计量挂在结论里, 读的人会读反。
    """
    n1, n2, k = a + b, c + d, a + c
    if tail == "upper":
        rng = range(a, min(n1, k) + 1)
    else:
        rng = range(max(0, k - n2), a + 1)
    return sum(comb(n1, i) * comb(n2, k - i) for i in rng) / comb(n1 + n2, k)


def main():
    rows = [r for r in json.loads(RAW.read_text(encoding="utf-8")) if r["top1"]]
    res = {"block": "SUSPEND_FIX_CONFIRMATION_RESULT",
           "★prereg": "tests/data/suspend_fix_confirmation_prereg.json",
           "★synthetic": "★★ 仍是 SYNTHETIC_DIAGNOSTIC。即使全过, **只证明修法在构造题上有效**, 不证明修好了自然评论。",
           "n_parsed": len(rows)}

    def r8(rs, cells):
        s = [x for x in rs if x["cell"] in cells]
        k = sum(1 for x in s if x["top1"] == "suspend")
        return k, len(s), (round(k / len(s), 3) if s else None), wilson(k, len(s))

    FAIL = ["已决定_延后执行", "历史悬置_现已决定"]
    TRUE = ["★真悬置_必须仍判"]
    ADV_P = ["★悬置_未来时间词"]
    ADV_D = ["★已决定_未来时间词"]
    for fam, pred in (("MiniMax五员", lambda r: not r["model"].startswith("glm")),
                      ("GLM跨家族", lambda r: r["model"].startswith("glm"))):
        rs = [r for r in rows if pred(r)]
        out = {}
        for arm in ("V0", "V1"):
            a = [r for r in rs if r["arm"] == arm]
            out[arm] = {"失败方向": r8(a, FAIL), "真悬置": r8(a, TRUE),
                        "对抗_悬置未来词": r8(a, ADV_P), "对抗_已决定未来词": r8(a, ADV_D)}
        f0k, f0n = out["V0"]["失败方向"][:2]
        f1k, f1n = out["V1"]["失败方向"][:2]
        t0 = out["V0"]["真悬置"][2] or 0
        t1 = out["V1"]["真悬置"][2] or 0
        p_c1 = fisher(f1k, f1n - f1k, f0k, f0n - f0k, tail="lower") if f0n and f1n else None
        ap, ad = out["V1"]["对抗_悬置未来词"], out["V1"]["对抗_已决定未来词"]
        p_c3 = fisher(ap[0], ap[1] - ap[0], ad[0], ad[1] - ad[0]) if ap[1] and ad[1] else None
        out["★C1_修法在失败方向上有效"] = {
            "V0": f"{f0k}/{f0n}={f0k/max(f0n,1):.1%}", "V1": f"{f1k}/{f1n}={f1k/max(f1n,1):.1%}",
            "fisher_p单侧(V1<V0,下尾)": round(p_c1, 5) if p_c1 is not None else None,
            "★n": f"V0 n={f0n} · V1 n={f1n}" + ("  ★两臂 n 不等: 解析失败数不同" if f0n != f1n else ""),
            "verdict": "PASS" if (f1n and f1k / f1n <= 0.20) else "★★FAIL: 修法无效或不足"}
        out["★★C2_修法不许压掉真悬置"] = {
            "V0": t0, "V1": t1, "差": round(t1 - t0, 3),
            "verdict": "PASS" if (t1 >= 0.70 and abs(t1 - t0) <= 0.20) else "★★★FAIL: **修法过度**, 把真悬置也排掉了"}
        out["★C3_对抗组能分开"] = {
            "悬置+未来词": f"{ap[0]}/{ap[1]}={ap[2]}", "已决定+未来词": f"{ad[0]}/{ad[1]}={ad[2]}",
            "fisher_p": round(p_c3, 5) if p_c3 is not None else None,
            "★检定力": (f"n={ap[1]} vs {ad[1]}" + ("  ★★ 完全分离下的**最小可能 p**, 该臂无检定力"
                        if (p_c3 is not None and ap[1] <= 3 and ad[1] <= 3) else "")),
            "verdict": "PASS" if (ap[2] is not None and ad[2] is not None and ap[2] > ad[2]) else
                       "★★FAIL: 靠 time 维度判而非决策状态 ⇒ 修 negative_examples 治不了根"}
        res[fam] = out
    # ══ ★★★ 事后敏感性: 差别性缺失 ══════════════════════════════════════════
    #  首轮实测: 4 条解析失败**全在 V1 臂、全是 glm-4.5-flash**(V1 4/132 vs V0 0/132,
    #  单侧 Fisher p=0.0611)。缺失若与结果相关, 会**机械地帮 V1** —— 判据分母变小。
    #  ★ 本块是**事后加的**, 明确标注; 它只能让判决**更严**, 不放宽任何一条。
    #  ★ 判据 C1~C4 本身**一字未改**。
    allrows = json.loads(RAW.read_text(encoding="utf-8"))
    for fam, pred in (("MiniMax五员", lambda r: not r["model"].startswith("glm")),
                      ("GLM跨家族", lambda r: r["model"].startswith("glm"))):
        sub = [r for r in allrows if pred(r)]
        blk = {}
        for name, cells, arm, worst in (("C1_失败方向", FAIL, "V1", "suspend"),
                                        ("C2_真悬置", TRUE, "V1", "non_suspend")):
            cs = [r for r in sub if r["cell"] in cells and r["arm"] == arm]
            ok = [r for r in cs if r["top1"]]
            miss = len(cs) - len(ok)
            k = sum(1 for r in ok if r["top1"] == "suspend")
            if worst == "suspend":
                wc = (k + miss) / (len(ok) + miss) if (len(ok) + miss) else None
                holds = wc is not None and wc <= 0.20
            else:
                wc = k / (len(ok) + miss) if (len(ok) + miss) else None
                holds = wc is not None and wc >= 0.70
            blk[name] = {"缺失条数": miss, "最坏界": round(wc, 4) if wc is not None else None,
                         "最坏界下判据": ("**仍成立**" if holds else "**翻成 FAIL**") if miss else "无缺失, 不适用"}
        res[fam]["★★★事后_差别性缺失敏感性"] = blk
        res[fam]["★★★事后_差别性缺失敏感性"]["★这是事后加的"] = (
            "★ C1~C4 判据一字未改; 本块只给**最坏界**, 只能让判决更严。"
            "★ 缺失若集中在一臂, 判据分母变小会**机械地帮那一臂** —— 预注册没预见这个失败模式。")

    # ══ ★★★ 2026-09-09 统计单位更正(网页版 GPT-6 Pro 指出, 我已复核并确认) ═══════
    #  原判决把「题 × 模型」当独立样本: C1 的 n=40 实际是 **8 题 × 5 模型**。
    #  同一题被 5 个模型判读有**共同题目效应**, 同一题跨臂是**配对**的 ⇒ **伪重复**。
    #  ⇒ Fisher 表按 40 个独立观测算, p 值被系统性夸大。
    #  ★ 本块以**题**为分析单位重算; **原数保留并列**, 不删 —— 记账要看得见改了什么。
    #  ★ 判据 C1~C4 的**阈值一字未改**; 变的是「这个结果支持多强的推断」。
    from collections import defaultdict as _dd
    for fam, pred in (("MiniMax五员", lambda r: not r["model"].startswith("glm")),
                      ("GLM跨家族", lambda r: r["model"].startswith("glm"))):
        blk = {}
        for name, cells in (("C1_失败方向", FAIL), ("C2_真悬置", TRUE)):
            per = _dd(dict)
            for r in rows:
                if r["cell"] in cells and pred(r) and r["top1"]:
                    per[r["id"]].setdefault(r["arm"], []).append(r["top1"] == "suspend")
            items = sorted(per)
            pairs = [(sum(per[i].get("V0", [])), len(per[i].get("V0", [])),
                      sum(per[i].get("V1", [])), len(per[i].get("V1", []))) for i in items]
            down = sum(1 for a, an, b, bn in pairs if b < a)
            up = sum(1 for a, an, b, bn in pairs if b > a)
            nn = down + up
            psign = (sum(comb(nn, i) for i in range(down, nn + 1)) / (2 ** nn)) if nn else 1.0
            maj0 = sum(1 for a, an, b, bn in pairs if an and a / an > .5)
            maj1 = sum(1 for a, an, b, bn in pairs if bn and b / bn > .5)
            blk[name] = {"题数": len(items), "题级配对": f"降 {down} · 升 {up} · 平 {len(pairs)-nn}",
                         "单侧精确符号检验p": round(psign, 5),
                         "题级多数判suspend": f"V0 {maj0}/{len(pairs)} → V1 {maj1}/{len(pairs)}",
                         "★逐题": [{"id": i, "V0": f"{a}/{an}", "V1": f"{b}/{bn}"}
                                    for i, (a, an, b, bn) in zip(items, pairs)]}
        blk["★★★读法"] = (
            "★ 以**题**为分析单位。原判决的 n=40 是 8 题 × 5 模型, 属**伪重复**(同题共享题目效应, 同题跨臂配对)。"
            "⇒ 上面按 题×模型 算出的 Fisher p **夸大了推断强度**, 以本块为准。"
            "★★ 但**效应本身稳健**: 失败方向零个反向。判据阈值一字未改, 变的只是「支持多强的推断」。")
        res[fam]["★★★事后_题级统计单位更正"] = blk

    v = {f: res[f]["★C1_修法在失败方向上有效"]["verdict"] for f in ("MiniMax五员", "GLM跨家族")}
    res["★C4_跨家族同向"] = {"per_family": v,
                             "verdict": "PASS" if len(set(v.values())) == 1 else "方向不一致"}
    allv = [res[f][k]["verdict"] for f in ("MiniMax五员", "GLM跨家族")
            for k in ("★C1_修法在失败方向上有效", "★★C2_修法不许压掉真悬置", "★C3_对抗组能分开")]
    frail = [f"{f}·{k}" for f in ("MiniMax五员", "GLM跨家族")
             for k, v in res[f]["★★★事后_差别性缺失敏感性"].items()
             if isinstance(v, dict) and v["最坏界下判据"] == "**翻成 FAIL**"]
    res["★★★overall"] = ("**未全过 ⇒ 不换代, 现网 prompt 不动**" if not all(x == "PASS" for x in allv)
                          else ("ALL_PASS 且**对缺失稳健**" if not frail else
                                f"ALL_PASS(按冻结判据) ★★但**不稳健**: {frail} 在最坏界下翻 FAIL "
                                "⇒ 必须补齐缺失读数后重判, 不得据此换代"))
    (ROOT / "tests/data/suspend_fix_confirmation_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for f in ("MiniMax五员", "GLM跨家族"):
        print(f"\n═══ {f} ═══")
        for k in ("★C1_修法在失败方向上有效", "★★C2_修法不许压掉真悬置", "★C3_对抗组能分开"):
            print(f"  {k}: {res[f][k]}")
    print(f"\n★ C4 {res['★C4_跨家族同向']}")
    print(f"★★★ 总判: {res['★★★overall']}")


if __name__ == "__main__":
    main()
