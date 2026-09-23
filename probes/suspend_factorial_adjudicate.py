#!/usr/bin/env python3
"""析因挑战的判决 —— **判据在看到读数之前写完**。零 API。

预注册: tests/data/suspend_factorial_prereg.json (题集校验和 8a25dc3cb6db472d)
四条预测 F1~F4 逐条查表, 不改表。
"""
import json
import pathlib
import sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
RAW = VAULT / "cce_runs" / "suspend_factorial" / "raw.json"
PRE = ROOT / "tests/data/suspend_factorial_prereg.json"


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def fisher(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    return sum(comb(n1, i) * comb(n2, k - i) for i in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)


def main():
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    ok = [r for r in rows if r["top1"]]
    mm = [r for r in ok if not r["model"].startswith("glm")]
    gl = [r for r in ok if r["model"].startswith("glm")]
    res = {"block": "SUSPEND_FACTORIAL_RESULT", "★prereg": str(PRE.name),
           "n_readings": len(rows), "n_parsed": len(ok),
           "★synthetic_diagnostic": ("★★ 合成题。**不并入自然语料 n**, **不继承分辨力结论**; "
                                      "且造于看过 81 条结果**之后** ⇒ development, **非 confirmatory**。")}

    def rate(rs, pred):
        s = [r for r in rs if pred(r)]
        k = sum(1 for r in s if r["top1"] == "suspend")
        return k, len(s), (k / len(s) if s else None), wilson(k, len(s))

    for tag, rs in (("MiniMax五员", mm), ("GLM跨家族", gl)):
        cells = {}
        for c in ("P_Q", "P_noQ", "noP_Q", "noP_noQ"):
            k, n, p, w = rate(rs, lambda r, c=c: r["cell"] == c)
            cells[c] = {"suspend": f"{k}/{n}", "rate": round(p, 3) if p is not None else None, "wilson95": w}
        pk, pn, _, _ = rate(rs, lambda r: r["arm"] == "factorial" and r["pending"])
        nk, nn, _, _ = rate(rs, lambda r: r["arm"] == "factorial" and not r["pending"])
        f1p = fisher(pk, pn - pk, nk, nn - nk) if pn and nn else None
        negs = {}
        for c in sorted({r["cell"] for r in rs if r["arm"] == "negative"}):
            k, n, p, w = rate(rs, lambda r, c=c: r["cell"] == c)
            negs[c] = {"suspend": f"{k}/{n}", "rate": round(p, 3) if p is not None else None, "wilson95": w}
        d_q = (cells["P_Q"]["rate"] or 0) - (cells["P_noQ"]["rate"] or 0)
        res[tag] = {
            "cells": cells,
            "F1_悬置是必要的": {
                "有悬置": f"{pk}/{pn} = {pk/pn:.1%}" if pn else "n=0",
                "无悬置": f"{nk}/{nn} = {nk/nn:.1%}" if nn else "n=0",
                "fisher_p": round(f1p, 5) if f1p is not None else None,
                "verdict": ("PASS" if (f1p is not None and f1p < 0.05 and pk / max(pn, 1) > nk / max(nn, 1))
                            else ("★★代理线索越权" if nn and nk / nn > 0.3 else "UNRESOLVED")),
            },
            "F2_问句不该改变判定": {
                "P_Q - P_noQ": round(d_q, 3),
                "verdict": "PASS" if abs(d_q) <= 0.20 else "★★FAIL: 在读句式不是语义",
            },
            "F3_负例不许触发": {
                "per_group": negs,
                "verdict": ("PASS" if all((v["rate"] or 0) <= 0.20 for v in negs.values())
                            else "★★FAIL: " + str([c for c, v in negs.items() if (v["rate"] or 0) > 0.20])),
            },
        }
    mmv = res["MiniMax五员"]["F1_悬置是必要的"]["verdict"]
    glv = res["GLM跨家族"]["F1_悬置是必要的"]["verdict"]
    res["F4_跨家族同向"] = {"MiniMax": mmv, "GLM": glv,
                            "verdict": "PASS" if mmv == glv == "PASS" else
                            ("GLM 侧不可判(与它在 81 条上只判 1 条 suspend 一致)"
                             if all(v["rate"] == 0 for v in res["GLM跨家族"]["cells"].values())
                             else "方向不一致")}
    res["★no_disposition"] = "★★ 本轮**不改判别式、不合并、不删类**。结果只填四分法的第一格。"
    (ROOT / "tests/data/suspend_factorial_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for tag in ("MiniMax五员", "GLM跨家族"):
        r = res[tag]
        print(f"\n═══ {tag} ═══")
        for c, v in r["cells"].items():
            print(f"  {c:8s} suspend {v['suspend']:>6s} = {v['rate']} Wilson {v['wilson95']}")
        print(f"  F1 {r['F1_悬置是必要的']}")
        print(f"  F2 {r['F2_问句不该改变判定']}")
        print(f"  F3 {r['F3_负例不许触发']['verdict']}")
        for c, v in r["F3_负例不许触发"]["per_group"].items():
            print(f"       {c:16s} {v['suspend']} = {v['rate']}")
    print(f"\n★ F4 {res['F4_跨家族同向']}")


if __name__ == "__main__":
    main()
