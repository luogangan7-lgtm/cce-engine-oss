#!/usr/bin/env python3
"""回复/评论批量两阶段跑法 —— reply.yml 一次只吃一条, 12 条要 dispatch 12 次, 不可行。

  phase A  只读对方 → 四层分布 + 九结分布 = 写作基准。写稿前必须先拿到它,
           否则就是"先写完再补一个 CCE 章"(2026-08-09 用户点名过这个问题)。
  phase B  投入草稿 → 复用 reply_loop 的对齐算子出触达率/改写指令 + 文风闸。

两阶段分开是刻意的: 中间那一步(照分布写稿)由人/模型在链外做, 链只负责给基准和验收,
不负责生成。生成侧消融(2026-08-10, n=29)已证分类学喂给"诊断"有效(B3vsA 82.8%),
喂给"改写"无独立增量(B4vsB3 57.1% n.s.), 所以这里只把诊断结论交出去。

用法:
  reply_batch.py --items run_items/x.json --phase A --out out/
  reply_batch.py --items run_items/x.json --phase B --out out/
"""
import os, sys, json, argparse, traceback
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from reply_loop import readout, layer_reach, LAYERS, norm  # noqa: E402
from cce_align_v2 import score as knot_align               # noqa: E402

# 并发度: MiniMax 侧限流, 实测 3 路稳定; 调高会出 429 把整批拖垮
WORKERS = int(os.environ.get("REPLY_BATCH_WORKERS", "3"))


def top_dims(vec, labels, floor=0.10):
    z = norm(vec)
    r = sorted(zip(labels, z), key=lambda x: -x[1])
    return [[l, round(p, 3)] for l, p in r if p >= floor]


def phase_a(it, outdir):
    a = readout(it["reader"], it["context"] + "(对方原文/写作基准侧)", 3,
                "A_" + it["tag"], outdir)
    knots = {x["key"]: x["weight"] for x in a["stage2"]["knots"]}
    return {"tag": it["tag"], "url": it["url"], "kind": it["kind"],
            "九结": knots,
            "打法": a["stage2"].get("playbook_primary") or a["stage2"].get("playbook"),
            "四层": {L: top_dims(a["stage1"]["layers"][L], lab) for L, lab in LAYERS.items()}}


def phase_b(it, outdir):
    draft = (it.get("draft") or "").strip()
    if not draft:
        return {"tag": it["tag"], "skip": "无草稿"}
    a = readout(it["reader"], it["context"] + "(对方原文/写作基准侧)", 3, "A_" + it["tag"], outdir)
    b = readout(draft, it["context"] + "(我方草稿/待验证侧)", 3, "B_" + it["tag"], outdir)
    ak = {x["key"]: x["weight"] for x in a["stage2"]["knots"]}
    bk = {x["key"]: x["weight"] for x in b["stage2"]["knots"]}
    ka = knot_align(ak, bk, draft, mode="reply")
    layers = {L: layer_reach(a["stage1"]["layers"][L], b["stage1"]["layers"][L], lab)
              for L, lab in LAYERS.items()}
    misses = [r["dim"] for L in layers.values() for r in L["逐维"] if not r["触达"]]
    need_ok = (layers["need_vec"]["触达率"] or 0) >= 0.5
    knot_ok = ka["alignment_score"] >= float(os.environ.get("CCE_ALIGN_THETA", "0.35"))
    return {"tag": it["tag"], "url": it["url"], "words": len(draft.split()),
            "对方九结": ak, "我方九结": bk,
            "对齐分": ka["alignment_score"], "共鸣": ka.get("resonance"), "拆除": ka.get("dissolution"),
            "四层触达": {L: {"显著维": v["显著维"], "触达数": v["触达数"], "触达率": v["触达率"]}
                       for L, v in layers.items()},
            "逐维缺口": [r for L in layers.values() for r in L["逐维"] if not r["触达"]],
            "未触达": misses, "need_ok": need_ok, "knot_ok": knot_ok,
            "PASS": bool(need_ok and knot_ok),
            "改写指令": ([] if (need_ok and knot_ok)
                       else [f"补上未触达维度: {', '.join(misses)}"] if misses
                       else ["九结对齐不足: 我方结分布未响应对方主结, 检查是否答非所问"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--phase", required=True, choices=["A", "B"])
    ap.add_argument("--out", default="out")
    A = ap.parse_args()
    os.makedirs(A.out, exist_ok=True)
    items = json.load(open(A.items, encoding="utf-8"))
    fn = phase_a if A.phase == "A" else phase_b

    def run(it):
        try:
            return fn(it, A.out)
        except Exception as e:
            traceback.print_exc()
            return {"tag": it["tag"], "ERROR": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(WORKERS) as ex:
        res = list(ex.map(run, items))
    p = os.path.join(A.out, f"phase{A.phase}.json")
    json.dump(res, open(p, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    bad = [r for r in res if r.get("ERROR")]
    print(f"\n=== phase {A.phase}: {len(res)} 条, 失败 {len(bad)} ===")
    # 失败不静默: 有一条炸就非零退出, 免得半批结果被当成全批
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
