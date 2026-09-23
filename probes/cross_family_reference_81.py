#!/usr/bin/env python3
"""★★★ 第五条路: **直接验证这 81 条产物**, 而不是先证明五名标注者「普遍合格」。

## 为什么是这条
2026-09-08 网页 GPT(Pro, 思考 10m10s)的裁决:
> 「若近期真正要交付的是这 81 条的验收结果, 我会**优先考虑独立人工参考标注**,
>  而不是先投入大规模采集、建设一场**仅用于决定谁能参与这 81 条验收**的资格考。」
★★★ 它把问题从「**先证明谁合格**」翻转成「**直接证明这批产物的质量**」——
   而后者才是实际要交付的东西。**我一直在解前一个问题, 而它不是必需的前置。**

## 与 GPT 原方案的差别, 以及为什么这个差别必须写在最上面
GPT 说的是 **独立人工参考**。我**没有人类复核者**, 而**我自己不能当** ——
2026-08-07 的冷启动盲测之所以有效, 是因为标注者「从未参与 codebook 修订」;
而我今天大量改动了 taxonomy / 资格考判据 / 多个闸, **我是这条链的作者**。
⇒ 本探针用 **`glm-4.5-flash`** 代替: 跨家族(与测量模型 MiniMax 不同家族)、
  在**人定的 5 个锚例**上阳性对照 **5/5**、且**从未标注过评论语料**(它只标过帖子)。
★★ 真值标签因此是 **`cross_family_model_reference`**, **不是** human-adjudicated。
   阳性对照 5/5 的 Wilson 下界只有 **0.566** —— 这个限度必须随结论一起报。

## 它能给什么、不能给什么
· **能给**: 固定语料(81 条评论)上, MiniMax 五员的共识标签与**一个独立家族**的参考标签之间的一致度。
· **不能给**: ①不把五名标注者变成 QUALIFIED ②不恢复旧语料的外部独立性
  ③**不是**人工金标 —— 两个模型都可能同向错。

## ★ 顺带补上一个缺口
GLM 此前**只标过帖子**, 从未标过评论 ⇒ 「跨家族一致」只在帖子侧验过。
本轮**第一次**在评论侧验, 也就是**验收语料本身所在的那一侧**。
"""
import json
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

BASE = "https://api.z.ai/api/paas/v4/chat/completions"
MODEL = "glm-4.5-flash"
MAX_TOK = 6000          # ★ 推理模型, reasoning_content 独占预算; 1500 时 content 为空
OUT = VAULT / "cce_runs" / "cross_family_reference_81"
_lock = threading.Lock()


def call(prompt):
    """★ 串行/低并发 + 指数退避 + timeout 900s(实测 420s 会超时, 且超时**与内容无关**, Fisher p=0.71)。"""
    key = os.environ["ZHIPU_API_KEY"]
    for a in range(6):
        body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": MAX_TOK, "temperature": 0}
        req = urllib.request.Request(BASE, json.dumps(body).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=900))
            ch = r["choices"][0]
            return ch["message"].get("content") or "", ch.get("finish_reason")
        except Exception:
            pass
        time.sleep(min(6 * (2 ** a), 90))
    return "", "err"


def main():
    corpus = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
    anchors = set(RG.ANCHOR_IDS)
    items = [c for c in corpus if c["id"] not in anchors]      # 与验收的 SAMPLE 同口径
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT, extra={"annotators_actually_used": ["glm-4.5-flash"]})   # ★ 含额外标注者
    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {r["id"] for r in rows}
    todo = [c for c in items if c["id"] not in have]
    print(f"验收语料 {len(items)} 条**评论**(与 SAMPLE 同口径) · 已有 {len(rows)} · 待跑 {len(todo)}", flush=True)
    print(f"参考标注者 {MODEL}(跨家族) · max_tokens={MAX_TOK} · 2 并发 · **逐条落盘**", flush=True)
    t0 = time.time()

    def one(c):
        p = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                                decision_tree=RG.DECISION_TREE,
                                negative_examples=RG.NEGATIVE_EXAMPLES,
                                body=c["b"][:RG.BODY_CHARS])
        dist, fr, txt = None, None, ""
        try:      # ★ 一条坏读数不许掀翻整轮(arm B 曾因 JSON 里一个字面 `...` 崩在 339/405)
            txt, fr = call(p)
            d = RG.extract_json_robust(txt, log_note="glm_ref81")
            if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
                v = {}
                for k in d["knots"]:
                    if isinstance(k, dict) and k.get("key") in RG.KNOTS:   # ★ 元素未必是 dict
                        v[k["key"]] = float(k.get("weight", 0))
                tot = sum(v.values())
                if tot > 0:
                    dist = {k: w / tot for k, w in v.items()}
        except Exception:
            pass
        r = {"id": c["id"], "dist": dist,
             "top1": max(dist, key=dist.get) if dist else None, "finish": fr,
             "raw": (txt or "")[:4000]}   # ★ 原始响应: 支持确定性重解析(那不算重新抽样)
        with _lock:
            rows.append(r)
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            n = len(rows)
            if n % 10 == 0:
                el = time.time() - t0
                per = el / max(1, n - len(have))
                print(f"  {n}/{len(items)} · {per:.0f}s/条 · 剩 ~{(len(items)-n)*per/60:.0f}分", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(one, todo))
    ok = [r for r in rows if r["top1"]]
    print(f"\n★ 解析成功 {len(ok)}/{len(rows)}")
    import collections
    print(f"★ GLM 在**评论**上的分布: {dict(collections.Counter(r['top1'] for r in ok).most_common())}")


if __name__ == "__main__":
    main()
