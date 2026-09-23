#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命题框架层的**能力上界**测量 —— **零模型调用**。

★★★ 它回答的是: **槽位标注正确时**, 新判据在五类语义关系上能拦住多少。
★★★ 它**不**回答: 槽位由谁填、填错多少。那是**另一个未测的问题**。
  ⇒ 本文件给出的是**上界**, 不是端到端表现。这条边界写进产物, 不靠自觉。

★ 对照基线: 同一批 10 对最小对照上, **现有资格层** 10/10 全部错误放行
  (results/semantic_blindspot_scan.json)。
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
ANN = ROOT / "tests/data/claim_frame_annotations.json"
BASE = ROOT / "results/semantic_blindspot_scan.json"
OUT = ROOT / "results" / "claim_frame_upper_bound.json"


def build(pair, side, ann, CF):
    """按标注造两条 ClaimFrame(P 支 + Q 支)。缺省槽位用冻结默认值。"""
    d = ANN_DEFAULT
    s = pair[side]
    fr = []
    for key, conj in (("A", CF.CONJ_P), ("B", CF.CONJ_Q)):
        ov = ann[side][key]
        kw = dict(d)
        kw.update(ov)
        fr.append(CF.ClaimFrame(
            s[key][0], conj, object=s[key][1],
            predicate=kw["predicate"], speaker=kw["speaker"], polarity=kw["polarity"],
            time=kw["time"], citation=kw["citation"], possession=kw["possession"],
            increment_kind=(s[key][2] if key == "A" else None)))
    return fr


