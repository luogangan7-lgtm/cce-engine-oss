#!/usr/bin/env python3
"""交叉家族盲验 —— G1 写的交 GLM 验, G2 写的交千问验。

## 为什么不是第三方
owner 只订阅阿里云与 MiniMax ⇒ 手上只有两个家族, 而 MiniMax 是**测量模型**。
★ 用测量模型当盲验 = 按它自己的判断筛刺激, 留下的都是它认为变了的那些
  ⇒ 可分辨性被系统性抬高。这是循环, 比少一个家族严重得多。

## 盲化
验证者只看到: 原文 · 变体 · **那一条规则的原文**。看不到:
  九结 taxonomy · CCE prompt · 任何 T/p/readout · 臂的等级含义(不知道 A2 是「三级里的中级」)
  · 其它臂的存在 · 「A 应被读出 / B 不应」这个预期

## 限度(写在这里, 不许省略)
验证者恰是**另一个生成器**。两者若共享同一语言先验, 这道盲验查不出来。
⇒ blind_rule_check 只作**规则合规**的二次确认, **不作「扰动强度」的裁定**。
"""
import json, sys, threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))
from exp_crossmodel_desire import call_model, MODELS   # noqa: E402
from phase2_generate_stimuli import ARM_RULES, VERIFIER_OF, GENERATORS  # noqa: E402

CKPT = ROOT / "tests" / "data" / "phase2" / "blind_verify_checkpoint.jsonl"
WORKERS = 6
_lock = threading.Lock()

TMPL = ("Below are two passages and a rule. Judge only whether PASSAGE B follows the rule "
        "with respect to PASSAGE A.\n\nRule:\n{rule}\n\nPASSAGE A:\n{a}\n\nPASSAGE B:\n{b}\n\n"
        "Answer with exactly one line: VERDICT: FOLLOWS or VERDICT: VIOLATES, "
        "then one short sentence of reason on the next line.")


def parse(txt):
    up = txt.upper()
    if "VERDICT: FOLLOWS" in up:
        return "FOLLOWS"
    if "VERDICT: VIOLATES" in up:
        return "VIOLATES"
    return "UNPARSED"


def _done():
    if not CKPT.exists():
        return set()
    return {(json.loads(l)["base_id"], json.loads(l)["arm"])
            for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()}


def main():
    st = json.loads((ROOT / "tests" / "data" / "phase2"
                     / "stimuli_frozen.json").read_text(encoding="utf-8"))
    bases = {b["base_id"]: b["text"] for b in json.loads(
        (ROOT / "tests" / "data" / "phase2"
         / "base_sample_frozen.json").read_text(encoding="utf-8"))["chosen"]}
    todo = [v for v in st["variants"] if "text" in v
            and (v["base_id"], v["arm"]) not in _done()]
    print(f"待验 {len(todo)} 条 (已完成 {len(_done())})")
    n = len(todo)
    out = []

    def run(v):
        gfam = v["stimulus_provenance"]["generator_family"]
        vkey = VERIFIER_OF[gfam]
        txt, meta = call_model(vkey, TMPL.format(rule=ARM_RULES[v["arm"]],
                                                 a=bases[v["base_id"]], b=v["text"]),
                               temperature=0.0, timeout=120, max_retries=2)
        rec = {"base_id": v["base_id"], "arm": v["arm"], "generator_family": gfam,
               "verifier_family": vkey, "verifier_model": MODELS[vkey]["model"],
               "verdict": parse(txt), "reason": txt.strip()[:200],
               "error": meta.get("error")}
        with _lock:
            out.append(rec)
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  [{len(out)}/{n}] {rec['base_id'][:8]} {rec['arm']} "
                  f"{gfam}→{vkey}: {rec['verdict']}", flush=True)
        return rec

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, todo))

    allrec = [json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = ROOT / "tests" / "data" / "phase2" / "blind_verify_frozen.json"
    res.write_text(json.dumps({
        "mode": "CROSS_FAMILY_NO_THIRD_PARTY", "verifier_of": VERIFIER_OF,
        "limitation": ("验证者恰是另一个生成器; 两者若共享同一语言先验, 这道盲验查不出来。"
                       "⇒ 只作规则合规的二次确认, 不作扰动强度裁定。"),
        "n": len(allrec),
        "by_verdict": dict(Counter(r["verdict"] for r in allrec)),
        "by_arm": {a: dict(Counter(r["verdict"] for r in allrec if r["arm"] == a))
                   for a in sorted({r["arm"] for r in allrec})},
        "by_generator": {g: dict(Counter(r["verdict"] for r in allrec
                                         if r["generator_family"] == g))
                         for g in sorted({r["generator_family"] for r in allrec})},
        "records": allrec}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", res.relative_to(ROOT))
    print("  总判决:", dict(Counter(r["verdict"] for r in allrec)))


if __name__ == "__main__":
    main()
