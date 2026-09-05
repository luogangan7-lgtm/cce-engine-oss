#!/usr/bin/env python3
"""派生量的可靠性 —— 0 次新增调用。

## 为什么要单独测
intensity 层被 K1 判为不达标。weight / mass / composition / drive_brake **都建在
intensity 上**, 直觉是「它们一样不可靠」。但那是**直觉不是测量**: 比值可能比
分子分母都稳(共模噪声抵消), 取 max 则可能更抖。所以先测再决定扣发范围。

数据: k1_rootcause 的 LIVE 臂, 取前 5 个 draw = **生产口径**(轮转 i%3, 前缀严格复现)。
判据: 与 K1 同一条 —— A(δ=0.10) >= 0.95(冻结于 f2b52ba)。

★ 本测量是 **exploratory**: experimental unit = 1 个文本, 零复现。
  它**不构成**任何量的正式判定, 只用来说明「不能凭『是派生量』直接断言」。
  生产路由按「未单独判定 ⇒ 扣发」处理, 不按这里的数放行。
"""
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))
from cce_knot_classify import _has_support, derived_layers  # noqa: E402
from k1_gate import CRIT  # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
DELTA, AMIN = CRIT["tolerance_delta"], CRIT["agreement_min"]
N_DRAW = 5   # 生产口径


def rep_layers(rep, taxo):
    draws = rep[:N_DRAW]
    stability, keys = {}, set()
    for k in draws[0]["knot_vector"]:
        ws = [d["knot_vector"][k] for d in draws]
        nz = [w for w in ws if w > 0]
        if nz:
            keys.add(k)
        stability[k] = {"occur": len(nz), "n": len(draws),
                        "intensity": round(statistics.median(nz), 4) if nz else 0.0}
    fam, _ = derived_layers(stability, keys, taxo)
    tot = sum(stability[k]["intensity"] for k in keys if _has_support(stability[k])) or 1.0
    dm, bm = fam["推动"]["mass"], fam["阻挡"]["mass"]
    return {
        "intensity": {k: stability[k]["intensity"] for k in keys if _has_support(stability[k])},
        "weight": {k: round(stability[k]["intensity"] / tot, 4)
                   for k in keys if _has_support(stability[k])},
        "mass": {f: fam[f]["mass"] for f in fam},
        "composition": {f: fam[f]["composition"] for f in fam},
        "quadrant": f"{'high' if dm >= 0.5 else 'low'}_drive/"
                    f"{'high' if bm >= 0.5 else 'low'}_brake",
    }


def agree(vals):
    """逐对容差一致率 + **非退化标记**。返回 (rate, n, degenerate)。

    ★★ 2026-09-06 补: 此前只返回 (rate, n), **没有非退化闸** —— 一个**常数估计器**
       (永远吐同一个数)会拿满分 1.000, 而它零判别力。
       ⇒ 违反本项目铁律「**恒定值 + 零方差 ⇒ 先查仪器, 不当结论**」。

    ★ 而讽刺的是: **同一个文件的 quadrant 那条路径早就有这个闸**
      (`degenerate = len(set(q)) == 1` + 「零方差, 不是信度证据」的注记)。
      同一位作者、同一个函数体里, 纪律只落实了一半 ——
      这正是「知道规则」与「规则被执行」之间的那道缝。

    degenerate=True 时 rate **不得当作可靠性证据**: 一致率高可以来自真稳定,
    也可以来自估计器根本不动, 两者**从 rate 上不可区分**。
    """
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return None, len(v), None
    pr = list(itertools.combinations(v, 2))
    rate = sum(1 for a, b in pr if abs(a - b) <= DELTA) / len(pr)
    return rate, len(v), len(set(v)) == 1


