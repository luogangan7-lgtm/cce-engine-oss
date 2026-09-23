# -*- coding: utf-8 -*-
"""possession 三轮「负增益」的解剖。零调用。

★ 结论先写: 它是**打分口径的伪影**, 不是模型缺陷 ——
  合同的 Q 是析取(已拥有 **或** 已经历), 判据层对 OWNED 与 EXPERIENCED **给同一个结局**(SUPPORTS, 本文件现证);
  但槽位级打分把两者当不同答案, 而金标把 64/68 条 B 支一律记成 OWNED —— 其中一半的句子只说了「wear/use」没说「own」。
  模型越按定义字面读, 槽位分越低。
"""
import importlib.util, json, pathlib, re, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results/possession_gain_artifact.json"
RUNS = {"MiniMax r5(v3)": "results/slot_filling_r5.json", "MiniMax r6(v4)": "results/slot_filling_r6.json",
        "Jev r6-jev(v4)": "results/slot_filling_r6_jev.json"}
OWN = re.compile(r"\b(own|owned|mine|bought|got|picked up|have (?:a|an|the|these|two)|had (?:a|an|the|these))\b", re.I)
EQ = {"OWNED": "Q_SATISFIED", "EXPERIENCED": "Q_SATISFIED"}     # 合同等价类


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def claim_frame_equivalence(CF):
    """★ 现证: 只把 possession 从 OWNED 换成 EXPERIENCED, allow_label 两档结局逐字相同。"""
    base = dict(speaker="SELF", polarity="ASSERTED", time="PAST_OR_PRESENT", citation="DIRECT")
    out = {}
    for tier in (False, True):
        res = []
        for pv in ("OWNED", "EXPERIENCED"):
            fr = [CF.ClaimFrame("s1", CF.CONJ_P, object="X", increment_kind="数据", predicate="OF_DECLARED_KIND", possession=pv, **base),
                  CF.ClaimFrame("s2", CF.CONJ_Q, object="X", possession=pv, **base)]
            v = CF.allow_label(fr, use_interpretation=tier)
            res.append([v["allow"], {k: x["state"] for k, x in v["per_conjunct"].items()}])  # list 不是 tuple: JSON 读回逐键比对要相等
        out["明文+解释" if tier else "只用合同明文"] = {"OWNED": res[0], "EXPERIENCED": res[1], "★两值结局相同": res[0] == res[1]}
    return out


def build(m, CF):
    D = m.GOLD["★默认槽位"]; its = {it["id"]: it for it in m.items()}
    gold_B = {i: dict(D, **it["gold"]["B"])["possession"] for i, it in its.items()}
    lex = {i: ("含拥有词" if OWN.search(it["ev"][1][1]) else "只含使用词") for i, it in its.items()}
    per = {}
    for nm, rel in RUNS.items():
        p = ROOT / rel
        if not p.exists():
            continue
        rows = [r for r in json.loads(p.read_text(encoding="utf-8"))["rows"] if r.get("调用成功") and r["id"] in its]
        # r5 跑在 v3 上, ANX/HLD 的 id 相同但文本不同 —— 只对 v4 items 做词法对照; r5 只报总分
        raw = sum(1 for r in rows if (r["模型原样"]["片段二"] or {}).get("possession") == gold_B[r["id"]])
        eq = sum(1 for r in rows if EQ.get((r["模型原样"]["片段二"] or {}).get("possession")) == EQ.get(gold_B[r["id"]])
                 or (r["模型原样"]["片段二"] or {}).get("possession") == gold_B[r["id"]])
        base_raw = sum(1 for r in rows if gold_B[r["id"]] == "OWNED")
        conf = Counter((gold_B[r["id"]], (r["模型原样"]["片段二"] or {}).get("possession")) for r in rows)
        by_lex = Counter((lex[r["id"]], (r["模型原样"]["片段二"] or {}).get("possession")) for r in rows) if "v4" in nm else None
        per[nm] = {"n": len(rows), "槽位级原打分": "%d/%d" % (raw, len(rows)), "零基线(全填 OWNED)": "%d/%d" % (base_raw, len(rows)),
                   "原口径净增益": raw - base_raw,
                   "★合同等价类口径(OWNED≡EXPERIENCED)": "%d/%d" % (eq, len(rows)), "★等价类口径净增益": eq - base_raw,
                   "混淆(金标→模型)": {"%s→%s" % k: v for k, v in sorted(conf.items(), key=lambda kv: -kv[1])},
                   "★按 B 句词法(仅 v4 轮)": ({"%s→%s" % k: v for k, v in sorted(by_lex.items())} if by_lex else "r5 跑在 v3 文本上, 不比")}
    gold_lex = Counter((lex[i], gold_B[i]) for i in its)
    return {
        "block": "POSSESSION_GAIN_ARTIFACT", "date": "2026-09-23",
        "★零调用": "只读三轮已有产物与仓内金标, 不发调用、不改任何产物。",
        "★★★判据层现证: OWNED 与 EXPERIENCED 结局相同": claim_frame_equivalence(CF),
        "★★★金标怎么记的": {"B 支金标分布": dict(Counter(gold_B.values())),
                           "★按句子词法 × 金标": {"%s / 金标=%s" % k: v for k, v in sorted(gold_lex.items())},
                           "★读法": "「只含使用词」(I've worn / I use / I've had …)的句子也被记成 OWNED —— 金标没有区分「拥有」与「用过」, 因为合同的 Q 对两者不分。"},
        "★★★三轮对照": per,
        "★★★结论": {
            "①负增益是打分伪影": "槽位级打分把 OWNED/EXPERIENCED 当两个答案, 金标却按合同析取一律记 OWNED ⇒ 模型按定义字面读「wear/use」为 EXPERIENCED 就丢分。判据层对两者给同一结局(上面现证), 端到端 68/68 可用两轮都没受影响。",
            "②越字面越亏": "MiniMax r5 −6 → r6 −11 → Jev −24: Jev 把「含拥有词」28 条几乎全填 OWNED、「只含使用词」28 条填 EXPERIENCED —— 那是**最符合槽位定义**的填法, 却是三者里槽位分最低的。",
            "③按合同等价类重算": "见三轮对照的「★等价类口径净增益」—— 伪影消失后 possession 不再是负的。",
            "④不改冻结产物": "r5/r6/r6-jev 的槽位级数**保持原样**(它们按当时冻结的打分算的); 本文件只提供等价类口径的**附带读数**。要把等价类写进打分, 是下一轮预注册的事。"},
        "★不得据此说": ["不得说三个模型 possession 都对 —— ONE_NEGATED/BOTH_NEGATED 那 4 格没测(金标里只有 2+0 例)。",
                        "不得回头改 r5/r6/r6-jev 的槽位级数。"],
    }


def main():
    x = _load("probes/slot_filling_run_r6.py", "r6x"); m = x.patched()
    sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    out = build(m, CF); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for nm, v in out["★★★三轮对照"].items():
        print("  %-16s 原 %s(净 %+d) → 等价类 %s(净 %+d)" % (nm, v["槽位级原打分"], v["原口径净增益"], v["★合同等价类口径(OWNED≡EXPERIENCED)"], v["★等价类口径净增益"]))
    print("  判据层等价:", {k: v["★两值结局相同"] for k, v in out["★★★判据层现证: OWNED 与 EXPERIENCED 结局相同"].items()}); print("→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