def main():
    import cce_claim_frame as CF
    global ANN_DEFAULT
    a = json.loads(ANN.read_text(encoding="utf-8"))
    ANN_DEFAULT = a["★默认槽位"]
    pairs = {p["id"]: p for p in json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]}

    rows, by_cls = [], {}
    for pid, ent in a["annotations"].items():
        p = pairs[pid]
        r = {"id": pid, "cls": p["cls"], "依据": p["依据"]}
        for tier, use_i in (("只用合同明文", False), ("明文+解释", True)):
            t = {}
            for side in ("pos", "neg"):
                fr = build(p, side, ent["frames"], CF)
                res = CF.allow_label(fr, use_interpretation=use_i)
                t[side] = {"allow": res["allow"],
                           "per": {k: v["state"] for k, v in res["per_conjunct"].items()}}
            t["★错误放行"] = bool(t["neg"]["allow"])
            t["★对照有效"] = bool(t["pos"]["allow"])
            r[tier] = t
        rows.append(r)
        c = by_cls.setdefault(p["cls"], {"n": 0, "依据": p["依据"],
                                         "只用合同明文": 0, "明文+解释": 0, "对照": 0})
        c["n"] += 1
        c["只用合同明文"] += r["只用合同明文"]["★错误放行"]
        c["明文+解释"] += r["明文+解释"]["★错误放行"]
        c["对照"] += r["明文+解释"]["★对照有效"]

    n = len(rows)
    leak_mx = sum(r["只用合同明文"]["★错误放行"] for r in rows)
    leak_all = sum(r["明文+解释"]["★错误放行"] for r in rows)
    ctrl_mx = sum(r["只用合同明文"]["★对照有效"] for r in rows)
    ctrl_all = sum(r["明文+解释"]["★对照有效"] for r in rows)

    base = None
    if BASE.exists():
        base = json.loads(BASE.read_text(encoding="utf-8"))["★★★合计"]["错误放行"]

    res = {
        "block": "CLAIM_FRAME_UPPER_BOUND",
        "★零调用": "本测量**不发起任何模型调用**。槽位标注是**人工给定的正确答案**。",
        "★★★这是能力上界_不是端到端表现": "数是「**槽位标注正确时**判据能拦住多少」。"
            "★ 槽位**由谁填、填错多少**是**另一个未测的问题**; "
            "本层**不承诺**结构化抽取会正确, 它只把错误**挪到可逐项检验的地方**。",
        "★对照基线(现有资格层, 同一批 10 对)": base or "未跑",
        "★★★逐类错误放行": {
            k: {"只用合同明文": "%d/%d" % (v["只用合同明文"], v["n"]),
                "明文+解释": "%d/%d" % (v["明文+解释"], v["n"]),
                "对照有效": "%d/%d" % (v["对照"], v["n"]),
                "依据": v["依据"]}
            for k, v in by_cls.items()},
        "★★★合计": {"只用合同明文": "%d/%d" % (leak_mx, n),
                  "明文+解释": "%d/%d" % (leak_all, n),
                  "对照有效(明文)": "%d/%d" % (ctrl_mx, n),
                  "对照有效(明文+解释)": "%d/%d" % (ctrl_all, n)},
        "★★★两档为什么必须分开报": "**合同明文**买到的和**依赖解释**买到的, 是两个不同强度的东西。"
            "**不许合并**成一个总数 —— 合并会让「靠解释拦住的」**冒充**「合同支持的」。"
            "★ 解释类规则若被推翻, 对应那几类**自动回到漏**, 而明文那几类不受影响。",
        "★★★变异实测暴露的_规则冗余(如实登记)": {
            "现象": "在这 10 对最小对照上, **polarity(否定辖域) / possession(析取两支同否) / time(未来时)** "
                  "三条规则**互相冗余** —— 删掉任一条, 端到端结果**一点不变**。",
            "为什么冗余是**真实的**而不是标注错误":
                "否定型文本里, 片段落在否定辖域内**必然**伴随 possession 被否定; "
                "未来时的文本里 possession 也**必然**无法落到肯定的一支。这是语义上的真实共现。",
            "★★★但它带来一个真问题":
                "端到端对照**测不出每条规则单独是否在起作用**。最要命的是: "
                "**ONE_NEGATED 那条分支完全零覆盖** —— 把它从 UNDERDETERMINED 改成 REFUTES"
                "(即把「沉默」当成「否定」, 正是库内 2026-09-10 最值钱的教训所禁止的), "
                "**10 对最小对照一个都没红**。",
            "修法": "**分工**: 最小对照测**端到端能力上界**; **规则级单元测试**测每条规则单独是否在起作用。",
            "★★★变异实测复核(镜像_未动仓)": {
                "删 polarity NEGATED": "被抓到 ✅", "删 possession BOTH_NEGATED": "被抓到 ✅",
                "删 time FUTURE": "被抓到 ✅", "★ONE_NEGATED→REFUTES(把沉默当否定)": "被抓到 ✅",
                "缺槽位→REFUTES(靠常识补)": "被抓到 ✅", "解释档规则改成不可关": "被抓到 ✅",
                "零证据改成放行": "被抓到 ✅",
                "小计": "**7/7 全部被抓到**, 含端到端测不出的那四条。"},
            "★通则": "**冗余保护会让闸看起来绿, 而其中某条规则其实从未被测过。** "
                   "端到端对照全绿**不等于**每条规则都在起作用 —— 必须用**变异实测逐条验**。"},
        "★★★这一层与现有资格层的关系":
            "**新增一道, 不替换**。现有资格层验**形式**(片段逐字 · 两支同对象 · kind 在枚举内); "
            "本层验**命题是否被支持**(六槽位 ⇒ 支持/反驳/证据不足)。"
            "★ 两道都过才允许输出标签。★ 本层**未接进生产** —— 接线是另一件事, "
            "且要先解决「槽位由谁填」。",
        "★★★默认槽位必须 fail-closed":
            "标注档案的默认槽位**全部是 UNSPECIFIED**。2026-09-14 抓到我自己: "
            "原默认写的是 possession='OWNED' —— 那是 **fail-open**, "
            "漏标会被补成「支持」而不是「证据不足」。",
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("命题框架层 · 能力上界(**零调用** · 槽位标注正确)\n")
    print("  %-14s %-12s %-12s %-10s %s" % ("关系类", "明文漏", "明文+解释漏", "对照有效", "依据"))
    for k, v in by_cls.items():
        print("  %-14s %-12s %-12s %-10s %s"
              % (k, "%d/%d" % (v["只用合同明文"], v["n"]), "%d/%d" % (v["明文+解释"], v["n"]),
                 "%d/%d" % (v["对照"], v["n"]), v["依据"].strip("*")))
    print("\n  %-14s %-12s %-12s %s"
          % ("合计", "%d/%d" % (leak_mx, n), "%d/%d" % (leak_all, n),
             "对照 %d/%d" % (ctrl_all, n)))
    print("  ★ 对照基线(现有资格层): 错误放行 %s" % (base or "未跑"))
    print("\n→", OUT)


if __name__ == "__main__":
    main()
