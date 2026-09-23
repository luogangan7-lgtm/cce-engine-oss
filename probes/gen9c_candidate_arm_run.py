#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen9-C · 违例稳定性重复测量(**候选构造器臂**) —— 判据见 tests/data/gen9_violation_stability_prereg.json(测量前冻结)。

★ 走**真实生产路径** CK.stage1 / CK.stage2, 不改任何生产文件(只在本进程内包计数器)。
★ key 仅从 /Volumes/data/viral-skill-eval/.env 进程内加载, **不回显 · 不复制 · 不写仓 · 不写记忆**。
"""
import collections
import hashlib
import json
import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PREREG = json.loads((ROOT / "tests/data/gen9_violation_stability_prereg.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "gen9c_violation_stability"
CAP = PREREG["request_cap"]
_req = {"n": 0, "empty": 0}


def _load_key():
    p = pathlib.Path("/Volumes/data/viral-skill-eval/.env")
    if not p.exists():
        raise SystemExit("★ 找不到订阅凭据文件 —— **未发起任何调用**")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("MINIMAX_API_KEY"):
        raise SystemExit("★ 凭据文件里没有 MINIMAX_API_KEY —— **未发起任何调用**")


def _counting(orig, label):
    def w(*a, **kw):
        _req["n"] += 1
        if _req["n"] > CAP:
            raise RuntimeError("★★★ 撞请求上限 %d —— **立即停**, 不追加" % CAP)
        r = orig(*a, **kw)
        # ★ M3 陷阱: max_tokens 不足时静默返回空 content 且 status_code=0。
        #   空结果**不算成功** —— 台账 2026-07-30 记过, 开跑前已复现。
        txt = r[0] if isinstance(r, tuple) and r else r
        if isinstance(txt, str) and not txt.strip():
            _req["empty"] += 1
        return r
    return w


def main(cases_filter=None, n_override=None):
    assert PREREG["★★★status"].startswith("**READY**"), "★ 预注册未就绪, 不得发起"
    _load_key()
    import cce_knot_classify as CK

    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    ih = CK.instrument_id(taxo, k=3, knot_n=CK.KNOT_N,
                          s1_pairing="round_robin_over_3_s1_draws")["instrument_hash"]
    assert ih == "d4cce4c745f3f991", "★★★ 仪器不是预注册里那台(%s) —— 停" % ih

    A = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8"))["断言"]
    TXT = {a["用例"]: a["文本"] for a in A}
    cases = PREREG["arms"]["A_要判的"]["cases"] + PREREG["arms"]["B_退化对照"]["cases"]
    if cases_filter:
        cases = [c for c in cases if c in cases_filter]
    n = n_override or PREREG["n_per_case"]

    # ★★★ 候选臂: 只在本进程内替换 stage2 构造器 —— 与 gen8 逐字同一路径, 生产文件一字不动
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_stage2_candidate as V
    COMPONENTS = ("ontology", "discriminant", "negative", "full_behavior", "decision_tree")
    CK._build_stage2_prompt = lambda t, text, s1: V.build(t, text, s1, COMPONENTS)

    CK.call_parse = _counting(CK.call_parse, "s1")     # ★ 两条路径都要包 —— 只包一条账少一半
    CK.call_model = _counting(CK.call_model, "s2")

    OUT.mkdir(parents=True, exist_ok=True)
    rows, t0 = [], time.time()
    for ci, c in enumerate(cases, 1):
        text = TXT[c]
        for rep in range(n):
            r = {"case": c, "rep": rep, "sha8": hashlib.sha256(text.encode()).hexdigest()[:8]}
            t1 = time.time()
            try:
                s1 = CK.stage1(text, "reddit hearing discussion", 3)
                s2 = CK.stage2(text, s1, taxo)
                ks = s2.get("knots", [])
                r["top1"] = ks[0]["key"] if ks else None
                r["abstained"] = not ks
            except RuntimeError as e:
                if "撞请求上限" in str(e):
                    r["error"] = str(e); rows.append(r)
                    _dump(rows, t0, cases, n, aborted=True); raise
                r["error"] = "%s: %s" % (type(e).__name__, e); r["top1"] = None
            except Exception as e:
                r["error"] = "%s: %s" % (type(e).__name__, e)
                r["tb"] = traceback.format_exc()[-400:]
                r["top1"] = None
            r["sec"] = round(time.time() - t1, 1)
            rows.append(r)
            print("  [%2d/%d] %-26s rep%d top1=%-10s %4.1fs  累计请求 %d"
                  % (ci, len(cases), c, rep, r.get("top1"), r["sec"], _req["n"]), flush=True)
    _dump(rows, t0, cases, n)
    return rows


def _dump(rows, t0, cases, n, aborted=False):
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("top1"):
            by[r["case"]].append(r["top1"])
    per = {}
    for c, v in by.items():
        cnt = collections.Counter(v)
        mode, m = cnt.most_common(1)[0]
        per[c] = {"n_ok": len(v), "mode": mode, "mode_share": "%d/%d" % (m, len(v)),
                  "stable(>=7/8)": m >= 7 and len(v) >= 8, "dist": dict(cnt),
                  "saw_display": "display" in cnt}
    (OUT / "raw_draws.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                                         encoding="utf-8")
    (OUT / "per_case.json").write_text(json.dumps({
        "block": "GEN9C_PER_CASE(候选构造器臂)", "aborted": aborted,
        "★判据来自": "tests/data/gen9_violation_stability_prereg.json(测量前冻结)",
        "cases": cases, "n_per_case": n,
        "requests": _req["n"], "★空 content 次数(M3 静默失败)": _req["empty"],
        "wall_sec": round(time.time() - t0, 1), "per_case": per,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--n", type=int)
    a = ap.parse_args()
    main(a.only, a.n)
    print("\n请求 %d / cap %d · 空 content %d" % (_req["n"], CAP, _req["empty"]))
