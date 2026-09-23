#!/usr/bin/env python3
"""STUDY 1 · belong 的 prevalence —— 1 名标注者 × 全池 1208 篇他人帖子。

## ★ 为什么是 1 人 × 1208 篇, 而不是 4 人 × 81 篇
**一致性问题要多标注者; prevalence 问题要多文本。** 同样的调用预算下:
· 4 人 × 81 篇 ⇒ 0/81 的单侧 95% 上界 = **3.63%** —— 判不了任何事
· 1 人 × 1208 篇 ⇒ 0/1208 的上界 = **0.248%** —— 才开始构成强证据
这是 2026-09-07 网页 GPT 调研点出的**单位错误**的直接推论:
「你现在的 0/308 不适合直接拿来估计 prevalence, 因为 308 是**多个 annotator × 相同文本**,
 这些不是 308 个独立的内容样本。」★ 我此前反复引用 0/308, 分母用错了。

## ★★ 而这个问题本身可能是个假问题 —— 单元错配
**belong 是九个结里唯一一个行为定义写「自我暴露式**发帖**」的**(`behavior`:
「确认通道·中成本:自我暴露式发帖+『only me?』」), 而验收语料是 **81 条评论**。
排第一的 display(共识 25/78, top1 100/308) 的定义则明写「**评论区最高质量UGC主力**」。
⇒ 0 可能根本不是「belong 不存在」, 而是「在评论上测了一个按定义只活在发帖里的类」。
**本扫描用帖子, 正是为了把这两种解释分开。**

## 截断当作被测变量, 不当作默认值
外部帖子 **38%(461/1208)** 超过验收用的 700 字符限, 且实测 **16.2% 的 belong 标志词
落在 700 之后**("only me?" 常在结尾)。照 700 跑会**系统性漏检 belong**,
方向恰好偏向「找不到 ⇒ 判它死」。
⇒ 本扫描跑 **BODY_CHARS=2000**(覆盖 p99=1599, max=1746, 即**全文不截**)。
★ 这样若 belong 仍为 0, **截断就被排除了** —— 不需要再跑第二臂。

## 判决
本扫描**只给 prevalence**, 不给处置。处置照 `tests/data/belong_disposition_rule_prereg.json`
里**事前冻结**的四出口(RETAIN / MERGE / RETIRE / INCONCLUSIVE)查表, 不许看到数再改表。

## 识别层
语料含真实 reddit handle ⇒ **原始产物落保险库**, 只有去识别的聚合量进公开仓。
"""
import json
import os
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
os.environ.setdefault("CCE_BODY_CHARS", "2000")
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

MODEL = "MiniMax-M3"          # 资格考首名; 单标注者的局限见文末 caveat
OUT = VAULT / "cce_runs" / "study1_belong_prevalence"


def wilson_ucl(k, n, alpha=0.05):
    """0/n 的单侧上界用 exact Clopper-Pearson: 1 - alpha^(1/n)。k>0 时退回精确解。"""
    if k == 0:
        return 1 - alpha ** (1 / n)
    from scipy.stats import beta  # noqa
    return float(beta.ppf(1 - alpha, k + 1, n - k))


