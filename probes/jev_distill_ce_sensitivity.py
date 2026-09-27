# -*- coding: utf-8 -*-
"""★非预注册 · 测量后的敏感性分析(2026-09-28, 起因: 独立复核 wf_8a24ff4e-b04 的 P1)。不改任何冻结判决, 只量「判决对一个实现细节有多敏感」。

预注册写的是「留一平均交叉熵选 λ」; 冻结脚本 probes/jev_distill_vs_retest.py 的 ce() 里带一个 +1e-12 保护。X 族每折只有 36 条独热标签,
留一时常把某一类的唯一一条留出去: 那一折的训练集里该类不存在, 截距不受罚 ⇒ 没有有限最优解, 留出条的交叉熵(约 25–58 nats)取决于优化器停在哪、
以及有没有那个保护 —— 于是 λ 的选择、进而个别读出, 由实现细节决定。本探针做两件事:
  ① 数每个 (变体, 面, 折) 里「留一会留空某一类」的折数(独立于任何拟合, 只看 J1 标签与折分配);
  ② 把 ce() 换成不加保护的 −log P(唯一改动), 其余逐字调用冻结分析, 六个读者重跑, 与已提交的冻结结果逐格并列。
产物 results/jev_distill_ce_sensitivity.json: 只有计数、d、判决、λ; 无原文。零 API、零模型。
用法: python3 probes/jev_distill_ce_sensitivity.py <train_run_dir> <eval_run_dir>
"""
import collections, hashlib, importlib.util, json, pathlib, sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DISTILL = ROOT / "probes/jev_distill_vs_retest.py"
OUT = ROOT / "results/jev_distill_ce_sensitivity.json"
READERS = [f + v for f in "TX" for v in "ABC"]


def _load():
    s = importlib.util.spec_from_file_location("_distill_sens", DISTILL); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def singleton_folds(H, X_, pre):
    """(面, 折) → 该折 36 条训练标签里只出现一次的类数(= 留一时会留空一类的留出条数)。与变体无关(标签只来自 J1)。"""
    items = [json.loads(l) for l in H.EVAL_SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    order = [it for it in items if "text_ref" in it and not it["item_id"].startswith("rep-")]
    j1 = X_.load_arms()["J1"]
    out = {}
    for f in pre["★面"]["模型读"]:
        lab = [X_.RT.norm(j1[H._ptr(it["text_ref"])].get(f), X_.FACETS[f]) for it in order]
        per = []
        for k in range(H.N_FOLDS):
            c = collections.Counter(l for i, l in enumerate(lab) if i % H.N_FOLDS != k)
            per.append(sum(1 for v in c.values() if v == 1))
        out[f] = {"per_fold_singletons": per, "folds_with_singleton": sum(1 for v in per if v)}
    return out


def cells(doc, facets):
    return {f: {"d": [doc["per_facet"][f]["pairs"]["D~J1"]["d"], doc["per_facet"][f]["pairs"]["D~J2"]["d"]], "verdict": doc["verdicts"][f],
                "lambdas": doc["★头"][f]["lambdas"]} for f in facets} if doc.get("per_facet") else None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    H = _load()
    pre = json.loads(H.PRE.read_text(encoding="utf-8"))
    X_ = H.load_frozen(pre)
    facets = pre["★面"]["模型读"]
    H.ce = lambda P, Y: float(-(Y * np.log(P)).sum(axis=1).mean()) if (P > 0).all() else float("inf")   # 唯一改动: 去掉 +1e-12 保护
    rows = {}
    for t in READERS:
        frozen = json.loads(H.out_path(t).read_text(encoding="utf-8"))
        alt = H.analyse_reader(t[0], t[1], argv[0], argv[1], pre, X_)
        a, b = cells(frozen, facets), cells(alt, facets)
        rows[t] = {"frozen_overall": frozen["overall"], "unguarded_overall": alt["overall"], "unguarded_errors": alt["★前置错误"],
                   "facets": {f: {"frozen": a[f], "unguarded": b[f] if b else None,
                                  "changed": b is None or a[f]["d"] != b[f]["d"] or a[f]["verdict"] != b[f]["verdict"]} for f in facets}}
    doc = {"block": "JEV_DISTILL_CE_SENSITIVITY", "★性质": "非预注册, 测量后; 不改任何冻结判决; 只报告判决对 ce() 保护项这一实现细节的敏感度",
           "起因": "独立复核 wf_8a24ff4e-b04 (recompute) P1: X 族 λ 选择在「留一留空一类」的折上没有良定义的答案",
           "唯一改动": "ce(P, Y) = mean(−Σ Y·log P)(冻结版为 log(P + 1e-12)); 其余逐字调用 probes/jev_distill_vs_retest.analyse_reader",
           "distill_sha256": hashlib.sha256(DISTILL.read_bytes()).hexdigest(), "prereg_sha256": hashlib.sha256(H.PRE.read_bytes()).hexdigest(),
           "★X 族留一留空一类的折(按面, 7 折)": singleton_folds(H, X_, pre),
           "readers": rows,
           "changed_cells": sorted(f"{t}:{f}" for t, r in rows.items() for f, c in r["facets"].items() if c["changed"]),
           "any_replaceable_unguarded": sorted(f"{t}:{f}" for t, r in rows.items() for f, c in r["facets"].items() if c["unguarded"] and c["unguarded"]["verdict"] == "可替代")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("changed_cells", "any_replaceable_unguarded")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
