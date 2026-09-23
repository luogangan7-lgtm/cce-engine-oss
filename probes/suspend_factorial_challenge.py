#!/usr/bin/env python3
"""suspend 的 2×2 析因挑战 —— 诊断「必要条件执行失败」这一格。

## 它回答什么
四分法里**只有第一格**能用合成题干净回答:
「文本根本没提供悬置证据, 模型却靠**质询/收藏**猜出来」= **必要条件执行失败**。
其余三格(标注器能力限制 / 类别边界欠规定 / 只在明确表达上成立)**需要独立人类参考**, 本轮没有。

## 设计(预注册冻结于 tests/data/suspend_factorial_prereg.json, 校验和 8a25dc3cb6db472d)
**明确悬置(有/无) × 质询句式(有/无)**, 每格 6 题 = 24; 另 5 组负例 × 2 = 10。
同一题干尽量保持产品/需求/理由/长度相近 —— 让格间只差被操纵的那一维。

## ★★ 这是 SYNTHETIC_DIAGNOSTIC
题目是**构造**的。按裁决: 合成题**适合测必要条件与易混边界**, **不推荐冒充新增自然样本量**。
⇒ 其数量**不并入**自然语料资格考的 n, **不继承**任何分辨力结论。
⇒ 且它是我**看过 81 条结果之后**造的 ⇒ **development/diagnostic, 不是 confirmatory**。

## ★ 无论结果如何, 本轮不改判别式、不合并、不删类
"""
import json
import os
import pathlib
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "accuracy"))
# ★ 2026-09-08: 原来这里**硬编 2000**, 而 RG.BODY_CHARS 仍是 700 ⇒ 盖的章会说谎。
#   改成走同一个环境变量: 单一真值, prompt **逐字不变**(2000 还是 2000), 但现在可核实。
os.environ.setdefault("CCE_BODY_CHARS", "2000")
import run_gates as RG  # noqa: E402

OUT = VAULT / "cce_runs" / "suspend_factorial"
ZBASE = "https://api.z.ai/api/paas/v4/chat/completions"
_lock = threading.Lock()


def glm(prompt, model="glm-4.5-flash", mt=6000):
    key = os.environ["ZHIPU_API_KEY"]
    for a in range(6):
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": mt, "temperature": 0}
        req = urllib.request.Request(ZBASE, json.dumps(body).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=900))
            return r["choices"][0]["message"].get("content") or ""
        except Exception:
            pass
        time.sleep(min(6 * (2 ** a), 90))
    return ""


def parse(txt):
    d = RG.extract_json_robust(txt, log_note="fact")
    if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
        v = {k["key"]: float(k.get("weight", 0)) for k in d["knots"] if k.get("key") in RG.KNOTS}
        tot = sum(v.values())
        if tot > 0:
            return {k: w / tot for k, w in v.items()}
    return None


def main():
    items = json.loads((VAULT / "cce_runs" / "suspend_factorial_items.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT, extra={"annotators_actually_used": list(RG.MODELS) + ["glm-4.5-flash"]})   # ★ 含额外标注者
    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {(r["id"], r["model"]) for r in rows}
    models = list(RG.MODELS) + ["glm-4.5-flash"]
    jobs = [(it, m) for it in items for m in models if (it["id"], m) not in have]
    print(f"{len(items)} 题 × {len(models)} 标注者(MiniMax 五员 + GLM 跨家族) · 待跑 {len(jobs)}", flush=True)

    def one(job):
        it, m = job
        p = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                                decision_tree=RG.DECISION_TREE,
                                negative_examples=RG.NEGATIVE_EXAMPLES, body=it["b"][:RG.BODY_CHARS])
        txt = ""
        try:
            txt = (glm(p) if m.startswith("glm") else RG.call(m, p)) or ""
            dist = parse(txt)
        except Exception:   # ★ 一条坏读数不许掀翻整轮
            dist = None
        r = {"id": it["id"], "model": m, "arm": it["arm"], "cell": it["cell"],
             "pending": it["pending"], "question": it["question"],
             "dist": dist, "top1": max(dist, key=dist.get) if dist else None,
             "suspend_w": round(dist.get("suspend", 0), 3) if dist else None,
             "raw": txt[:4000]}
        with _lock:                                # ★ 逐条落盘
            rows.append(r)
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            if len(rows) % 20 == 0:
                print(f"  {len(rows)}/{len(items)*len(models)}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, jobs))
    print(f"\n★ 完成 {len(rows)} 条读数")


if __name__ == "__main__":
    main()
