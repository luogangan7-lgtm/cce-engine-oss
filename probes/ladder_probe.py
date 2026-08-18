#!/usr/bin/env python3
"""温度阶梯到底加了什么？—— 阶梯 vs 同温重复采样的受控对照。

背景: s1 stage1 按设计跑 K 次不同温度([0.0,0.3,0.6,0.9,0.15])再取平均, 这是有意的展开。
但 P0-0 探针已证 **temperature=0.0 本身就不产生确定性**(同 prompt n=6 得 6 个不同输出)。
于是问题变成: 阶梯带来的离散, 相对「同温重复采样」的离散, 是不是多出来的?

若两者的 within_js 同量级 → 阶梯没有加可测的东西, 只是把端点噪声换了个名字,
   而它同时引入了一个不受控变量(每次采样的温度不同)。
若阶梯显著更大 → 它确实在展开语义模糊度, 应保留, 但必须与端点噪声分开记账。

本探针只测量, 不改生产。
"""
import json, os, statistics as st, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

LAYERS = ("desire_vec", "need_vec", "emotion_vec", "action_vec")
TEXT = Path(sys.argv[1]).read_text(encoding="utf-8").strip() if len(sys.argv) > 1 else None
CTX = "reddit r/HearingAids hearing_aid: 温度阶梯对照"
REPS = int(os.environ.get("LADDER_REPS", "3"))

ARMS = {"A 阶梯 [0,.3,.6,.9,.15]": [0.0, 0.3, 0.6, 0.9, 0.15],
        "B 同温 [0,0,0,0,0]": [0.0] * 5}


def run(temps):
    """复用 stage1，只把温度序列换掉。"""
    orig = K._base if hasattr(K, "_base") else None
    src = K.stage1.__code__
    # stage1 内部由 _base 切片得 temps；直接换不方便，改为复制其逻辑最小版本
    case = (f"平台/形态: {CTX}\n"
            f"以下是内容全文(仅文本, 无任何互动数据):\n\n{TEXT}\n\n"
            f"(注: 请对『写下这段内容的这一个人』反推其心理因果链四层占比分布。这是一个个体，不是群体。)")
    from concurrent.futures import ThreadPoolExecutor

    def one(T):
        for att in range(3):
            c, p, pv, m, ok = K.call_parse("M3", case, T, f"ladder_T{T}")
            if ok:
                return pv
        return None
    with ThreadPoolExecutor(max_workers=5) as ex:
        pvs = [p for p in ex.map(one, temps) if p]
    if len(pvs) < 2:
        return None
    avg = {L: [sum(p[L][j] for p in pvs) / len(pvs) for j in range(len(pvs[0][L]))] for L in LAYERS}
    within = {L: round(sum(K.js_divergence(pvs[i][L], pvs[j][L])
                           for i in range(len(pvs)) for j in range(i + 1, len(pvs)))
                       / (len(pvs) * (len(pvs) - 1) / 2), 4) for L in LAYERS}
    return {"n": len(pvs), "avg": avg, "within": within}


out = {}
for name, temps in ARMS.items():
    reps = []
    for r in range(REPS):
        t0 = time.time()
        res = run(temps)
        if res:
            reps.append(res)
            print(f"  {name}  rep{r+1}  n={res['n']}  {int(time.time()-t0)}s  within={res['within']}")
    out[name] = reps

print("\n═══ 臂内离散 within_js（同一次调用内 K 个样本之间）═══")
for name, reps in out.items():
    print(f"  {name}")
    for L in LAYERS:
        v = [r["within"][L] for r in reps]
        print(f"    {L:<12} {[f'{x:.3f}' for x in v]}  均值 {st.mean(v):.4f}")

print("\n═══ 臂间波动（同一臂重复 R 次，聚合后 layers 的差异）═══")
for name, reps in out.items():
    print(f"  {name}")
    for L in LAYERS:
        pair = [K.js_divergence(reps[i]["avg"][L], reps[j]["avg"][L])
                for i in range(len(reps)) for j in range(i + 1, len(reps))]
        print(f"    {L:<12} 两两 JS {[f'{x:.3f}' for x in pair]}  均值 {st.mean(pair):.4f}")

Path("/tmp/ladder_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
