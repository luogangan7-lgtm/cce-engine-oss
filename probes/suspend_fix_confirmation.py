#!/usr/bin/env python3
"""suspend 修法的确证 —— **V0(现网) vs V1(仅改一个字段)** 跑同一批**全新**题目。

## 为什么必须用新题
修法是**看到第一轮 F3 失败之后**想到的 ⇒ 用第一轮那 34 题确认它就是**用结果选规则**。
本轮 22 题**全新**, 与第一轮同构造规则、不同实例。预注册校验和 6627d70e135d0113。

## ★★★ 修法落在哪, 以及我一度写错的地方
★ 目标字段 = **`suspend.negative_examples_prompt`** —— **已验证进 prompt**(NEGATIVE_EXAMPLES)。
★★★ 我一度写「修 `hard_discriminant`」—— **那是错的**: 它**不进 prompt**
   (KNOT_BRIEF 只注入 key/name/signature/behavior[:70]), 改它**一个字都不改变模型行为**。
   ⇒ **修字段之前先确认它进不进 prompt。** 这条今天第三次出现。

## ★★ 最小改动
**只改这一个字段**。decision_tree / signature / behavior / 其余八结**全部不动** ——
防止同时改多处后无法归因。

## ★ 现网不动
本探针在**旁路**构造 V1 的 NEGATIVE_EXAMPLES 字符串, **不写回 config**。
改 prompt = 换仪器, 必须走 `how_to_change_core` 的换代流程 —— 只有 C1~C4 全过才走。
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

PRE = json.loads((ROOT / "tests/data/suspend_fix_confirmation_prereg.json").read_text(encoding="utf-8"))
FIX = PRE["★★the_fix_verbatim"]
OUT = VAULT / "cce_runs" / "suspend_fix_confirm"
ZBASE = "https://api.z.ai/api/paas/v4/chat/completions"
_lock = threading.Lock()

# ★ V1 = 只把 suspend 那一行的负例替换掉, 其余逐字不动
NEG_V0 = RG.NEGATIVE_EXAMPLES
assert FIX["old"] in NEG_V0, "★ 修法的 old 文本与现网 NEGATIVE_EXAMPLES 不符 —— 停"
NEG_V1 = NEG_V0.replace(FIX["old"], FIX["new"], 1)
assert NEG_V1 != NEG_V0 and NEG_V0.count(FIX["old"]) == 1, "★ 替换未生效或命中多处"


def glm(prompt, mt=6000):
    key = os.environ["ZHIPU_API_KEY"]
    for a in range(6):
        body = {"model": "glm-4.5-flash", "messages": [{"role": "user", "content": prompt}],
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
    d = RG.extract_json_robust(txt, log_note="fix")
    if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
        v = {k["key"]: float(k.get("weight", 0)) for k in d["knots"] if k.get("key") in RG.KNOTS}
        t = sum(v.values())
        if t > 0:
            return {k: w / t for k, w in v.items()}
    return None


def main():
    items = json.loads((VAULT / "cce_runs" / "suspend_confirm_items.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT, extra={"annotators_actually_used": list(RG.MODELS) + ["glm-4.5-flash"]})   # ★ 含额外标注者
    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {(r["id"], r["model"], r["arm"]) for r in rows}
    models = list(RG.MODELS) + ["glm-4.5-flash"]
    jobs = [(it, m, a) for it in items for m in models for a in ("V0", "V1")
            if (it["id"], m, a) not in have]
    print(f"{len(items)} 题 × {len(models)} 标注者 × 2 臂 · 待跑 {len(jobs)}", flush=True)
    print(f"★ V1 只改 suspend 的 negative_examples; 两臂其余**逐字相同**", flush=True)

    def one(job):
        it, m, arm = job
        p = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                                decision_tree=RG.DECISION_TREE,
                                negative_examples=(NEG_V0 if arm == "V0" else NEG_V1),
                                body=it["b"][:RG.BODY_CHARS])
        txt = ""
        try:
            txt = (glm(p) if m.startswith("glm") else RG.call(m, p)) or ""
            dist = parse(txt)
        except Exception:   # ★ 一条坏读数不许掀翻整轮(arm B 曾因 JSON 里一个字面 `...` 崩在 339/405)
            dist = None
        r = {"id": it["id"], "model": m, "arm": arm, "cell": it["cell"],
             "should_be_suspend": it["★should_be_suspend"], "dist": dist,
             "top1": max(dist, key=dist.get) if dist else None,
             "suspend_w": round(dist.get("suspend", 0), 3) if dist else None,
             "raw": txt[:4000]}   # ★ 原始响应: 区分「模型没答」与「解析器坏了」, 并支持确定性重解析
        with _lock:
            rows.append(r)
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            if len(rows) % 24 == 0:
                print(f"  {len(rows)}/{len(items)*len(models)*2}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, jobs))
    print(f"\n★ 完成 {len(rows)} 条读数 · 解析成功 {sum(1 for r in rows if r['top1'])}")


if __name__ == "__main__":
    main()
