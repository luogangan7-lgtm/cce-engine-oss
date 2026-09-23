#!/usr/bin/env python3
"""锚例扩充 —— **跨家族模型共识**给候选帖打标。预注册见 tests/data/anchor_expansion_prereg.json。

## ★★ 为什么这条路今天才可行
我上一轮判定「锚例扩充**结构上做不成**」, 前提是「没有第二个模型家族」——
库内铁律禁止拿**测量模型**(MiniMax)定锚例真值, 那是循环。
**那个前提是错的**: owner 提醒后实测, 智谱 `api.z.ai` 的 **glm-4.7-flash / glm-4.5-flash 免费档可用**。
★ 我第一次探活用了 `open.bigmodel.cn` + 付费模型 ⇒ 全 429 ⇒ 误报不可用;
  而**库里 2026-07-21 就记着 CCE 用的是 api.z.ai**。探了活, 但没先查库确认端点。

## ★ 阳性对照先行(今天刚立的闸)
在**人定的 5 个既有锚例**上: glm-4.5-flash **5/5**, glm-4.7-flash **4/4**(第 5 条 tok 打满非判错)。
★★ 但 9/9 的 Wilson 下界只有 **0.70** —— 排除不了真实准确率低到 70%;
   且那 5 条是人挑来当锚例的(清晰样本), **边界样本上的表现未知**。

## 真值规则(冻结)
**只保留两个 GLM top1 一致的**。不一致丢弃(只有两票, 不做多数决)。
★ 产物标 `truth_source: cross_family_model_consensus` —— **不是** human-adjudicated,
  **不得**在未经 owner 确认前替换 anchors.json。

## 已知限度
两个标注者同属 **GLM 家族**(4.5 与 4.7) ⇒ 共享先验查不出来。
与库内 2026-08-19 记的限度同型: 「验证者恰是另一个生成器…该盲验查不出来」。
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
# ★ 2026-09-08: 原来这里**硬编 2000**, 而 RG.BODY_CHARS 仍是 700 ⇒ 盖的章会说谎。
#   改成走同一个环境变量: 单一真值, prompt **逐字不变**(2000 还是 2000), 但现在可核实。
os.environ.setdefault("CCE_BODY_CHARS", "2000")
import run_gates as RG  # noqa: E402

BASE = "https://api.z.ai/api/paas/v4/chat/completions"
MODELS = ("glm-4.5-flash", "glm-4.7-flash")
MAX_TOK = 6000          # ★ flash 档是推理模型, reasoning_content 独占预算; 1500 时 content 为空
OUT = VAULT / "cce_runs" / "anchor_expansion"


def call(model, prompt):
    """★ **串行 + 指数退避** —— 免费档限流严, 并发 3 实测会大面积 429。"""
    key = os.environ["ZHIPU_API_KEY"]
    last = ""
    for a in range(8):
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": MAX_TOK, "temperature": 0}
        req = urllib.request.Request(BASE, json.dumps(body).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=420))
            ch = r["choices"][0]
            return ch["message"].get("content") or "", ch.get("finish_reason")
        except urllib.error.HTTPError as e:
            last = f"HTTP{e.code}"
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(6 * (2 ** a), 90))
    return "", f"err({last})"


def label(model, body):
    p = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                            decision_tree=RG.DECISION_TREE,
                            negative_examples=RG.NEGATIVE_EXAMPLES, body=body[:RG.BODY_CHARS])
    c, fr = call(model, p)
    try:
        d = RG.extract_json_robust(c, log_note="glm_anchor")
        if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
            ks = {k["key"]: float(k.get("weight", 0)) for k in d["knots"]
                  if isinstance(k, dict) and k.get("key") in RG.KNOTS}   # ★ 元素未必是 dict
            if ks:
                return max(ks, key=ks.get), ks, fr, c
    except Exception:
        pass          # ★ 一条坏读数不许掀翻整轮
    return None, None, fr, c


def main():
    cand = json.loads((VAULT / "cce_runs" / "anchor_candidates_60.json").read_text(encoding="utf-8"))
    print(f"候选 {len(cand)} 篇 × {len(MODELS)} 个 GLM · 串行 · max_tokens={MAX_TOK}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT, extra={"annotators_actually_used": list(MODELS)})   # ★ 含额外标注者
    ckpt = OUT / "raw.json"
    # ★★ 断点续跑 + 逐条落盘。第一版**只在最后 write 一次** —— 60 篇 × ~54s ≈ 1 小时的活,
    #   挂在 55/60 就全丢。同日 Run B 崩在 405 次标注之后, 靠「落盘在前」才没丢数据;
    #   我写这个脚本时**又犯了同一个错**。⇒ 已由 tests/test_cce_incremental_persistence.py 钉住。
    rows = json.loads(ckpt.read_text(encoding="utf-8")) if ckpt.exists() else []
    have = {r["id"] for r in rows}
    cand = [c for c in cand if c["id"] not in have]
    if have:
        print(f"  ★ 断点续跑: 已有 {len(have)} 条, 待跑 {len(cand)}", flush=True)
    for i, c in enumerate(cand, 1):
        r = {"id": c["id"], "author": c["author"], "chars": len(c["b"])}
        for m in MODELS:
            top, dist, fr, raw = label(m, c["b"])
            # ★ 落盘**原始响应**: 没有它就无法区分「模型没答」与「解析器坏了」,
            #   也走不了「用同一确定性修复重新解析已有响应」这条不算重新抽样的重试路。
            r[m] = {"top1": top, "dist": dist, "finish": fr, "raw": (raw or "")[:4000]}
            time.sleep(2)
        a, b = r[MODELS[0]]["top1"], r[MODELS[1]]["top1"]
        r["agree"] = (a is not None and a == b)
        r["consensus_knot"] = a if r["agree"] else None
        rows.append(r)
        ckpt.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")   # ★ 逐条落盘
        if i % 5 == 0 or r["agree"]:
            n_ok = sum(1 for x in rows if x["agree"])
            print(f"  {i}/{len(cand)} · 一致 {n_ok} · 本条 {a} vs {b} "
                  f"{'✅' if r['agree'] else ''}", flush=True)
    import collections
    agreed = [r for r in rows if r["agree"]]
    by_knot = collections.Counter(r["consensus_knot"] for r in agreed)
    parsed = sum(1 for r in rows if r[MODELS[0]]["top1"] and r[MODELS[1]]["top1"])
    res = {"block": "ANCHOR_EXPANSION_CROSS_FAMILY_RESULT",
           "★truth_source": "**cross_family_model_consensus** —— **不是** human-adjudicated",
           "★prereg": "tests/data/anchor_expansion_prereg.json",
           "n_candidates": len(rows), "n_both_parsed": parsed,
           "n_agreed": len(agreed),
           "agreement_rate_among_parsed": round(len(agreed) / parsed, 4) if parsed else None,
           "by_knot": dict(by_knot.most_common()),
           "n_knots_covered": len(by_knot),
           "★do_not_use_without_owner_confirmation": (
               "★★ GLM 共识**不等于**人裁定: 阳性对照 9/9 的 Wilson 下界只有 **0.70**, "
               "且那 5 条是人挑来当锚例的清晰样本, **边界样本未验**。"
               "⇒ **不得**在未经 owner 确认前替换 accuracy/data/anchors.json。"),
           "candidates": [{"id": r["id"], "knot": r["consensus_knot"], "chars": r["chars"]}
                          for r in agreed]}
    (ROOT / "tests/data/anchor_expansion_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n★ 两模型都解析成功 {parsed}/{len(rows)} · **一致 {len(agreed)}** "
          f"(一致率 {len(agreed)/parsed:.1%})" if parsed else "★ 无有效解析")
    print(f"★ 覆盖 **{len(by_knot)}** 个结: {dict(by_knot.most_common())}")


if __name__ == "__main__":
    main()
