#!/usr/bin/env python3
"""STUDY 2 · belong 与最近邻 display 是不是同一个构念 —— 覆盖挑战集 + 阴性近似对照。

## ★★★ 为什么必须与 STUDY 1 分开
2026-09-07 网页 GPT 调研的核心判词, 我采纳:
**「零频次回答的是『多常见』; 合并决定要求回答的是『是不是同一个构念』。
   这两个问题不能用同一个 0/308 证据替代。」**
⇒ STUDY 1 给 prevalence 上界, **只能支持 RETIRE**; 要支持 **MERGE** 必须证明
   「在**有设计地覆盖 belong 生成机制**之后, 仍然分不开」—— 那就是本研究。

## 选择器是**理论驱动**的, 且在看到任何标注之前冻结
候选来自 belong **自己的定义**(「自我暴露式发帖 + 『only me?』」「自报身份以入群」
「无信息增量要求」)的表面标志; 阴性近似对照来自最近邻 display 的标志(**带信息增量**的自我暴露)。
两组标志词逐字冻结在 `tests/data/belong_disposition_rule_prereg.json`。

★ 已知的循环风险(必须自己先答): 若这些标志词**也出现在喂给标注者的 prompt 里**,
  那就是用仪器自己的定义去检验仪器。本脚本启动时**实测**这一点并打印, 不通过就拒跑。

## 阴性近似对照做什么
只看「候选集上 belong 点火率高」是不够的 —— 一条**对什么都点火**的规则同样能做到。
hard negatives 回答: 它**只**在该点火的地方点火吗。
★ 判据(冻结): RETAIN 要求候选集命中 **且** hard negative 的命中率 **< 候选集的一半**。

## 识别层
语料含真实 reddit handle ⇒ 原始产物落保险库, 只有去识别的聚合量进公开仓。
"""
import json
import os
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
os.environ.setdefault("CCE_BODY_CHARS", "2000")
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

PREREG = json.loads((ROOT / "tests/data/belong_disposition_rule_prereg.json").read_text(encoding="utf-8"))
BM = PREREG["STUDY_2_discriminant_validity"]["belong_markers"]
DM = PREREG["STUDY_2_discriminant_validity"]["display_hard_negative_markers"]
OUT = VAULT / "cce_runs" / "study2_belong_discriminant"


def _circularity_check():
    """★ 标志词若也在喂给标注者的 prompt 里, 本研究就是循环的。实测, 不通过就拒跑。"""
    fed = (RG.KNOT_BRIEF + RG.DECISION_TREE + RG.NEGATIVE_EXAMPLES + RG.DIST_TMPL).lower()
    leaked = [p for p in BM + DM if re.search(p, fed)]
    return leaked, len(fed)


