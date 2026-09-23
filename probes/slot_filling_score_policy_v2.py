# -*- coding: utf-8 -*-
"""填槽打分策略 v2: possession 按**合同等价类**打分。零调用。

★ 为什么: results/possession_gain_artifact.json 现证 —— 判据层对 OWNED 与 EXPERIENCED 给同一结局(合同 Q 是析取),
  而 v1 打分把两者当两个答案 ⇒ 三轮「负增益」是打分伪影。
★ 等价类**不手写**: 由 scripts/cce_claim_frame.allow_label 在标准框架上**现算**每个取值的结局, 结局相同者同类。
  合同若改, 类随之变; 闸会核「类是现算的」。
★ 只改 possession 这一槽; 其他槽位 v1 照旧。r5/r6/r6-jev 的冻结产物**一字节不改**, 本文件只提供 v2 口径的**附带读数**(可比不可合);
  v2 是 **r7 起**的正式打分口径(预注册 tests/data/slot_filling_score_policy_v2_prereg.json)。
"""
import hashlib, importlib.util, json, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
PREREG = ROOT / "tests/data/slot_filling_score_policy_v2_prereg.json"; OUT = ROOT / "results/slot_filling_score_policy_v2.json"
RUNS = {"MiniMax r5(v3)": "results/slot_filling_r5.json", "MiniMax r6(v4)": "results/slot_filling_r6.json", "Jev r6-jev(v4)": "results/slot_filling_r6_jev.json"}
MIN_GOLD_PER_CLASS = 6   # 金标少于此的类标「测不出」(与「可得增益 ≤2 ⇒ 测不出」同精神, 但按类计数)


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def derive_classes(CF):
    """possession 每个合法取值 → 判据层两档结局; 结局相同者同一等价类。返回 {取值: 类名}, 类名 = 该类里按 CF.POSSESSION 顺序的第一个取值。"""
    base = dict(speaker="SELF", polarity="ASSERTED", time="PAST_OR_PRESENT", citation="DIRECT")
    outcome = {}
    for pv in CF.POSSESSION:
        sig = []
        for tier in (False, True):
            fr = [CF.ClaimFrame("s1", CF.CONJ_P, object="X", increment_kind="数据", predicate="OF_DECLARED_KIND", possession=pv, **base),
                  CF.ClaimFrame("s2", CF.CONJ_Q, object="X", possession=pv, **base)]
            v = CF.allow_label(fr, use_interpretation=tier)
            sig.append((v["allow"], tuple(sorted((k, x["state"]) for k, x in v["per_conjunct"].items()))))
        outcome[pv] = tuple(sig)
    cls = {}
    for pv in CF.POSSESSION:
        rep = next(q for q in CF.POSSESSION if outcome[q] == outcome[pv]); cls[pv] = rep
    return cls, {pv: [[a, dict(b)] for a, b in sig] for pv, sig in outcome.items()}


def same_class(mv, gv, cls): return cls.get(mv) is not None and cls.get(mv) == cls.get(gv)


def rescore(m, CF, cls):
    """三轮冻结产物按 v2 口径重算 possession(B 支)。零基线 = 全填 OWNED, 也按类算。"""
    D = m.GOLD["★默认槽位"]; its = {it["id"]: it for it in m.items()}
    gold_B = {i: dict(D, **it["gold"]["B"])["possession"] for i, it in its.items()}
    per = {}
    for nm, rel in RUNS.items():
        p = ROOT / rel
        if not p.exists(): continue
        rows = [r for r in json.loads(p.read_text(encoding="utf-8"))["rows"] if r.get("调用成功") and r["id"] in its]
        mv = {r["id"]: (r["模型原样"]["片段二"] or {}).get("possession") for r in rows}
        v1 = sum(1 for i in mv if mv[i] == gold_B[i]); v2 = sum(1 for i in mv if same_class(mv[i], gold_B[i], cls))
        z1 = sum(1 for i in mv if gold_B[i] == "OWNED"); z2 = sum(1 for i in mv if same_class("OWNED", gold_B[i], cls))
        gold_cls = Counter(cls.get(gold_B[i], gold_B[i]) for i in mv)
        per[nm] = {"n": len(rows), "v1 槽位级": "%d/%d" % (v1, len(rows)), "v1 零基线(全 OWNED)": "%d/%d" % (z1, len(rows)), "v1 净增益": v1 - z1,
                   "v2 等价类": "%d/%d" % (v2, len(rows)), "v2 零基线(全 OWNED, 按类)": "%d/%d" % (z2, len(rows)), "v2 净增益": v2 - z2, "v2 可得增益": len(rows) - z2,
                   "金标按类": dict(gold_cls), "★测不出的类(金标 < %d)" % MIN_GOLD_PER_CLASS: sorted({c for c in cls.values() if gold_cls.get(c, 0) < MIN_GOLD_PER_CLASS}),
                   "★产物 sha256(未改)": hashlib.sha256(p.read_bytes()).hexdigest()}
    return per


def build():
    x = _load("probes/slot_filling_run_r6.py", "r6x_pol"); m = x.patched(); import cce_claim_frame as CF
    cls, outcomes = derive_classes(CF)
    return {"block": "SLOT_FILLING_SCORE_POLICY_V2", "date": "2026-09-23", "★零调用": True,
            "★预注册 sha": hashlib.sha256(PREREG.read_bytes()).hexdigest()[:16] if PREREG.exists() else None,
            "★判据源 sha(cce_claim_frame.py)": hashlib.sha256((ROOT / "scripts/cce_claim_frame.py").read_bytes()).hexdigest()[:16],
            "★★★等价类(由判据层现算, 不手写)": cls, "★每个取值的两档结局": outcomes,
            "★★★三轮对照(可比不可合, 冻结产物未改)": rescore(m, CF, cls),
            "★怎么读": ["v2 是 r7 起的正式口径; 三轮的 v1 数保留原样。", "「测不出的类」= 金标里该类样本太少, 该类的对错不得引用为能力证据。", "等价类若变(合同改), 本产物作废重算。"]}


def main():
    r = build(); OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("等价类:", r["★★★等价类(由判据层现算, 不手写)"])
    for k, v in r["★★★三轮对照(可比不可合, 冻结产物未改)"].items(): print("  %-16s v1 %s(净 %+d) → v2 %s(净 %+d) 测不出 %s" % (k, v["v1 槽位级"], v["v1 净增益"], v["v2 等价类"], v["v2 净增益"], v["★测不出的类(金标 < 6)"]))
    print("→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
