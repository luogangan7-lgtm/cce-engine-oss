#!/usr/bin/env python3
"""把本次 G-K 结果与冻结基线对比, 输出 markdown 报告到 stdout。
基线: accuracy/data/baseline_v5_taxo_1.1.1.json (taxonomy v1.1.1 时的通过态)
"""
import json, os, glob

A = os.path.dirname(os.path.abspath(__file__))
cur_p = os.path.join(A, "out", "gates_result.json")
base_p = os.path.join(A, "data", "baseline_v5_taxo_1.1.1.json")
taxo = json.load(open(os.path.join(os.path.dirname(A), "config", "knot_taxonomy.json"), encoding="utf-8"))

print(f"## CCE 准确度回归 · taxonomy v{taxo['version']}\n")
if not os.path.exists(cur_p):
    print("**本次未产出结果**(gate 脚本失败, 见上一步日志)")
    raise SystemExit

cur = json.load(open(cur_p, encoding="utf-8"))
base = json.load(open(base_p, encoding="utf-8"))


def pull(d):
    """抽出可比的核心指标"""
    out = {}
    g1 = d.get("G_K1v2_分布一致性", {}).get("pairwise", {})
    if g1:
        ks = [v.get("top1_kappa") for v in g1.values() if v.get("top1_kappa") is not None]
        t2 = [v.get("top2_hit") for v in g1.values() if v.get("top2_hit") is not None]
        js = [v.get("mean_JS") for v in g1.values() if v.get("mean_JS") is not None]
        if ks: out["G-K1 平均top1κ"] = round(sum(ks) / len(ks), 3)
        if t2: out["G-K1 平均top2命中"] = round(sum(t2) / len(t2), 3)
        if js: out["G-K1 平均JS距离"] = round(sum(js) / len(js), 3)
    g2 = d.get("G_K2v2_成本档预测", {})
    for k, label in (("exact_acc", "G-K2 精确档命中"), ("within_1_tier", "G-K2 相邻档内"),
                     ("lift_vs_baseline", "G-K2 相对多数基线增益")):
        if g2.get(k) is not None: out[label] = g2[k]
    out["overall_pass"] = d.get("overall_pass")
    return out


c, b = pull(cur), pull(base)
print(f"基线: `{base.get('gate','?')}`  样本 n={base.get('sample_n')}")
print(f"本次: 样本 n={cur.get('sample_n')}\n")
print("| 指标 | 基线 | 本次 | 变化 |")
print("|---|---|---|---|")
for k in dict.fromkeys(list(b) + list(c)):
    bv, cv = b.get(k), c.get(k)
    if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
        d_ = cv - bv
        # JS 距离越低越好, 其余指标越高越好 — 方向不能一刀切(v1首跑时这里报反了)
        better = (d_ < -0.001) if "JS" in k else (d_ > 0.001)
        worse = (d_ > 0.001) if "JS" in k else (d_ < -0.001)
        arrow = "🟢 " if better else ("🔴 " if worse else "⚪ ")
        print(f"| {k} | {bv} | {cv} | {arrow}{d_:+.3f} |")
    else:
        print(f"| {k} | {bv} | {cv} | |")

conf = cur.get("混淆诊断", {}).get("top_confusion_pairs")
if conf:
    print(f"\n**主要混淆对**: " + ", ".join(f"`{k}`×{v}" for k, v in list(conf.items())[:5]))
print("\n> 判读: κ 与 top2命中 升高 = 分类学更可复现; JS距离 降低 = 标注者分布更一致。"
      "任一指标显著下降说明本次改动伤了准确度, 应回滚。")
