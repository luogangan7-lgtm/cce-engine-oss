#!/usr/bin/env python3
"""语义 proxy 盲评 —— ontology-blinded，**永远不解锁** human SESOI。

## 定位（外部评审 2026-08-19 判决，逐条照办）
semantic_anchor.human = BLOCKED_EXTERNAL_ANCHOR（缺的是**外部真值**，不是算力）
semantic_anchor.llm_proxy = AVAILABLE_EXPLORATORY
★ 独立模型 ≠ 独立真值：不同 LLM 仍共享预训练语料、对长度/风格/权威措辞的偏好、
  类似 RLHF，且已知有 position / verbosity / self-preference bias。
  「qwen 与 glm 一致」只支持 multi-model proxy agreement，**不支持** human ground truth。

## 盲化契约（构造上，不是承诺上）
judge 看不到：九结 taxonomy · CCE prompt · 任何 T/p/readout · 臂标签 · 上游 appraisal/prior
judge 只看到：随机顺序的两段原始文本 + 一个**不含本体词汇**的问题
两个模型家族 × **随机交换 A/B 顺序**（对抗 position bias）

## 为什么现在跑
阿里云订阅约 2026-08-22 到期。proxy 数据是**永久文件**，日后拿到真人锚时可做一个
高价值检验：proxy 到底能不能迁移到人类判断。过期后这批就再也采不到。

## 它能回答的一个当下问题
主面板判 B1(同义改写, 内容不变) **6/20 分开** ⇒ SURFACE_SENSITIVE。
若盲评者也说 B1 两段「处境没变」而 CCE 却判分开 ⇒ 该结论被**独立佐证**。
"""
import hashlib, json, random, sys, threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from exp_crossmodel_desire import call_model, MODELS   # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "llm_proxy_checkpoint.jsonl"
JUDGES = ("Qwen3.8", "GLM5.2")      # 两个家族; **都不是测量模型**
SEED = 20260821
WORKERS = 6
_lock = threading.Lock()

# ★ 问题里不得出现任何本体词汇(结/需求/情绪/动机/心理…)
QUESTION = ("Read the two passages below. Judging only from what each speaker says about "
            "their circumstances, position, or intent, is there a difference between them "
            "large enough to change how you would understand the speaker's situation?\n\n"
            "Answer with exactly one line: ANSWER: SAME or ANSWER: DIFFERENT, "
            "then one short sentence of reason.\n\nPassage 1:\n{a}\n\nPassage 2:\n{b}")


def parse(t):
    u = t.upper()
    if "ANSWER: DIFFERENT" in u:
        return "DIFFERENT"
    if "ANSWER: SAME" in u:
        return "SAME"
    return "UNPARSED"


def _done():
    if not CKPT.exists():
        return set()
    return {(r["base_id"], r["arm"], r["judge"], r["order"]) for r in
            (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())}


def main():
    st = json.loads((P / "stimuli_frozen.json").read_text(encoding="utf-8"))
    f = P / "base_sample_with_extension.json"
    if not f.exists():
        f = P / "base_sample_frozen.json"
    bases = {b["base_id"]: b["text"] for b in json.loads(f.read_text(encoding="utf-8"))["chosen"]}
    var = {(v["base_id"], v["arm"]): v["text"] for v in st["variants"] if "text" in v}
    # L0b 用 base 原文自身作零参照对(两段逐字相同 ⇒ 盲评应压倒性判 SAME, 是**阳性对照**)
    pairs = [(b, "L0b", bases[b], bases[b]) for b in bases]
    pairs += [(b, a, bases[b], var[(b, a)]) for (b, a) in sorted(var) if b in bases]
    done = _done()
    tasks = [(b, a, x, y, j, o) for (b, a, x, y) in pairs for j in JUDGES for o in (0, 1)
             if (b, a, j, o) not in done]
    random.Random(SEED).shuffle(tasks)      # 顺序与臂无关
    n = len(tasks)
    print(f"盲评对 {len(pairs)} × {len(JUDGES)} 家族 × 2 顺序 = {len(pairs)*4}; "
          f"已完成 {len(done)}, 待办 {n}")
    if "--dry" in sys.argv:
        return
    cnt = Counter()

    def run(t):
        b, a, x, y, j, o = t
        p1, p2 = (x, y) if o == 0 else (y, x)
        txt, meta = call_model(j, QUESTION.format(a=p1, b=p2), temperature=0.0,
                               timeout=120, max_retries=2)
        rec = {"base_id": b, "arm": a, "judge": j, "judge_model": MODELS[j]["model"],
               "order": o, "answer": parse(txt), "reason": txt.strip()[:160],
               "error": meta.get("error")}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt["n"] += 1
            if cnt["n"] % 40 == 0 or cnt["n"] == n:
                print(f"  [{cnt['n']}/{n}]", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, tasks))

    all_ = [json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_arm = defaultdict(Counter)
    for r in all_:
        by_arm[r["arm"]][r["answer"]] += 1
    out = {"status": "AVAILABLE_EXPLORATORY", "ontology_blinded": True,
           "judge_families": list(JUDGES), "seed": SEED,
           "never_unlocks": ("human SESOI 保持 BLOCKED_EXTERNAL_ANCHOR —— "
                             "独立模型 ≠ 独立真值; 本数据只支持 multi-model proxy agreement"),
           "question_is_ontology_free": True,
           "n": len(all_),
           "P_DIFFERENT_by_arm": {a: round(c["DIFFERENT"] / max(sum(c.values()), 1), 3)
                                  for a, c in sorted(by_arm.items())},
           "by_arm": {a: dict(c) for a, c in sorted(by_arm.items())},
           "records": all_}
    (P / "llm_proxy_anchor.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("  P(DIFFERENT) 按臂:", out["P_DIFFERENT_by_arm"])


if __name__ == "__main__":
    main()
