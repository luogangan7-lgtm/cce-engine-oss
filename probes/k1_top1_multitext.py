# -*- coding: utf-8 -*-
"""多文本 top-1 判定(零调用): 从已采集的 K1 raw draw 按**测量前冻结**的判据「top-1 一致 >= 7/8」逐文本判, 加非退化检验。

为什么有它(2026-09-29, 诊断 #2): 生产 k=3 仪器(reply/response)的 top-1「可用」此前只靠 v1 的**单文本**判定;
而同一台仪器上 K1-v2 早已采了 5 文本 × n=8 = 40 条 raw draw(tests/data/phase2/k1_v2_checkpoint.jsonl),
其预注册 criterion 本就含「top1 >= 7/8」(probes/k1_gate.judge 五项之一), 只是那次只判了 intensity/weight 两层。
k=5 仪器的 top-1 判定正是这样从 40 条 raw draw 零调用得出的(k1_top1_k5_verdict.json) —— 本脚本把同一做法落成可重跑的代码,
并用它**复现** k=5 那份已提交判定作自检。

用法: python3 probes/k1_top1_multitext.py k3      (写 tests/data/phase2/k1_top1_k3_verdict.json)
      python3 probes/k1_top1_multitext.py check   (只自检: 复现 k=5 的 per_text 与 verdict)
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "tests", "data", "phase2")


def judge(checkpoint, instrument_hash):
    rows = [json.loads(l) for l in open(os.path.join(P, checkpoint), encoding="utf-8") if l.strip()]
    assert rows and {r["instrument_hash"] for r in rows} == {instrument_hash}, "raw draw 不全在这台仪器上"
    assert all(r.get("qualified") for r in rows), "有不合格 draw —— 判据只对合格读数成立"
    by = collections.defaultdict(list)
    for r in rows:
        by[r["base_id"]].append(r["top1"])
    per_text = {}
    for b, tops in sorted(by.items()):
        mode, same = collections.Counter(tops).most_common(1)[0]
        per_text[b] = {"n": len(tops), "mode": mode, "same_as_mode": same, "pass": len(tops) >= 8 and same >= 7}
    modes = {v["mode"] for v in per_text.values()}
    ok = all(v["pass"] for v in per_text.values())
    return per_text, {"distinct_modes": len(modes), "pass": len(modes) >= 2,
                      "rule": "5 个文本的 top-1 众数至少要有 2 种取值 —— 恒返回同一个结也会满分"}, ok


def build_k3():
    per_text, degen, ok = judge("k1_v2_checkpoint.jsonl", "565470cf26c16d01")
    mt = json.load(open(os.path.join(P, "k1_v2_multitext_verdict.json"), encoding="utf-8"))
    ints = mt["layers"]["intensity"]
    top_ok = ok and degen["pass"]
    return {
        "block": "K1_TOP1_ON_K3_INSTRUMENT_MULTITEXT",
        "measured_at": "2026-09-03", "judged_at": "2026-09-29",
        "instrument_hash": "565470cf26c16d01",
        "prereg": "tests/data/phase2/k1_v2_multitext_prereg.json",
        "raw_rows": "tests/data/phase2/k1_v2_checkpoint.jsonl",
        "★source": "复用 K1_RELIABILITY_V2_MULTITEXT_GEN4 的 40 条 raw draw, **零新增调用**; 由 probes/k1_top1_multitext.py 现算",
        "★criterion_pre_exists": "「top-1 一致 >= 7/8」写在 k1_v2_multitext_prereg.json 的 criterion.per_text 里(probes/k1_gate.judge 五项之一, 测量前冻结); 那次只判了 intensity/weight 两层, top-1 这一项今天补判, 判据一字未改",
        "n": 8, "texts": len(per_text),
        "checks": [
            {"name": "n >= 8 (展示项)", "pass": all(v["n"] >= 8 for v in per_text.values()), "value": "8"},
            {"name": "top-1 一致 >= 7/8", "pass": top_ok,
             "value": f"{sum(v['pass'] for v in per_text.values())}/{len(per_text)} 文本达标; "
                      + ", ".join(f"{v['same_as_mode']}/{v['n']}" for v in per_text.values())
                      + f"; 非退化: {degen['distinct_modes']} 种众数"},
            {"name": "逐对容差一致 A(0.1) >= 0.95 (intensity, K1-v2 同批 5 文本)", "pass": False,
             "value": f"{ints['passed_texts']}/{ints['of']} 文本 (判定 {mt['decision']}, 见 k1_v2_multitext_verdict.json)"},
        ],
        "verdict": "TOP1_USABLE" if top_ok else "TOP1_FAIL",
        "per_text": per_text, "degeneracy": degen,
        "★replaces": "此前 k=3 的 top-1 路由到 k1_reliability_verdict.json(v1, **单文本**)。那份文件保留作历史; 路由改指本文件(5 文本 + 非退化)。",
        "★k5_for_comparison": {"instrument": "0e9ca1d4e7a2f180", "file": "tests/data/phase2/k1_top1_k5_verdict.json"},
    }


def check_k5():
    per_text, degen, ok = judge("k1_v2_k5_checkpoint.jsonl", "0e9ca1d4e7a2f180")
    k5 = json.load(open(os.path.join(P, "k1_top1_k5_verdict.json"), encoding="utf-8"))
    assert per_text == k5["per_text"], "★ 复现不了已提交的 k=5 per_text —— 本脚本与当时的判法不一致"
    assert degen["distinct_modes"] == k5["degeneracy"]["distinct_modes"] and (ok and degen["pass"]) == (k5["verdict"] == "TOP1_USABLE")
    return True


if __name__ == "__main__":
    check_k5()
    if sys.argv[1:] == ["k3"]:
        out = os.path.join(P, "k1_top1_k3_verdict.json")
        json.dump(build_k3(), open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("wrote", os.path.relpath(out, ROOT))
    print("k5 复现: OK")