def main() -> int:
    taxo = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in
            (P / "k1_rootcause_checkpoint.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    reps = [[d for d in r["ledger"] if not d.get("infra") and d.get("knot_vector")]
            for r in rows if r["arm"] == "LIVE" and r.get("ledger")]
    for r in reps:
        assert all(d["prompt_idx"] == d["draw_id"] % 3 for d in r), "轮转不是 i%3, 前缀无效"
    L = [rep_layers(r, taxo) for r in reps]
    m, need = len(L), len(L) * 7 // 8
    out = {}
    degenerate_quantities = []   # ★ 零方差的量 —— 它们的 A 值不是信度证据
    print(f"生产口径 n={N_DRAW} draw · {m} rep · A(δ={DELTA}) >= {AMIN} 才算达标\n")
    print(f"  {'量':<32} {'A':>7} {'可评估':>7}")
    for fam_key, getter in (("intensity", lambda x, k: x["intensity"].get(k)),
                            ("weight", lambda x, k: x["weight"].get(k))):
        for k in sorted({kk for x in L for kk in x[fam_key]}):
            a, c, deg = agree([getter(x, k) for x in L])
            if a is not None and c >= need:
                out[f"{fam_key}.{k}"] = round(a, 4)
                if deg:
                    degenerate_quantities.append(f"{fam_key}.{k}")
                print(f"  {fam_key + '.' + k:<32} {a:>7.3f} {c:>7}"
                      f"   {'⚠️ 零方差, 不是信度证据' if deg else ''}")
    for f in ("推动", "阻挡"):
        a, c, deg = agree([x["mass"][f] for x in L])
        out[f"mass.{f}"] = round(a, 4)
        if deg:
            degenerate_quantities.append(f"mass.{f}")
        print(f"  {'mass.' + f:<32} {a:>7.3f} {c:>7}"
              f"   {'⚠️ 零方差, 不是信度证据' if deg else ''}")
        for k in sorted({kk for x in L for kk in x["composition"][f]}):
            a2, c2, deg2 = agree([x["composition"][f].get(k) for x in L])
            if a2 is not None and c2 >= need:
                out[f"composition.{f}.{k}"] = round(a2, 4)
                if deg2:
                    degenerate_quantities.append(f"composition.{f}.{k}")
                print(f"  {'composition.' + f + '.' + k:<32} {a2:>7.3f} {c2:>7}"
                      f"   {'⚠️ 零方差, 不是信度证据' if deg2 else ''}")
    q = [x["quadrant"] for x in L]
    qa = max(q.count(t) for t in set(q)) / m
    degenerate = len(set(q)) == 1
    print(f"  {'drive_brake.quadrant(同值率)':<32} {qa:>7.3f} {m:>7}"
          f"   {'⚠️ 零方差, 不是信度证据' if degenerate else ''}")

    (P / "derived_layer_reliability.json").write_text(json.dumps({
        "block": "DERIVED_LAYER_RELIABILITY", "measured_at": "2026-09-02",
        "new_calls": 0, "n_draw": N_DRAW, "n_rep": m,
        "delta": DELTA, "agreement_min": AMIN,
        "source": "tests/data/phase2/k1_rootcause_checkpoint.jsonl (LIVE 臂, 前 5 draw)",
        "per_quantity": out,
        # ★ 2026-09-06: 零方差的量必须**具名列出**。它们的 A 值在 per_quantity 里看起来
        #   和真稳定的量一模一样 —— 不列出来, 读者无从分辨。
        "★degenerate_quantities": sorted(degenerate_quantities),
        "★why_degenerate_matters": ("零方差 ⇒ 一致率必然 1.000, 但那是「估计器不动」而非"
                                    "「它测得准」。两者从 A 值上**不可区分**, 故必须单独标。"
                                    "此前本探针只给 quadrant 加了这个闸, agree() 覆盖的"
                                    "intensity/weight/mass/composition 全都没有。"),
        "quadrant": {"agreement": round(qa, 4), "values": sorted(set(q)),
                     "degenerate": degenerate,
                     "★note": ("10 个 rep 全是同一个值 ⇒ **零方差, 不是信度证据**。"
                               "一个从不变化的分类标签说明不了它的分辨力 —— "
                               "与此前踩过的退化估计量同一个坑。")},
        "★finding": ("**推翻了「派生量一律继承 intensity 的不可靠」这个直觉**: "
                     "weight 反而比 intensity 更稳(归一化抵消共模噪声), mass 更差(取 max 更抖)。"),
        "★status": ("**exploratory** —— experimental unit = 1 个文本, 零复现。"
                    "不构成任何量的正式判定。生产路由按「未单独判定 ⇒ 扣发」处理, "
                    "**不按这里的数放行**。"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n产物: tests/data/phase2/derived_layer_reliability.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
