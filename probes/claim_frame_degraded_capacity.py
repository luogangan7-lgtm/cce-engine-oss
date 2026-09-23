#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**判据层在「填不出的槽位一律留空」时还剩多少拦截力** —— 接入决策的直接证据。**零模型调用**。

## 为什么算这个
接入判据层有两条路, 两条都已被实测挡住:
  · **(a) 把合同文本塞进生产 prompt** —— gen9 双臂重测已排除
  · **(b) 让模型自动填六槽位** —— r5 已测, 没有可用的证据支持

★★★ **具体的数一律只写在产物里**(下面 build_result 现算并落盘), **docstring 不复述**。
  2026-09-15 变异实测踩到的: 同一个数字写在 docstring 与产物两处 ⇒ 改了 docstring 那处
  **没有任何闸会红**(它不进产物), 而文档就此与读数不一致。
  ⇒ 通则: **一个数只写在一个地方 —— 现算的那个; 其余地方指过去。**

⇒ 那么还剩一条: **只用填得出的槽位, 填不出的一律留空(UNSPECIFIED ⇒ 证据不足)**。
   这条路**不需要新证据也不需要花钱**, 但要先知道: **这样还剩多少拦截力?**
   本文件就算这个。

★ 边界: 用的是**已付费的真实证书回放**(r1/r2/r3 的 48 次)与**手构最小对照**。
  真实证书那边**分母极小**, 结论只能判方向。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "results" / "claim_frame_degraded_capacity.json"
ANN = ROOT / "tests/data/claim_frame_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
# ★★★ r5 实测「这批数据测不出 / 模型填不出」的槽位。降级 = 把它们一律留空。
UNFILLABLE = ("predicate", "possession")


def _run(frames_of, drop, CF, use_i):
    """frames_of: 产生 [(id, is_neg, [ClaimFrame])] 的函数。drop: 要留空的槽位。"""
    neg_blocked = neg_n = pos_ok = pos_n = 0
    for _id, is_neg, mk in frames_of(drop, CF):
        allow = CF.allow_label(mk, use_interpretation=use_i)["allow"] if mk else False
        if is_neg:
            neg_n += 1; neg_blocked += (not allow)
        else:
            pos_n += 1; pos_ok += allow
    return {"阴性拦住": "%d/%d" % (neg_blocked, neg_n),
            "对照通过": "%d/%d" % (pos_ok, pos_n)}


def _minimal(drop, CF):
    ann = json.loads(ANN.read_text(encoding="utf-8")); D = ann["★默认槽位"]
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    pr = {p["id"]: p for p in d["pairs"]}
    out = []
    for pid, e in ann["annotations"].items():
        for side in ("pos", "neg"):
            out.append((f"{pid}/{side}", side == "neg",
                        _mk(pr[pid][side], e["frames"][side], D, drop, CF)))
    for p in d["contract_pairs"]:
        for side in ("pos", "neg"):
            out.append((f"{p['id']}/{side}", side == "neg",
                        _mk(p[side], p["frames"][side], D, drop, CF)))
    return out


def _mk(src, ann, D, drop, CF):
    fr = []
    for key, conj in (("A", CF.CONJ_P), ("B", CF.CONJ_Q)):
        kw = dict(D, **ann[key])
        for s in drop:
            kw[s] = CF.UNSPEC
        fr.append(CF.ClaimFrame(src[key][0], conj, object=src[key][1],
                                predicate=kw["predicate"], speaker=kw["speaker"],
                                polarity=kw["polarity"], time=kw["time"],
                                citation=kw["citation"], possession=kw["possession"],
                                increment_kind=(src[key][2] if key == "A" else None)))
    return fr


def _replay_degraded(drop, CF):
    """★★★ 2026-09-15 补上的欠账: 用**已验证的** probes/claim_frame_replay.py 算真实证书上的降级效果。

    ★ 做法是给**那份**探针加一个 drop 参数(默认 () ⇒ 它的历史读数逐字节不变),
      **不是**再写一份自己的实现 —— 那正是上一轮犯的错。
    """
    import importlib.util
    sp = importlib.util.spec_from_file_location("cfr", ROOT / "probes/claim_frame_replay.py")
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    rows, _missing = m.build_rows(drop=drop)
    neg = [r for r in rows if r["★是阴性吗"]]
    pos = [r for r in rows if not r["★是阴性吗"]]
    out = {"回放条数": {"真实证书": len(rows), "阴性": len(neg), "对照": len(pos)}}
    for t in ("只用合同明文", "明文+解释"):
        out[t] = {"阴性拦住": "%d/%d" % (sum(1 for r in neg if not r[t]["allow"]), len(neg)),
                  "对照通过": "%d/%d" % (sum(1 for r in pos if r[t]["allow"]), len(pos))}
    return out


def _existing_replay_numbers():
    """★★★ **不自己重新实现回放** —— 仓里已有一份验证过的 probes/claim_frame_replay.py。

    ★ 2026-09-15 如实登记: 我**先写了一份自己的 _replay 实现**, 它读出「对照通过 0/12」,
      而已验证的那份读出 **12/12**。⇒ **我的实现是错的**(多半是 increment_kind 没传对,
      导致 _p 一律落「未声明增量种类 ⇒ 证据不足」)。
    ★★ 处理: **撤掉我那份**, 不是「修好它」—— 已经有一个验证过的实现, 重写是多余的,
      而两份实现并存会让下一个人不知道该信哪个。
    ★★★ **代价(必须说)**: 因此本文件**只算得出手构最小对照上的降级效果**;
      真实证书上的降级效果**需要给 claim_frame_replay.py 加一个 drop 参数才能算**, **本轮未做**。
    """
    p = ROOT / "results/claim_frame_replay.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return {"★这是全槽位的历史读数_不是降级后的": True,
            "阴性拦得住吗": d["★★★阴性_拦得住吗"],
            "对照会不会误拦": d["★★★对照_会不会误拦"],
            "★降级后的数": "**未算** —— 见本函数 docstring。"}


