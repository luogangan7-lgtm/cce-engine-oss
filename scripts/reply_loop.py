#!/usr/bin/env python3
"""回复闭环 — 对方分布当基准, 写完回过来验是否触达, 不达则退回重写。

reply 模式原链路 s1..s4 只解析对方, 写完就发, 没有对齐验证——本文件补上缺的后半截。

  A侧 = 对方原文   → 四层分布 + 九结分布   (写作基准)
  B侧 = 我的草稿   → 四层分布 + 九结分布
  对齐 = 九结分族算子(cce_align_v2, 推动族求共鸣/阻挡族求拆除)
       + 四层加权重叠(逐维报缺口, 让"没触达哪一维"可指认)

用法: reply_loop.py --reader reader.txt --draft draft.txt --context "..." --out out.json
"""
import os, sys, json, argparse, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from exp_crossmodel_desire import DESIRES
from exp_v4_causal_chain import EMOTIONS, ACTIONS
from cce_align_v2 import score as knot_align

NEEDS = json.load(open(os.path.join(ROOT, "config/need_taxonomy.json"), encoding="utf-8"))["controlled_keys"]
LAYERS = {"desire_vec": DESIRES, "need_vec": NEEDS, "emotion_vec": EMOTIONS, "action_vec": ACTIONS}
# 触达门槛: 对方该维占比 >= 该值才算"必须回应的维度"
SALIENT = float(os.environ.get("REPLY_SALIENT", "0.15"))
# 我方在某维的占比 >= 对方占比 x 该系数, 才算触达该维
REACH = float(os.environ.get("REPLY_REACH", "0.5"))


def readout(text, context, k, tag, outdir):
    """跑 s1(四层读数)+s2(九结), 复用生产同一脚本, 不另起实现"""
    tf = os.path.join(outdir, f"{tag}.txt")
    open(tf, "w", encoding="utf-8").write(text)
    out = os.path.join(outdir, f"{tag}_readout.json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/cce_knot_classify.py"),
                        "--text-file", tf, "--context", context, "--k", str(k), "--out", out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=ROOT, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"{tag} readout rc={r.returncode}: {(r.stderr or '')[-300:]}")
    return json.load(open(out, encoding="utf-8"))


def norm(v):
    t = sum(v)
    return [x / t for x in v] if t > 0 else v


def layer_reach(a_vec, b_vec, labels):
    """逐维: 对方显著的维度, 我方有没有跟上"""
    A, B = norm(a_vec), norm(b_vec)
    rows = []
    for lab, pa, pb in zip(labels, A, B):
        if pa < SALIENT:
            continue
        rows.append({"dim": lab, "对方": round(pa, 3), "我方": round(pb, 3),
                     "触达": bool(pb >= pa * REACH),
                     "缺口": round(max(0.0, pa * REACH - pb), 3)})
    hit = sum(1 for r in rows if r["触达"])
    return {"显著维": len(rows), "触达数": hit,
            "触达率": round(hit / len(rows), 3) if rows else None, "逐维": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=3)
    A = ap.parse_args()
    outdir = os.path.dirname(os.path.abspath(A.out)) or "."
    os.makedirs(outdir, exist_ok=True)
    reader = open(A.reader, encoding="utf-8").read().strip()
    draft = open(A.draft, encoding="utf-8").read().strip()

    # 两侧读数互不依赖(b 不用 a 的任何结果), 并行跑。
    # 2026-08-15 实测串行代价: run 31890090368 item0 的对齐闸 486s 里 389s 是 B 在等 A。
    # 各自写 {tag}.txt / {tag}_readout.json, 文件名不冲突。
    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(readout, reader, A.context + "(对方原文/写作基准侧)", A.k, "A_reader", outdir)
        fb = ex.submit(readout, draft, A.context + "(我方草稿/待验证侧)", A.k, "B_draft", outdir)
        a, b = fa.result(), fb.result()

    a_knots = {x["key"]: x["weight"] for x in a["stage2"]["knots"]}
    b_knots = {x["key"]: x["weight"] for x in b["stage2"]["knots"]}
    ka = knot_align(a_knots, b_knots, draft, mode="reply")

    layers = {L: layer_reach(a["stage1"]["layers"][L], b["stage1"]["layers"][L], lab)
              for L, lab in LAYERS.items()}

    misses = [r["dim"] for L in layers.values() for r in L["逐维"] if not r["触达"]]
    need_ok = (layers["need_vec"]["触达率"] or 0) >= 0.5
    # 2026-08-18: 补 top1_stable 守卫。此前不确定性只在 cce_full_run.py 的 s2 段生效
    # (top1 不稳时扣发 playbook_primary), 而这里照旧拿被抖动过的 weight 算出 PASS/FAIL ——
    # 同一份不可靠读数, 一条路上被扣住、另一条路上照发判决。爆炸半径不一致本身就是缺陷。
    _unstable = [x.get("stage2", {}).get("sampling", {}).get("top1_stable") is False
                 for x in (a, b) if isinstance(x, dict)]
    knot_ok = ka["alignment_score"] >= float(os.environ.get("CCE_ALIGN_THETA", "0.35"))
    if any(_unstable):
        # 不判 FAIL —— 判「不可判」。首结不稳时这个分数本身没有可解释性,
        # 强行给 PASS 或 FAIL 都是把噪声当结论。
        knot_ok = None
    verdict = {
        "对方九结": a_knots, "我方九结": b_knots,
        "九结对齐": ka,
        "四层触达": layers,
        "未触达维度": misses,
        "判据": "need层触达率>=0.5 且 九结对齐分>=theta",
        "need_ok": need_ok, "knot_ok": knot_ok,
        "PASS": bool(need_ok and knot_ok),
        "改写指令": ([] if (need_ok and knot_ok) else
                   [f"补上未触达维度: {', '.join(misses)}" ] if misses else
                   ["九结对齐不足: 我方结分布未响应对方主结, 检查是否答非所问"]),
    }
    json.dump({"reader_readout": a, "draft_readout": b, "verdict": verdict},
              open(A.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(verdict, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
