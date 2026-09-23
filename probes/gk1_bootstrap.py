#!/usr/bin/env python3
"""G-K1 的自助置信区间 —— 「余量只有 0.55 个 SD」到底稳不稳。零 API。

## 为什么现在才能做
run1(2026-09-07 早)**没有落盘逐条原始标注** —— 430+ 次调用的原始数据丢了,
于是「想知道 JS 的置信区间」就得再花 430 次。当天修了落盘, run2 才有这份数据。

## ★★ 两个必须分开的问题(预注册 A1 vs A4)
· **A1/A2 抽样不确定性**: 对**条目**自助重采样 ⇒ 「换 81 条别的评论还过吗」
· **A4 模型不确定性**: run1 与 run2 的点估之差 ⇒ 「同一批条目重跑一次差多少」
★ 若跨运行差 **大于** 抽样 SE, 说明主要噪声来自模型而非样本 ⇒ **加样本量没用, 该加重复次数**。
  这两条路的成本差一个量级。

## ★★★ 面板成分不同, 不能直接比
run1 判 M2.7 落榜(3/5) ⇒ **4 人面板**; run2 判它合格(5/5) ⇒ **5 人面板**。
⇒ 本脚本对 run2 算**两套**: 5 人(如实跑的) 与 **限定到 run1 那 4 人**(可比子集)。
只有后者能与 run1 直接比。
"""
import itertools
import json
import math
import pathlib
import random
import statistics as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
RUN2 = VAULT / "cce_runs" / "run_a_repeat" / "raw_annotations.json"
RUN1 = ROOT / "accuracy" / "out" / "gates_result.json"
B = 10000
SEED = 20260907        # ★ 冻结: 自助的随机种子写死, 结果可复现


def js_div(p, q):
    ks = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in ks}
    kl = lambda a: sum(a.get(k, 0) * math.log2(a[k] / m[k]) for k in ks if a.get(k, 0) > 0 and m[k] > 0)
    return 0.5 * kl(p) + 0.5 * kl(q)


def metrics(dists, models, ids):
    """与 run_gates.py:412-424 逐字同口径: 对**两两对**取均值。"""
    t2s, jss = [], []
    for a, b in itertools.combinations(models, 2):
        use = [i for i in ids if dists[a].get(i) and dists[b].get(i)]
        if not use:
            continue
        ta = {i: max(dists[a][i], key=dists[a][i].get) for i in use}
        tb = {i: max(dists[b][i], key=dists[b][i].get) for i in use}
        p2a = {i: sorted(dists[a][i], key=dists[a][i].get, reverse=True)[:2] for i in use}
        p2b = {i: sorted(dists[b][i], key=dists[b][i].get, reverse=True)[:2] for i in use}
        t2s.append(sum(1 for i in use if ta[i] in p2b[i] or tb[i] in p2a[i]) / len(use))
        jss.append(sum(js_div(dists[a][i], dists[b][i]) for i in use) / len(use))
    return (sum(t2s) / len(t2s) if t2s else None, sum(jss) / len(jss) if jss else None)


def boot(dists, models, ids, b=B):
    rng = random.Random(SEED)
    n = len(ids)
    T, J = [], []
    for _ in range(b):
        s = [ids[rng.randrange(n)] for _ in range(n)]
        t, j = metrics(dists, models, s)
        if t is not None:
            T.append(t); J.append(j)
    q = lambda v, p: sorted(v)[max(0, min(len(v) - 1, int(p * len(v))))]
    return {"top2": {"lo": round(q(T, .025), 4), "hi": round(q(T, .975), 4), "se": round(st.pstdev(T), 4)},
            "JS":   {"lo": round(q(J, .025), 4), "hi": round(q(J, .975), 4), "se": round(st.pstdev(J), 4)}}