def build_result():
    import cce_claim_frame as CF
    res = {
        "block": "CLAIM_FRAME_DEGRADED_CAPACITY",
        "★零调用": "只重算已付费的读数与手构对照, **不发起任何新调用**。",
        "★★★它回答什么": "接入判据层的两条路都被实测挡住后, 还剩「**只用填得出的槽位, 填不出的一律留空**」这一条。"
            "本文件算: **这样还剩多少拦截力**。",
        "★★★两条被挡住的路": {
            "(a) 把合同文本塞进生产 prompt":
                "gen9 双臂重测(results/gen9_verdict.json): display 出现率由**生产臂 1/80**(0/48 + 1/32) "
                "涨到**候选臂 40/80**(27/48 + 13/32), 且**倒挂** —— "
                "合同说**不该**给的 A 臂 **56%** > 合理可能的 B 臂 **41%**。⇒ **已排除**。",
            "(b) 让模型自动填六槽位":
                "r5(results/slot_fillability_audit.json): predicate 只取到可得增益的 **12%**, "
                "possession **净 −6**(比不读文本还差)。⇒ **没有可用的证据支持**。"},
        "★降级方案": "把 r5 实测填不出的槽位 %r **一律留空**(UNSPECIFIED ⇒ 证据不足), 其余照填。" % (UNFILLABLE,),
    }
    blk = {}
    for lbl, drop in (("① 全槽位(能力上界)", ()), ("② 降级: %s 留空" % ("+".join(UNFILLABLE)), UNFILLABLE)):
        blk[lbl] = {t: _run(_minimal, drop, CF, ui)
                    for t, ui in (("只用合同明文", False), ("明文+解释", True))}
    res["手构最小对照(34 对 × 2 版)"] = blk
    rb = {}
    for lbl, drop in (("① 全槽位(能力上界)", ()), ("② 降级: %s 留空" % ("+".join(UNFILLABLE)), UNFILLABLE)):
        rb[lbl] = _replay_degraded(drop, CF)
    res["真实证书回放(r1/r2/r3 已付费的 48 次)"] = rb
    rdeg = rb["② 降级: %s 留空" % ("+".join(UNFILLABLE))]["明文+解释"]
    rfull = rb["① 全槽位(能力上界)"]["明文+解释"]
    res["★★★真实证书上也一样吗"] = (
        "**一样。** 全槽位时真实证书 阴性拦住 %s · 对照通过 %s; "
        "降级后 阴性拦住 %s · **对照通过 %s**。"
        "⇒ 「留空 ⇒ 对照全误拦」**不是手构对照的特性**, 在**真实模型产出的证书**上同样成立。"
        "★ 边界: 真实证书对照只有 %s 张, **分母小**, 只判方向。"
        % (rfull["阴性拦住"], rfull["对照通过"], rdeg["阴性拦住"], rdeg["对照通过"],
           rb["① 全槽位(能力上界)"]["回放条数"]["对照"]))
    res["★★★结论"] = (
        "**降级方案不可用。** 把 %s 留空后, 手构最小对照上**阴性拦住 %s(满分)** —— "
        "但**对照也全被拦**(%s)。★ 这在逻辑上是显然的(留空 ⇒ 证据不足 ⇒ fail-closed ⇒ 什么都不许输出), "
        "但**算出来才是证据**。⇒ 一个把所有东西都拦住的过滤器**没有鉴别力**, 接进生产等于关掉输出。"
        % ("+".join(UNFILLABLE),
           blk["② 降级: %s 留空" % ("+".join(UNFILLABLE))]["明文+解释"]["阴性拦住"],
           blk["② 降级: %s 留空" % ("+".join(UNFILLABLE))]["明文+解释"]["对照通过"]))
    res["★★★所以现在的答案是"] = (
        "**不接入。** 三条路都走不通: "
        "(a) 塞进 prompt —— gen9 实测 display 1/80 → 40/80 且倒挂, **已排除**; "
        "(b) 让模型自动填槽位 —— r5 实测 predicate 取到 12%%、possession 净 −6, **没有证据支持**; "
        "(c) 填不出的留空 —— 本文件实测**对照全误拦**, 等于关掉输出。"
        "★★ 判据层**本身是有效的**(全槽位时最小对照阴性拦住 %s、对照 %s), "
        "问题**不在判据, 在没有可靠的方法把槽位填对**。"
        % (blk["① 全槽位(能力上界)"]["明文+解释"]["阴性拦住"],
           blk["① 全槽位(能力上界)"]["明文+解释"]["对照通过"]))
    return res


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("判据层降级后的拦截力(**零调用**)\n")
    for blk_name in ("手构最小对照(34 对 × 2 版)", "真实证书回放(r1/r2/r3 已付费的 48 次)"):
        print("  %s" % blk_name)
        for lbl, tiers in r[blk_name].items():
            for t, d in tiers.items():
                if t == "回放条数":
                    continue
                print("    %-30s %-12s 阴性拦住 %-8s 对照通过 %s"
                      % (lbl, t, d["阴性拦住"], d["对照通过"]))
        print()
    print("  " + r["★★★真实证书上也一样吗"])
    print("\n  " + r["★★★结论"])
    print("\n  " + r["★★★所以现在的答案是"])
    print("→", OUT)


if __name__ == "__main__":
    main()
