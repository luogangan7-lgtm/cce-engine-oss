#!/usr/bin/env python3
"""闸材料候选 v3c 的判决 —— 判据在看到读数之前写完。零 API。

★★ R2 是**修法可能失败的方向**: 收紧必要条件最可能把**真悬置**也排掉。
★ JS **只作并列诊断, 不作判决** —— 它不能补偿语义失败。
"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RAW = V / "gate_dt_candidate" / "raw.json"
OLD = V / "suspend_fix_confirm" / "raw.json"
PRE = json.loads((ROOT / "tests/data/gate_decision_tree_candidate_prereg.json").read_text(encoding="utf-8"))
FAIL = ["已决定_延后执行", "历史悬置_现已决定"]
TRUE = ["★真悬置_必须仍判"]


def major(rows, arm, cells=None, key="top1"):
    """题级多数判 suspend 的题数 / 总题数。"""
    d = collections.defaultdict(list)
    for r in rows:
        if r.get("arm") == arm and r.get(key) and (cells is None or r["cell"] in cells):
            d[r["id"]].append(r[key] == "suspend")
    n = len(d)
    k = sum(1 for v in d.values() if sum(v) / len(v) > .5)
    return k, n


def rate(rows, arm, cells):
    s = [r for r in rows if r.get("arm") == arm and r["cell"] in cells and r.get("top1")]
    return (sum(1 for r in s if r["top1"] == "suspend"), len(s))


def main():
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    cells = sorted({r["cell"] for r in rows})
    res = {"block": "GATE_DT_CANDIDATE_RESULT",
           "★prereg": "tests/data/gate_decision_tree_candidate_prereg.json",
           "★★口径": "**候选筛选, 不是启用**。题目是**已暴露的开发/回归集**, 不是独立确认集。",
           "解析成功": f"{sum(1 for r in rows if r.get('top1'))}/{len(rows)}"}

    # R1 仅收藏
    a = rate(rows, "v2", ["仅收藏"]); b = rate(rows, "v3c", ["仅收藏"])
    ma = major(rows, "v2", ["仅收藏"]); mb = major(rows, "v3c", ["仅收藏"])
    res["★R1_仅收藏"] = {
        "读数级": f"v2 {a[0]}/{a[1]} → v3c {b[0]}/{b[1]}",
        "题级多数判": f"v2 {ma[0]}/{ma[1]} → v3c {mb[0]}/{mb[1]}",
        "verdict": ("PASS" if (b[1] and a[1] and b[0]/b[1] < a[0]/a[1] and mb[0] == 0)
                    else "★FAIL: 仅收藏没降下来, 或仍有题级多数判 suspend")}

    # R2 —— 修法可能失败的方向
    c1a, c1b = major(rows, "v2", FAIL), major(rows, "v3c", FAIL)
    ta, tb = rate(rows, "v2", TRUE), rate(rows, "v3c", TRUE)
    ra = ta[0]/ta[1] if ta[1] else 0; rb = tb[0]/tb[1] if tb[1] else 0
    res["★★R2_不许压掉真悬置与失败方向"] = {
        "C1 失败方向题级": f"v2 {c1a[0]}/{c1a[1]} → v3c {c1b[0]}/{c1b[1]}",
        "真悬置读数级": f"v2 {ta[0]}/{ta[1]}={ra:.2f} → v3c {tb[0]}/{tb[1]}={rb:.2f}",
        "verdict": ("PASS" if (c1b[0] <= c1a[0] and rb >= 0.70 and rb >= ra - 0.20)
                    else "★★★FAIL: **收紧必要条件把真悬置或失败方向弄坏了** ⇒ 退回候选, **不放宽判据**")}

    # R3 六个负例组完整报告
    neg = [c for c in cells if not any(r["should_be_suspend"] for r in rows if r["cell"] == c)]
    prof, worse = {}, []
    for c in cells:
        x, y = rate(rows, "v2", [c]), rate(rows, "v3c", [c])
        want = next(r["should_be_suspend"] for r in rows if r["cell"] == c)
        rx = x[0]/x[1] if x[1] else 0; ry = y[0]/y[1] if y[1] else 0
        bad = (ry > rx) if want is False else (ry < rx)
        prof[c] = {"应判suspend": want, "v2": f"{x[0]}/{x[1]}={rx:.0%}",
                   "v3c": f"{y[0]}/{y[1]}={ry:.0%}", "方向": "★变坏" if bad else "对/持平"}
        if bad:
            worse.append(c)
    res["★R3_全组剖面"] = {"逐组": prof, "负例组数": len(neg), "★变坏的组": worse,
                          "verdict": "PASS" if not worse else f"★FAIL: {worse} 变坏"}

    # R4 JS 并列诊断
    import itertools
    import math
    def js(p, q):
        ks = set(p) | set(q); m = {k: (p.get(k, 0)+q.get(k, 0))/2 for k in ks}
        kl = lambda z: sum(z.get(k, 0)*math.log2(z[k]/m[k]) for k in ks if z.get(k, 0) > 0)
        return (kl(p)+kl(q))/2
    jsv = {}
    for arm in ("v2", "v3c"):
        d = collections.defaultdict(dict)
        for r in rows:
            if r.get("arm") == arm and r.get("dist"):
                d[r["model"]][r["id"]] = r["dist"]
        vals = []
        for m1, m2 in itertools.combinations(sorted(d), 2):
            ids = [i for i in d[m1] if i in d[m2]]
            if ids:
                vals.append(sum(js(d[m1][i], d[m2][i]) for i in ids)/len(ids))
        jsv[arm] = round(sum(vals)/len(vals), 4) if vals else None
    res["★R4_一致性(并列诊断, **不作判决**)"] = {
        "mean_JS": jsv, "★注": "**JS 不能补偿语义失败** —— 它只是并列诊断。"}

    # R5 闸的运行间变动(顺带)
    try:
        old = json.loads(OLD.read_text(encoding="utf-8"))
        prev = {}
        for r in old:
            if r.get("arm") == "V1" and not r["model"].startswith("glm") and r.get("top1"):
                prev[(r["id"], r["model"])] = r["top1"]
        now = {(r["id"], r["model"]): r["top1"] for r in rows
               if r.get("arm") == "v2" and r.get("top1")}
        both = [k for k in now if k in prev]
        same = sum(1 for k in both if now[k] == prev[k])
        res["★R5_闸的运行间变动(顺带买到, 只报事实)"] = {
            "逐(题,模型)一致": f"{same}/{len(both)}",
            "★注": "**未事先定义允许翻转率 ⇒ 不签发闸的信度结论**。对照: 生产逐题翻转 3/22。"}
    except Exception as e:
        res["★R5_闸的运行间变动(顺带买到, 只报事实)"] = f"不可算: {e}"

    vs = [res["★R1_仅收藏"]["verdict"], res["★★R2_不许压掉真悬置与失败方向"]["verdict"],
          res["★R3_全组剖面"]["verdict"]]
    res["★★★overall"] = ("**候选通过筛选 —— 值得继续验证**(仍须走 GATE_PROTOCOL_CHANGE 全部义务才谈启用)"
                         if all(v == "PASS" for v in vs)
                         else "**候选未通过 ⇒ 退回, 不改现网, 不放宽判据**")
    res["★my_bet"] = {"赌的是": "R1 成立但 R2 紧张(真悬置可能掉到 0.8~0.9)", "信心": "中",
                      "★结果": "见 R2"}
    res["★★不能声称的"] = PRE["★★★what_this_run_cannot_claim"]
    (ROOT / "tests/data/gate_decision_tree_candidate_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "★★不能声称的"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
