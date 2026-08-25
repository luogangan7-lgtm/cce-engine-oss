#!/usr/bin/env python3
"""同批受控对照的刺激生成：R1(同义改写) vs N1b(追加中性内容)。

## 本设计最大的坑
R1 与 N1 的「扰动量」本质上不可比。**不宣称相等** —— 只做到:
  ① 用 R1 相对 L0 的 Levenshtein 距离**定** N1b 的追加长度, 使两臂改动字符数同量级
  ② 两臂各自的编辑距离**随结果一起报**, 让读者自己判
若不做这一步, 「R1 比 N1 更能动读数」就可以被「R1 改得更多」解释掉。

## 生成与验收
生成器 DeepSeek(ontology-blind, ≠测量模型 MiniMax-M3)。
★ 本轮**无独立第三方盲验** —— 阿里云订阅到期后只剩 DeepSeek 一个非测量家族,
  它既生成就不能自评。故刺激合规**只有机器验收**, 这一限度必须随结果标注。
机器验收: R1 长度 ±15% 且不得引入新的心理状态词 · N1b 必须是**严格前缀扩展** ·
  N1b 追加段**零心理词** · 均不得与 L0 逐字相同。
"""
import json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from exp_crossmodel_desire import call_model, MODELS  # noqa: E402

P = ROOT / "tests" / "data" / "rephrase_vs_append"
CKPT = P / "stimuli_checkpoint.jsonl"
GEN = "DeepSeek"
MAX_REGEN = 12   # R1 首轮仅 8/14(3 长度超标 + 3 引入新心理词) ⇒ 提高重试
_lock = threading.Lock()
VOCAB = [w.strip() for w in (ROOT / "tests" / "data" / "ladder" / "PSYCH_VOCAB.txt")
         .read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]

R1_RULE = ("Rewrite the passage keeping what is said and the speaker's situation exactly the same. "
           "Replace wording with synonyms and change the order of sentences. "
           "Do not add, remove, or change any fact. "
           "Do not introduce any word naming a feeling, evaluation, motive, or inner state "
           "that is not already present in the original.")
N_RULE = ("Continue the passage by appending {n} to {m} characters of additional neutral factual "
          "detail (dates, model numbers, locations, procedural steps). "
          "Do not change a single character of the original passage — only append. "
          "Do not name any feeling, evaluation, motive, or inner state.")


def psych(t):
    low = t.lower()
    return sorted({w for w in VOCAB if re.search(r"\b" + re.escape(w) + r"\b", low)})


def edit_distance(a, b):
    """字符级编辑距离(用 SequenceMatcher 的 opcodes 算, 零依赖)。"""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")


def check(arm, base, var, target=None):
    f = []
    if not var.strip():
        return False, ["EMPTY"]
    if var.strip() == base.strip():
        f.append("IDENTICAL")
    if arm == "R1_rephrase":
        r = len(var) / len(base)
        if not (0.85 <= r <= 1.15):
            f.append(f"LENGTH_RATIO={r:.3f}")
        new = set(psych(var)) - set(psych(base))
        if new:
            f.append("NEW_PSYCH_WORDS=" + ",".join(sorted(new)))
    else:
        if not var.startswith(base.rstrip()):
            f.append("NOT_STRICT_APPEND")
        else:
            suf = var[len(base.rstrip()):]
            if psych(suf):
                f.append("APPENDIX_HAS_PSYCH=" + ",".join(psych(suf)))
            # ★ 协议修订 #1(2026-08-25, 此刻一个 T 都没有 ⇒ 依据是 operational 事实):
            #   原带宽 0.6-1.6× 让 N1b 13/14 失败(实测模型追加量超目标 2.4 倍)。
            #   **不收紧提示词、不截断文本**, 改为**放宽下界并记录实际编辑距离**——
            #   因为若 N1b 扰动量**更大**却仍动得**更少**, 结论是 a fortiori, 比精确配平更强。
            #   仅保留下界(防止追加过少导致「没动」是因为几乎没改)。
            if target and len(suf) < 0.6 * target:
                f.append(f"APPEND_TOO_SHORT={len(suf)} < 0.6*{target}")
    return (not f), f


def _done():
    if not CKPT.exists():
        return {}
    out = {}
    for l in CKPT.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if "text" in r:
                out[(r["base_id"], r["arm"])] = r
    return out


def main():
    bases = json.loads((P / "base_sample_frozen.json").read_text(encoding="utf-8"))["chosen"]
    done = _done()
    print(f"生成器 {MODELS[GEN]['model']} · base {len(bases)} · 已完成 {len(done)}")
    if "--dry" in sys.argv:
        return
    out = []

    def run(b):
        recs, fails = {}, {}
        # ① 先出 R1, 量它的编辑距离
        for att in range(1, MAX_REGEN + 1):
            if (b["base_id"], "R1_rephrase") in done:
                recs["R1_rephrase"] = done[(b["base_id"], "R1_rephrase")]
                break
            t, _ = call_model(GEN, R1_RULE + "\n\nOutput only the rewritten passage.\n\nPassage:\n"
                              + b["text"], temperature=0.7, timeout=120, max_retries=2)
            ok, f = check("R1_rephrase", b["text"], t.strip())
            fails["R1_rephrase"] = f
            if ok:
                recs["R1_rephrase"] = {"base_id": b["base_id"], "arm": "R1_rephrase",
                                       "text": t.strip(), "attempt": att,
                                       "edit_distance": edit_distance(b["text"], t.strip())}
                break
        r1 = recs.get("R1_rephrase")
        # ② N1b 的追加长度 = R1 的编辑距离(同量级)
        tgt = r1["edit_distance"] if r1 else max(80, len(b["text"]) // 5)
        for att in range(1, MAX_REGEN + 1):
            if (b["base_id"], "N1b_append_matched") in done:
                recs["N1b_append_matched"] = done[(b["base_id"], "N1b_append_matched")]
                break
            t, _ = call_model(GEN, N_RULE.format(n=int(tgt * 0.8), m=int(tgt * 1.2))
                              + "\n\nOutput the full passage including the original text.\n\nPassage:\n"
                              + b["text"], temperature=0.7, timeout=120, max_retries=2)
            ok, f = check("N1b_append_matched", b["text"], t.strip(), target=tgt)
            fails["N1b_append_matched"] = f
            if ok:
                suf = t.strip()[len(b["text"].rstrip()):]
                recs["N1b_append_matched"] = {"base_id": b["base_id"], "arm": "N1b_append_matched",
                                              "text": t.strip(), "attempt": att,
                                              "edit_distance": len(suf), "append_target": tgt}
                break
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                for a in ("R1_rephrase", "N1b_append_matched"):
                    r = recs.get(a) or {"base_id": b["base_id"], "arm": a,
                                        "status": "GENERATION_FAILED",
                                        # ★ 失败必须带原因 —— 只写 GENERATION_FAILED 等于没记
                                        "last_failures": fails.get(a)}
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.append(b["base_id"])
            print(f"  [{len(out)}/{len(bases)}] {b['base_id'][:8]} "
                  f"R1_ed={r1['edit_distance'] if r1 else 'FAIL'} "
                  f"N1b_ed={recs.get('N1b_append_matched',{}).get('edit_distance','FAIL')}", flush=True)

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(run, bases))
    print("→", CKPT.relative_to(ROOT))


if __name__ == "__main__":
    main()
