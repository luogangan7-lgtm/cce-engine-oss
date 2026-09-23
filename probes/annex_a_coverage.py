#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**合同条款对照** —— 附件 A 是否可被观察到。**零模型调用**。

★★★ 为什么要有这份东西: 2026-09-14 owner 裁定附件 A 升为合同, 但当时同步登记了一个缺口 ——
  **五类语义关系最小对照里没有一类依据附件 A**, 所以升了合同, 上界读数 4/10 → 0/10 **逐字不变**。
  ⇒ **合同里多了一条, 度量面上却看不见它**。本文件补的就是这个: 让附件 A 在对照集上**可测**。

★★★ 它测什么: 判据层能不能把「只复述/指认对象标识」与「给出关于对象的陈述」分开。
★★★ 它不测什么: 槽位由谁填、填错多少(那是 r4 测的, 且 r4 的提示词枚举里**没有** RESTATES_IDENTIFIER);
  也不测自然语料上的频率 —— 两对是**手构最小对照**, 分母不是语料。

★ 与 pairs 那 10 对的关系: **并列, 不合并**。合并要改冻结金标(r4 按 sha8 5a018edd 钉死), 等于事后动已付费那一轮的基准。
"""
import importlib.util, json, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
SRC = ROOT / "tests/data/semantic_minimal_pairs.json"
CF_SRC = ROOT / "scripts/cce_claim_frame.py"
BLIND = ROOT / "probes/semantic_blindspot_scan.py"
OUT = ROOT / "results" / "annex_a_coverage.json"

DEFAULT = {"speaker": "UNSPECIFIED", "polarity": "UNSPECIFIED", "time": "UNSPECIFIED",
           "citation": "UNSPECIFIED", "predicate": "UNSPECIFIED", "possession": "UNSPECIFIED"}
ANCHOR = '    if f.predicate == "RESTATES_IDENTIFIER":'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _frames(pair, side, CF):
    """按对里自带的 frames 造两条 ClaimFrame。★ 标注**不取自冻结金标** —— 见文件头。"""
    s, ann = pair[side], pair["frames"][side]
    out = []
    for key, conj in (("A", CF.CONJ_P), ("B", CF.CONJ_Q)):
        kw = dict(DEFAULT, **ann[key])
        out.append(CF.ClaimFrame(
            s[key][0], conj, object=s[key][1],
            predicate=kw["predicate"], speaker=kw["speaker"], polarity=kw["polarity"],
            time=kw["time"], citation=kw["citation"], possession=kw["possession"],
            increment_kind=(s[key][2] if key == "A" else None)))
    return out


def run(pairs, CF):
    """跑两档, 返回 (rows, 合计)。"""
    rows = []
    for p in pairs:
        r = {"id": p["id"], "cls": p["cls"], "依据": p["依据"]}
        for tier, use_i in (("只用合同明文", False), ("明文+解释", True)):
            t = {}
            for side in ("pos", "neg"):
                res = CF.allow_label(_frames(p, side, CF), use_interpretation=use_i)
                t[side] = {"allow": res["allow"],
                           "per": {k: v["state"] for k, v in res["per_conjunct"].items()}}
            t["★错误放行"] = bool(t["neg"]["allow"])
            t["★对照有效"] = bool(t["pos"]["allow"])
            r[tier] = t
        rows.append(r)
    n = len(rows)
    tot = {
        "只用合同明文_错误放行": "%d/%d" % (sum(r["只用合同明文"]["★错误放行"] for r in rows), n),
        "明文+解释_错误放行": "%d/%d" % (sum(r["明文+解释"]["★错误放行"] for r in rows), n),
        "只用合同明文_对照有效": "%d/%d" % (sum(r["只用合同明文"]["★对照有效"] for r in rows), n),
        "明文+解释_对照有效": "%d/%d" % (sum(r["明文+解释"]["★对照有效"] for r in rows), n),
    }
    return rows, tot


MUTATIONS = {
    "★把附件A降回解释档(即撤销 owner 的裁定)":
        (ANCHOR, '    if use_interpretation and f.predicate == "RESTATES_IDENTIFIER":'),
    "把只复述标识判成支持(等于没这条规则)":
        (ANCHOR, '    if False and f.predicate == "RESTATES_IDENTIFIER":'),
    "★恒拦: P 支一律反驳(一刀切的假成绩)":
        ('def _p(f, use_interpretation):\n    """判 P = 输出新信息增量。返回 (状态, 理由, 依据档)。"""',
         'def _p(f, use_interpretation):\n    """判 P。"""\n    return REFUTES, "mutant", BY_CONTRACT'),
}


def mutate(pairs, base):
    """★★★ 镜像变异实测(**不动仓**): 每个变异体在临时目录里跑, 看这套对照能不能观察到差别。

    ★ 结论**现跑**, 不手写 —— 手写进档案的结论会在判据变化后悄悄过期。
    """
    src = CF_SRC.read_text(encoding="utf-8")
    out = {}
    with tempfile.TemporaryDirectory() as td:
        for name, (old, new) in MUTATIONS.items():
            if old not in src:
                out[name] = "★★★ 锚点失配 —— 变异**没打中**, 这条不算证据"
                continue
            p = pathlib.Path(td) / ("m_%d.py" % abs(hash(name)))
            p.write_text(src.replace(old, new, 1), encoding="utf-8")
            try:
                _, tot = run(pairs, _load(p, p.stem))
            except Exception as e:                       # 变异体崩了也是一种「被抓到」
                out[name] = "被抓到 ✅ (变异体抛错: %s)" % type(e).__name__
                continue
            diff = {k: "%s → %s" % (base[k], tot[k]) for k in base if base[k] != tot[k]}
            out[name] = ("被抓到 ✅ " + json.dumps(diff, ensure_ascii=False)) if diff else \
                        "★★★ 没被抓到 —— 这套对照对该变异**不敏感**"
    return out


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    pairs = d["contract_pairs"]
    import cce_claim_frame as CF
    rows, tot = run(pairs, CF)

    # 对照基线: 现有资格层(形式验证)在同两对上漏多少
    import cce_label_qualification as LQ
    bl = _load(BLIND, "blindspot")
    base_rows = []
    for p in pairs:
        e = {"id": p["id"]}
        for side in ("pos", "neg"):
            st, _why = bl.judge(p[side]["text"], p[side]["A"], p[side]["B"])
            e[side] = {"state": st, "通过": st == LQ.CITED_UNVERIFIED}
        e["★错误放行"] = e["neg"]["通过"]
        e["★对照有效"] = e["pos"]["通过"]
        base_rows.append(e)
    n = len(pairs)
    base_leak = "%d/%d" % (sum(r["★错误放行"] for r in base_rows), n)
    base_ctrl = "%d/%d" % (sum(r["★对照有效"] for r in base_rows), n)

    mut = mutate(pairs, tot)

    res = {
        "block": "ANNEX_A_COVERAGE",
        "★零调用": "本测量**不发起任何模型调用**。槽位标注是**人工给定的正确答案**(写在对照对自带的 frames 里)。",
        "★★★这份东西回答什么": "**附件 A 这一条合同条款, 在对照集上是否可被观察到。** "
            "2026-09-14 升合同时同步登记的缺口是: 五类语义关系里**没有一类依据附件 A**, "
            "所以升合同后上界 4/10 → 0/10 **逐字不变** —— 合同多了一条, 度量面看不见。本文件补上这个。",
        "★★★它给的仍是能力上界_不是端到端": "槽位标注是**给定的正确答案**。"
            "★ 特别注意: r4(模型自己填槽位)的提示词枚举里**根本没有 RESTATES_IDENTIFIER** 这个取值 "
            "⇒ **模型在 r4 里无从填出它**, 本节的数**不能**读成「模型能做到」。",
        "★对照基线(现有资格层_形式验证)": {"错误放行": base_leak, "对照有效": base_ctrl, "rows": base_rows},
        "★★★合计": tot,
        "★★★两档为什么必须分开报": "**合同明文**买到的和**依赖解释**买到的是两个不同强度的东西, **不许合并**。"
            "★ 本节两对的依据是**合同明文**(附件 A 已升) ⇒ 两档应当**相同**; "
            "若只有「明文+解释」档拦得住, 说明判据实际上没把它当合同。",
        "★★★镜像变异实测(现跑_未动仓)": mut,
        "★★★变异里最要紧的那条": "「**把附件 A 降回解释档**」—— 它模拟的是 owner 的裁定被撤销。"
            "若这条**没被抓到**, 说明这套对照测的不是附件 A, 而是别的什么东西。",
        "★★★为什么要有「恒拦」这条变异": "一个把 P 支一律判反驳的退化判据, 在**只看错误放行**的读法下是满分(0/2 漏)。"
            "★ 必须由**对照有效**那一列拆穿它 —— 只报漏数不报对照, 任何一刀切都能拿满分。",
        "★★★边界": "① 两对是**手构最小对照**, 分母不是自然语料, **不得当误报率**; "
            "② 测的是**判据层**的可观察性, **不是**模型的错误率; "
            "③ 本层**未接进生产** —— 判据层一个字都不进 prompt(gen9 实测塞进 s2 prompt 会让 display 由 1/80 涨到 40/80 且倒挂)。",
        "★为什么不并进那 10 对": d["★★★contract_pairs 是什么_为什么不并进 pairs"],
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("合同条款对照 · 附件 A 可观察性(**零调用**)\n")
    print("  %-8s %-8s %-14s %-14s" % ("id", "类", "明文漏", "明文+解释漏"))
    for r in rows:
        print("  %-8s %-8s %-14s %-14s"
              % (r["id"], r["cls"], r["只用合同明文"]["★错误放行"], r["明文+解释"]["★错误放行"]))
    print("\n  合计: " + " · ".join("%s %s" % (k, v) for k, v in tot.items()))
    print("  ★ 对照基线(现有资格层): 错误放行 %s · 对照有效 %s" % (base_leak, base_ctrl))
    print("\n  镜像变异实测:")
    for k, v in mut.items():
        print("    %-40s %s" % (k, v))
    print("\n→", OUT)


if __name__ == "__main__":
    main()