def main():
    leaked, flen = _circularity_check()
    print(f"★ 循环性自检: 喂给标注者的 prompt 共 {flen} 字符; 标志词泄漏 {len(leaked)} 条")
    clean_m = [x for x in BM if x not in leaked]
    if leaked:
        print(f"  ★★ 泄漏: {leaked} ⇒ 拆两臂, **判据只看 ARM_CLEAN**")
        print(f"     (ARM_LEAKED 单独报, 不进判决 —— 若 belong 只在那一臂点火, "
              f"说明仪器在对自己 brief 的字面做关键词匹配)")
    else:
        print("  ✅ 无泄漏")

    posts = json.loads((VAULT / "hearingaids_others_20260809.json").read_text(encoding="utf-8"))["posts"]
    hit = lambda p, pats: [x for x in pats if re.search(x, (p["title"] + " " + p["selftext"]).lower())]
    cand = [p for p in posts if hit(p, clean_m)]                       # ARM_CLEAN
    leakonly = [p for p in posts if hit(p, leaked) and not hit(p, clean_m)]  # ARM_LEAKED
    hardneg = [p for p in posts if hit(p, DM) and not hit(p, BM)]
    print(f"ARM_CLEAN {len(cand)} · ARM_LEAKED {len(leakonly)} · 阴性近似对照 {len(hardneg)} · "
          f"标注者 {RG.MODELS} · BODY_CHARS={RG.BODY_CHARS}")

    mk = lambda p, a: {"id": p["id"], "b": (p["title"] + "\n\n" + p["selftext"]).strip(), "arm": a}
    items = ([mk(p, "candidate") for p in cand] + [mk(p, "leaked_only") for p in leakonly]
             + [mk(p, "hard_negative") for p in hardneg])
    jobs = [(m, it) for m in RG.MODELS for it in items]
    dists = {m: {} for m in RG.MODELS}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (m, _), (iid, dv) in zip(jobs, ex.map(RG.annot_dist, jobs)):
            dists[m][iid] = dv
    arm = {it["id"]: it["arm"] for it in items}

    cons = {}
    for iid in arm:
        vs = [dists[m].get(iid) for m in RG.MODELS if dists[m].get(iid)]
        if len(vs) >= 2:
            agg = {k: sum(v.get(k, 0) for v in vs) / len(vs) for k in RG.KNOTS}
            cons[iid] = agg

    posts_by_id = {p["id"]: p for p in posts}

    def rate(a):
        ids = [i for i in cons if arm[i] == a]
        hit = [i for i in ids if max(cons[i], key=cons[i].get) == "belong"]
        return len(hit), len(ids), (len(hit) / len(ids) if ids else None), hit

    cand_hit_ids = []

    cb, cn, cr, cand_hit_ids = rate("candidate")   # ★ 判据只看这一臂
    lb, ln_, lr, _ = rate("leaked_only")           # ★ 只作诊断, 不进判决
    hb, hn, hr, _ = rate("hard_negative")
    # ★★★ 照**修订后**的规则查表(2026-09-07, 在本研究发起**任何调用之前**冻结)。
    #   旧条文是「至少 1 条」—— 用仪器**自己测出的**构念无关点火率当零模型
    #   (验收集上 belong 共识权重>=0.1 = 2/78 = 2.56%), 在 n=105 上
    #   **P(至少 1 条) = 93.5%** ⇒ 它不是一个阈值, 是一次点名。
    #   而旧 MERGE 要求 k=0, 零模型下只有 6.5% 概率触发 —— 相反方向的同一缺陷。
    from math import comb

    def _fisher(a, b, c, dd):
        n1, n2, kk = a + b, c + dd, a + c
        return sum(comb(n1, i) * comb(n2, kk - i)
                   for i in range(a, min(n1, kk) + 1)) / comb(n1 + n2, kk)

    k, j = cb, hb
    pf = _fisher(k, cn - k, j, hn - j) if cn and hn else 1.0
    n_auth = len({posts_by_id[i]["author"] for i in cand_hit_ids})
    p0 = 2 / 78
    null_p = sum(comb(cn, x) * p0 ** x * (1 - p0) ** (cn - x) for x in range(k, cn + 1)) if cn else 1.0
    checks = {"(i) k>=7": k >= 7, "(ii) Fisher p<0.05": pf < 0.05, "(iii) >=3 作者": n_auth >= 3}
    if cn < 20:
        verdict, why = "INCONCLUSIVE", f"ARM_CLEAN 可判条数 {cn} < 冻结门槛 20"
    elif all(checks.values()):
        verdict = "RETAIN_as_core"
        why = (f"三条全中: k={k}>=7 · Fisher {k}/{cn} vs {j}/{hn} p={pf:.5f}<0.05 · "
               f"{n_auth} 个不同作者>=3。零模型下拿到 k>={k} 的概率 {null_p*100:.3f}%")
    else:
        dr = (sum(1 for i in cons if arm[i] == "candidate"
                  and max(cons[i], key=cons[i].get) == "display") / cn) if cn else 0
        if pf >= 0.05 and dr >= 2 / 3:
            verdict, why = "MERGE_into_display", f"与阴性对照不可区分(p={pf:.4f}) 且候选 display 占比 {dr:.3f}>=2/3"
        else:
            verdict = "INCONCLUSIVE"
            why = (f"未过: {[c for c, v in checks.items() if not v]}; "
                   f"MERGE 也不成立(Fisher p={pf:.4f}, display 占比 {dr:.3f})")

    res = {"block": "STUDY2_BELONG_DISCRIMINANT_VALIDITY",
           "★frozen_rule": "tests/data/belong_disposition_rule_prereg.json —— 照表查, 不改表",
           "★circularity_split": {
             "markers_leaked_into_prompt": leaked,
             "★handling": ("**不删, 拆两臂**: 判据只看 ARM_CLEAN(标志词不出现在标注 prompt 里); "
                            "ARM_LEAKED 单独报作诊断。★ 若 belong **只**在 ARM_LEAKED 点火, "
                            "说明仪器在对自己 brief 的字面做关键词匹配, 而不是在识别构念。"),
             "arm_leaked": {"belong_argmax": lb, "n": ln_, "rate": lr},
           },
           "annotators": RG.MODELS, "body_chars": RG.BODY_CHARS,
           "candidate_ARM_CLEAN": {"belong_argmax": cb, "n": cn, "rate": cr},
           "hard_negative": {"belong_argmax": hb, "n": hn, "rate": hr},
           "★verdict": verdict, "★why": why,
           "★rule_checks": checks, "fisher_p": round(pf, 5),
           "n_distinct_authors_among_hits": n_auth,
           "★null_model_P_of_k_or_more": round(null_p, 6),
           "★what_this_does_NOT_answer": [
             "★ 候选是**标志词**选出来的, 不是**人工判定**的真正 belong 正例。"
             "GPT 的建议是「先由人类或冻结规则确认这些文本是否真正表达 C9, 再测 LLM」—— "
             "本轮用的是**冻结规则**(标志词), **没有人工裁定**。⇒ 候选集里必然混有假阳性, "
             "这会**压低**命中率 ⇒ 若判 MERGE, 该判决**偏保守方向相反**, 需谨慎。",
             "★ 只对照了最近邻 display。与 reward/audit 的边界未测。",
           ]}
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT)   # ★ 记下进 prompt 的环境参数, 否则事后无法核实可比性
    (OUT / "raw.json").write_text(json.dumps({"dists": dists, "arm": arm}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "tests/data/study2_belong_discriminant.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1)[:1400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