def main():
    raw = json.loads(RUN2.read_text(encoding="utf-8"))
    d, models5 = raw["dists"], raw["annotators"]
    g1 = json.loads(RUN1.read_text(encoding="utf-8"))["G_K1v2_分布一致性"]
    models4 = sorted(g1["annotator_mean_JS"])          # run1 实际入选的 4 人
    ids = sorted({i for m in models5 for i in d[m] if d[m][i]})

    out = {"block": "GK1_BOOTSTRAP_ON_RUN2", "B": B, "seed": SEED, "n_items": len(ids),
           "★run1_panel": models4, "★run2_panel": models5,
           "★panels_differ_because": (
             "★★ 资格考不可复现: run1 判 M2.7 3/5 落榜 ⇒ 4 人; run2 判它 5/5 合格 ⇒ 5 人。"
             "该闸在真实能力 p∈[0.34,0.93] 区间内基本是抽签(详见 tests/data/qualification_exam_resolution.json)。"
             "⇒ **只有「限定到 run1 那 4 人」的那一套能与 run1 直接比。**"),
           "thresholds": {"top2": ">=0.80", "JS": "<=0.25"}}

    for tag, ms in [("run2_5panel_as_run", models5), ("run2_restricted_to_run1_4panel", models4)]:
        t, j = metrics(d, ms, ids)
        bs = boot(d, ms, ids)
        out[tag] = {"panel": ms, "point": {"top2": round(t, 4), "JS": round(j, 4)},
                    "bootstrap_95CI": bs,
                    "★JS_CI_crosses_0.25": bs["JS"]["hi"] > 0.25,
                    "★top2_CI_crosses_0.80": bs["top2"]["lo"] < 0.80}

    r1t, r1j = g1["mean_top2_hit"], g1["mean_JS"]
    r2 = out["run2_restricted_to_run1_4panel"]
    dt, dj = abs(r2["point"]["top2"] - r1t), abs(r2["point"]["JS"] - r1j)
    se = r2["bootstrap_95CI"]
    out["★A4_run_to_run_vs_sampling"] = {
      "run1_point": {"top2": r1t, "JS": r1j}, "run2_point": r2["point"],
      "abs_diff": {"top2": round(dt, 4), "JS": round(dj, 4)},
      "bootstrap_SE": {"top2": se["top2"]["se"], "JS": se["JS"]["se"]},
      "diff_over_SE": {"top2": round(dt / se["top2"]["se"], 2), "JS": round(dj / se["JS"]["se"], 2)},
      "★reading": (
        "★ 比值 >1 ⇒ 跨运行(模型)噪声**大于**抽样噪声 ⇒ **加样本量没用, 该加重复次数**; "
        "<1 ⇒ 反之。这两条路的成本差一个量级。"),
    }
    (ROOT / "tests/data/gk1_bootstrap.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"n={len(ids)} 条 · B={B} · 种子 {SEED}")
    for tag in ("run2_5panel_as_run", "run2_restricted_to_run1_4panel"):
        o = out[tag]; b = o["bootstrap_95CI"]
        print(f"\n[{tag}] 面板 {len(o['panel'])} 人")
        print(f"  top2 点估 {o['point']['top2']:.4f}  95%CI [{b['top2']['lo']:.4f}, {b['top2']['hi']:.4f}] "
              f"SE {b['top2']['se']:.4f}  {'★下界跌破 0.80' if o['★top2_CI_crosses_0.80'] else '下界稳在 0.80 上'}")
        print(f"  JS   点估 {o['point']['JS']:.4f}  95%CI [{b['JS']['lo']:.4f}, {b['JS']['hi']:.4f}] "
              f"SE {b['JS']['se']:.4f}  {'★★上界越过 0.25' if o['★JS_CI_crosses_0.25'] else '上界仍在 0.25 内'}")
    a4 = out["★A4_run_to_run_vs_sampling"]
    print(f"\n[A4] run1 vs run2(同 4 人面板): top2 差 {a4['abs_diff']['top2']:.4f} = "
          f"{a4['diff_over_SE']['top2']}×SE · JS 差 {a4['abs_diff']['JS']:.4f} = {a4['diff_over_SE']['JS']}×SE")


if __name__ == "__main__":
    main()
