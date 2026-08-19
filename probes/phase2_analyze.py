#!/usr/bin/env python3
"""Phase 2 分析 —— 三条 profile，**不压成一个 PASS**。

## 前登记约束（本脚本自己也要守）
★ 禁止用本批数据现算 delta_resolution, 再拿它给**同一批** A 臂发合格证。
  「一次买两样可以; 拿其中一样给另一样现场发毕业证不可以。」
  ⇒ 本脚本**不设**任何以本批 L0/L0b 分位数为阈值的合格判定, 只出分布。
★ primary(盲验 FOLLOWS) 与 sensitivity(全部机器验收通过) 两套都跑;
  任一 headline 判决不一致 ⇒ 该判决记 INDETERMINATE。
★ 指纹用**真实内容**导出, 不用 f"x{i}" 这种合成串 ——
  Phase 1 传了合成指纹, 等于把 _check 的缓存伪影守卫绕过去了。
  真指纹下若出现重复, 是**发现**(疑似缓存/退化), 按 finding 报告, 不静默替换。
"""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as KS   # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
ARMS_B = ("B1", "B2")
ARMS_A = ("A1", "A2", "A3")


def fp(rec):
    """真实内容指纹: 读数向量 + k_valid + 首次成功率。重复 = 疑似缓存/退化。"""
    payload = json.dumps({"k": rec["knots"], "kv": rec["k_valid"],
                          "f": (rec.get("op") or {}).get("first_attempt_success_rate")},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load():
    src = P / "panel_checkpoint.jsonl"
    return [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]


def contrasts(rows, only_primary):
    by = defaultdict(list)
    for r in rows:
        if not r["qualified"]:
            continue
        if only_primary and not r["in_primary"]:
            continue
        by[(r["base_id"], r["arm"])].append(r)
    out, findings = [], []
    bases = sorted({b for b, _ in by})
    for b in bases:
        L0 = by.get((b, "L0"), [])
        if len(L0) < 4:
            continue
        for arm in ("L0b",) + ARMS_A + ARMS_B:
            X = by.get((b, arm), [])
            if len(X) < 4:
                continue
            A, B = [r["knots"] for r in L0[:4]], [r["knots"] for r in X[:4]]
            fa, fb = [fp(r) for r in L0[:4]], [fp(r) for r in X[:4]]
            dup = [k for k, v in Counter(fa + fb).items() if v > 1]
            if dup:
                findings.append({"base_id": b, "arm": arm, "issue": "DUPLICATE_FINGERPRINT",
                                 "n_dup": len(dup),
                                 "note": "同一读数向量重复出现 ⇒ 疑似缓存伪影或读数退化"})
                continue
            s = KS.separation(A, B, fa, fb, nameA="L0", nameB=arm)
            out.append({"base_id": b, "arm": arm, "T": s["T"], "p": s["p"],
                        "verdict": s["verdict"],
                        "separated": s["verdict"] == "SEPARATED",
                        "null_max": s["null_max"],
                        "length_stratum": X[0]["length_stratum"],
                        "generator_family": X[0]["generator_family"]})
    return out, findings


def profile(cs, arm):
    v = sorted(c["T"] for c in cs if c["arm"] == arm)
    if not v:
        return None
    q = lambda p: v[min(int(p * len(v)), len(v) - 1)]
    return {"n": len(v), "min": round(v[0], 5), "q25": round(q(.25), 5),
            "median": round(q(.5), 5), "q75": round(q(.75), 5), "max": round(v[-1], 5),
            "n_separated": sum(1 for c in cs if c["arm"] == arm and c["separated"])}


def summarize(cs):
    null = {c["base_id"]: c["T"] for c in cs if c["arm"] == "L0b"}
    res = {"resolution_profile_candidate": profile(cs, "L0b"),
           "invariance_profile": {a: profile(cs, a) for a in ARMS_B},
           "perturbation_profile": {a: profile(cs, a) for a in ARMS_A}}
    # P[Ax > 同 base 的零参照]
    gt = {}
    for a in ARMS_A + ARMS_B:
        pairs = [(c["T"], null[c["base_id"]]) for c in cs
                 if c["arm"] == a and c["base_id"] in null]
        gt[a] = {"n": len(pairs),
                 "P_gt_same_null": round(sum(1 for t, n in pairs if t > n) / len(pairs), 3)
                 if pairs else None}
    res["vs_same_base_null"] = gt
    # 单调性 P[A1<A2<A3] —— 只在三臂齐全的 base 上算
    byb = defaultdict(dict)
    for c in cs:
        byb[c["base_id"]][c["arm"]] = c["T"]
    full = [d for d in byb.values() if all(a in d for a in ARMS_A)]
    res["monotonicity"] = {
        "n_bases_with_all_A": len(full),
        "P_A1_lt_A2_lt_A3": round(sum(1 for d in full
                                      if d["A1"] < d["A2"] < d["A3"]) / len(full), 3)
        if full else None}
    return res


if __name__ == "__main__":
    rows = load()
    print(f"reps {len(rows)} (qualified {sum(1 for r in rows if r['qualified'])})")
    out = {}
    for label, only in (("primary", True), ("sensitivity", False)):
        cs, fnd = contrasts(rows, only)
        out[label] = {"n_contrasts": len(cs), "summary": summarize(cs),
                      "findings": fnd, "contrasts": cs}
        s = out[label]["summary"]
        print(f"\n--- {label} ({len(cs)} 组对比) ---")
        print(f"  零参照 T(L0,L0b): {s['resolution_profile_candidate']}")
        for a in ARMS_A + ARMS_B:
            pr = (s["perturbation_profile"] if a in ARMS_A else s["invariance_profile"])[a]
            print(f"  {a}: {pr}  P(>同base零参照)={s['vs_same_base_null'][a]['P_gt_same_null']}")
        print(f"  单调性 P[A1<A2<A3] = {s['monotonicity']}")
        if fnd:
            print(f"  ★ findings: {len(fnd)} 条 —— {Counter(f['issue'] for f in fnd)}")
    (P / "panel_analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print("\n→ tests/data/phase2/panel_analysis.json")
    print("★ 本脚本不出合格判定: 禁止拿本批 L0/L0b 分位数给同一批 A 臂当阈值。")