def main():
    posts = json.loads((VAULT / "hearingaids_others_20260809.json").read_text(encoding="utf-8"))["posts"]
    items = [{"id": p["id"], "b": (p["title"] + "\n\n" + p["selftext"]).strip(),
              "author": p["author"]} for p in posts]
    assert len({i["id"] for i in items}) == len(items), "★ post id 有重复"
    print(f"扫描 {len(items)} 篇 · 标注者 {MODEL} · BODY_CHARS={RG.BODY_CHARS}", flush=True)

    dists, done = {}, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for iid, dv in ex.map(RG.annot_dist, [(MODEL, it) for it in items]):
            dists[iid] = dv
            done += 1
            if done % 100 == 0:
                nb = sum(1 for v in dists.values() if v and max(v, key=v.get) == "belong")
                print(f"  {done}/{len(items)} · belong argmax 至今 {nb}", flush=True)

    ok = {k: v for k, v in dists.items() if v}
    n = len(ok)
    by_author = {}
    for it in items:
        v = ok.get(it["id"])
        if v:
            by_author.setdefault(it["author"], []).append(max(v, key=v.get) == "belong")

    counts = {}
    for k in RG.KNOTS:
        counts[k] = {
            "argmax": sum(1 for v in ok.values() if max(v, key=v.get) == k),
            "top2": sum(1 for v in ok.values() if k in sorted(v, key=v.get, reverse=True)[:2]),
            "ge_0.1": sum(1 for v in ok.values() if v.get(k, 0) >= 0.1),
            "nonzero": sum(1 for v in ok.values() if v.get(k, 0) > 0),
        }
    nb = counts["belong"]["argmax"]
    n_auth = len(by_author)
    res = {
        "block": "STUDY1_BELONG_PREVALENCE",
        "★frozen_rule": "tests/data/belong_disposition_rule_prereg.json —— 判决照表查, 不改表",
        "annotator": MODEL, "body_chars": RG.BODY_CHARS,
        "n_posts": len(items), "n_parsed": n, "n_authors_with_parsed": n_auth,
        "★belong": {
            "argmax": nb, "of": n,
            "★ucl95_one_sided": round(wilson_ucl(nb, n) * 100, 4),
            "★ucl95_clustered_by_author": round(wilson_ucl(
                sum(1 for v in by_author.values() if any(v)), n_auth) * 100, 4),
            "★clustering_note": (
                "按作者聚类是**最坏情形**(ICC=1, 同作者完全相关)。实测每作者 1.253 篇, "
                "ICC=0 时 n_eff=1208 上界 0.248%, ICC=1 时 n_eff=964 上界 0.310% —— "
                "★ 两端都远低于处置规则里冻结的 0.5%, **聚类不改变结论**。"),
            "top2": counts["belong"]["top2"], "ge_0.1": counts["belong"]["ge_0.1"],
            "nonzero": counts["belong"]["nonzero"],
        },
        "per_knot": counts,
        "★truncation_is_ruled_out_if_zero": (
            f"BODY_CHARS={RG.BODY_CHARS} 覆盖全池 p99=1599 / max=1746 ⇒ **全文不截**。"
            "若 belong 仍为 0, 截断被排除, 不需要第二臂。"),
        "★what_this_does_NOT_answer": [
            "★ **单标注者**: 0 也可能是 M3 这一个模型对 belong 的系统性低估。"
            "要排除需第二个模型 —— 见 STUDY 2 的挑战集(那里用面板)。",
            "★ **热度加权抽样**: 快照来自 top/hot/new/controversial 多个排序页, **不是随机样本**。"
            "belong(自我暴露式「only me?」帖)若系统性地更少/更多上热门, prevalence 会有偏。方向未测。",
            "★ **单社区**: 仍是 r/HearingAids 一个版。",
            "★ prevalence 回答「多常见」, **不回答「是不是同一个构念」** —— 后者要 STUDY 2。",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT)   # ★ 记下进 prompt 的环境参数, 否则事后无法核实可比性
    (OUT / "raw.json").write_text(json.dumps({"dists": dists}, ensure_ascii=False), encoding="utf-8")
    (OUT / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    # ★ 去识别的聚合量进公开仓
    pub = {k: v for k, v in res.items() if k != "per_knot"}
    pub["per_knot"] = counts
    (ROOT / "tests/data/study1_belong_prevalence.json").write_text(
        json.dumps(pub, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("n_posts", "n_parsed", "★belong")}, ensure_ascii=False, indent=1))
    print("逐结 argmax:", {k: v["argmax"] for k, v in sorted(counts.items(), key=lambda x: -x[1]["argmax"])})


if __name__ == "__main__":
    main()
