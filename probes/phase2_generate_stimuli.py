#!/usr/bin/env python3
"""Phase 2 刺激生成 —— **ontology-blind 双生成器 + 机器验收**。

## 为什么不是我手写
外部评审判决(2026-08-19): 我手写 120 段变体 = experimenter-induced treatment construction
bias, 而且**比 LLM 生成的威胁更大** —— 我不仅懂自然语言, 还知道九结 ontology、CCE prompt、
历史失败模式、哪种表达以前容易被读出。这种知识**无法真正 blind**。
生成模型至少能在**构造上**隔离这些信息。

★ 一条重要限缩(评审给的, 我原来担心范围开太宽了):
  扰动作者**不污染 resolution profile** —— L0 vs L0b 两边都是真实 base 的独立测量,
  不涉及变体作者。作者只影响 A→discriminability 与 B→invariance。
  resolution 的偏倚源是 **base-text sampling frame**, 不是 perturbation author。

## 盲化契约（构造上, 不是承诺上）
- 生成器**逐臂单独调用**, 每次只收到**那一个臂**的改写规则, 不知道还有别的臂存在
  ⇒ 它无从知道「A 应当被读出 / B 应当读不出」这个预期
- 生成器不接触: 九结 taxonomy · CCE prompt · 任何 T/p/readout · 臂标签的含义
- 同一 base 的五个变体由**同一个** generator 写(within-base 比较不与 generator 混杂),
  而 24 个 base 随机分 12/12 给两个家族 ⇒ generator 成为**可估计的 facet**
- 状态标 ONTOLOGY_BLINDED_SYNTHETIC —— **不是「无偏」**: 生成家族与被测模型仍可能共享语言先验

## 机器验收（我只执行, 不改文本, 不看 T 后重做）
  长度 0.85 <= r <= 1.15   ★ 不许运行中放宽到 20%, 也不许「长文生成失败就换短 base」——
                             那会让 generation feasibility 反向改变 sampling frame
  A 臂 无心理状态词        tests/data/ladder/PSYCH_VOCAB.txt(反向自检能抓住违例)
  B2 归一化后与原文逐字相同  ★ 「只改格式标点」是**可完全机器验证**的
  超过 MAX_REGEN 仍不过 → GENERATION_FAILED(不伪造, 不替补, 进 operational 账)
"""
import json, os, random, re, sys, hashlib, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from exp_crossmodel_desire import call_model, MODELS  # noqa: E402

# ── 前登记参数 ──────────────────────────────────────────────────────────────
MEASUREMENT_MODEL = "M3"          # ★ 测量仪器不动(gen4 565470cf26c16d01)
GENERATORS = {"G1": "Qwen3.8", "G2": "GLM5.2"}    # 两个与测量模型**不同家族**的生成器
# ★★ 盲验改为**交叉验证**, 不再用第三个家族。
#   原设计是独立的 G3(KimiK3), 但 owner 只订阅阿里云与 MiniMax 两家 ⇒ 手上只有两个家族。
#   为什么**不能**拿 MiniMax-M3 顶 G3: 它是测量模型。用它筛「这段确实改变了处境」,
#   留下的就是**它自己认为变了**的那些变体 ⇒ 按测量模型的判断筛刺激, 会把可分辨性
#   系统性抬高。这是循环, 比少一个家族严重得多。
#   ⇒ 每个生成器的产出交给**另一个家族**盲验: 永不自评, 永不用测量模型评。
#   ⚠️ 已知限度: 验证者恰是另一个生成器 ⇒ 两者若共享同一语言先验, 该盲验查不出来。
#      故 blind_rule_check 只作**规则合规**的二次确认, 不作「扰动强度」的裁定。
VERIFIER_OF = {"G1": "GLM5.2", "G2": "Qwen3.8"}
VERIFIER_MODE = "CROSS_FAMILY_NO_THIRD_PARTY"
ASSIGN_SEED = 20260819
MAX_REGEN = 8                     # ★ amendment #1 后的值(原 3), 见 PROTOCOL_AMENDMENTS
LEN_LO, LEN_HI = 0.85, 1.15

# ─────────────────────────────────────────────────────────────────────────────
# 协议修订记录。**带时间戳 + 原因 + 「修订时尚无任何 T」的声明**, 缺一不可。
# 判据(外部评审 2026-08-19): 修订依据是 **operational 事实**(生成器格式合规率 / 语料容量)
# 还是 **实验 outcome**(T/p/ladder)? 前者在结果出现前透明更新不引入 outcome-dependent
# flexibility; 后者是 data-dependent deviation。两者风险不同类。
PROTOCOL_AMENDMENTS = [
    {"id": 1, "at": "2026-08-19", "field": "MAX_REGEN", "from": 3, "to": 8,
     "trigger": ("G2(glm-5.2) 每次尝试的格式合规率实测约 31.7%(19/60 首次通过), "
                 "3 次上限下 ladder 完备 base 仅 16/24 < coverage gate 20"),
     "evidence": "tests/data/phase2/stimuli_pre_amendment_maxregen3.json(修订前的完整结果)",
     "outcome_dependent": False,
     "why_not": ("观察到的是**生成器的格式合规率**(operational), "
                 "不是任何 T / p / ladder 结果 —— 此刻 Phase 2 一次测量都还没做"),
     "scope": "对所有 base / 所有臂 / 两个生成器**一律适用**, 不针对某一层或某个失败样本",
     "block": "重跑一次完整 block 后即停; **不许看结果再加**",
     "expected": "单臂通过率 1-(1-0.317)^8 ≈ 94%"},
]
ARMS = ("A1", "A2", "A3", "B1", "B2")

# ★ 逐臂规则。措辞刻意中性 —— 不含「这会/不会改变读数」这类预期泄露。
ARM_RULES = {
 "A1": "Rewrite the passage so that the speaker's situation and position have shifted "
       "slightly from the original. Describe only circumstances and actions. Do not name "
       "any feeling, evaluation, motive, or inner state.",
 "A2": "Rewrite the passage so that the speaker's situation and position have shifted "
       "moderately from the original. Describe only circumstances and actions. Do not name "
       "any feeling, evaluation, motive, or inner state.",
 "A3": "Rewrite the passage so that the speaker's situation and position have shifted "
       "substantially from the original. Describe only circumstances and actions. Do not name "
       "any feeling, evaluation, motive, or inner state.",
 "B1": "Rewrite the passage keeping what is said and the speaker's situation exactly the same. "
       "Replace wording with synonyms and change the order of sentences.",
 "B2": "Reproduce the passage changing only formatting, punctuation and line breaks. "
       "Do not change, add or remove a single word.",
}
_LEN_NOTE = ("Keep the length within {lo}-{hi} characters (the original is {n}). "
             "Output only the rewritten passage, with no preface, label or commentary.")

VOCAB = [w.strip() for w in (ROOT / "tests" / "data" / "ladder" / "PSYCH_VOCAB.txt")
         .read_text(encoding="utf-8").splitlines()
         if w.strip() and not w.startswith("#")]


def psych_hits(text):
    low = text.lower()
    return sorted({w for w in VOCAB if re.search(r"\b" + re.escape(w) + r"\b", low)})


def _norm(t):
    """B2 用: 去掉一切格式/标点/大小写差异后应与原文逐字相同。"""
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def check(arm, base, variant):
    """机器验收。返回 (pass: bool, failures: list)。**不做内容改写**。"""
    f = []
    if not variant.strip():
        return False, ["EMPTY"]
    r = len(variant) / len(base)
    if not (LEN_LO <= r <= LEN_HI):
        f.append(f"LENGTH_RATIO={r:.3f}")
    if variant.strip() == base.strip():
        f.append("IDENTICAL_TO_BASE")
    if arm.startswith("A"):
        h = psych_hits(variant)
        if h:
            f.append("PSYCH_VOCAB=" + ",".join(h))
    if arm == "B2" and _norm(variant) != _norm(base):
        f.append("B2_WORDS_CHANGED")     # 「只改格式」是可完全机器验证的
    return (not f), f


def assign(bases, seed=ASSIGN_SEED):
    """24 base 随机分 12/12 给 G1/G2。同一 base 的五臂由同一 generator 写。"""
    ids = sorted(b["base_id"] for b in bases)
    rng = random.Random(seed)
    rng.shuffle(ids)
    half = len(ids) // 2
    return {**{i: "G1" for i in ids[:half]}, **{i: "G2" for i in ids[half:]}}


def gen_one(gkey, arm, base, temperature=0.7):
    lo, hi = int(len(base) * LEN_LO), int(len(base) * LEN_HI)
    prompt = (ARM_RULES[arm] + "\n\n" + _LEN_NOTE.format(lo=lo, hi=hi, n=len(base))
              + "\n\nPassage:\n" + base)
    out, meta = call_model(gkey, prompt, temperature=temperature)
    return out.strip(), meta, hashlib.sha256(prompt.encode()).hexdigest()[:16]


CKPT = ROOT / "tests" / "data" / "phase2" / "stimuli_checkpoint.jsonl"
WORKERS = 6          # 端点实测 25-55s/次; 6 路并发把 120 次压到 ~15min
_lock = threading.Lock()


def _done_keys():
    """已完成的 (base_id, arm) —— 支持中断续跑。

    ★ 这条是踩出来的: 初版**跑完才落盘**, 中途一停 2 小时调用全丢。
      长任务没有 checkpoint = 一次意外就把已花的钱清零。
    """
    if not CKPT.exists():
        return {}
    out = {}
    for line in CKPT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if "text" in r:                 # ★ 只有成功才算 done
                out[(r["base_id"], r["arm"])] = r   # 失败的要在新 MAX_REGEN 下重来
    return out


def _one(b, arm, gfam, dry=False):
    """单臂: 生成 → 机器验收 → 不过就重生成, 上限 MAX_REGEN。返回 (记录, 尝试日志)。"""
    gkey = GENERATORS[gfam]
    log = []
    for attempt in range(1, MAX_REGEN + 1):
        if dry:
            text, meta, psha = "", {"error": "DRY_RUN"}, "dry"
        else:
            text, meta, psha = gen_one(gkey, arm, b["text"])
        ok, fails = check(arm, b["text"], text) if text else (False, ["NO_OUTPUT"])
        log.append({"base_id": b["base_id"], "arm": arm, "attempt": attempt,
                    "generator_family": gfam, "ok": ok, "failures": fails,
                    "error": meta.get("error")})
        if ok:
            return {"base_id": b["base_id"], "arm": arm, "text": text,
                    "length_stratum": b.get("length_stratum"),
                    "length_ratio": round(len(text) / len(b["text"]), 4),
                    "stimulus_provenance": {
                        "base_text_id": b["base_id"], "arm": arm,
                        "generator_family": gfam,
                        "generator_model_version": MODELS[gkey]["model"],
                        "prompt_sha256": psha, "attempt_index": attempt,
                        "machine_checks": "PASS", "blind_rule_check": "PENDING_CROSS",
                        "verifier_family": VERIFIER_OF[gfam]}}, log
    # ★ 不伪造、不替补、不换更短的 base —— 那会让 generation feasibility 反改 sampling frame
    return {"base_id": b["base_id"], "arm": arm, "status": "GENERATION_FAILED",
            "length_stratum": b.get("length_stratum"), "attempts": MAX_REGEN,
            "last_failures": log[-1]["failures"]}, log


def generate(bases, assignment, dry=False, workers=WORKERS):
    done = _done_keys()
    tasks = [(b, arm) for b in bases for arm in ARMS
             if (b["base_id"], arm) not in done]
    recs, attempts_log = list(done.values()), []
    if done:
        print(f"  续跑: 已完成 {len(done)}, 待办 {len(tasks)}")
    n = len(tasks)

    def run(t):
        b, arm = t
        rec, log = _one(b, arm, assignment[b["base_id"]], dry=dry)
        with _lock:
            recs.append(rec)
            attempts_log.extend(log)
            if not dry:
                with CKPT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            k = len(recs) - len(done)
            print(f"  [{k}/{n}] {rec['base_id'][:8]} {arm} "
                  f"{'OK' if 'text' in rec else 'FAILED ' + str(rec.get('last_failures'))}",
                  flush=True)
        return rec

    if dry or workers <= 1:
        for t in tasks:
            run(t)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(run, tasks))
    return recs, attempts_log


if __name__ == "__main__":
    frozen = json.loads((ROOT / "tests" / "data" / "phase2"
                         / "base_sample_frozen.json").read_text(encoding="utf-8"))
    bases = frozen["chosen"]
    asg = assign(bases)
    from collections import Counter
    print(f"base n={len(bases)}  分配 {dict(Counter(asg.values()))}  "
          f"生成器 {GENERATORS}  交叉盲验 {VERIFIER_OF} ({VERIFIER_MODE})")
    print(f"计划调用 {len(bases)*len(ARMS)} 次(不含重试, 上限 ×{MAX_REGEN})")
    need = set(GENERATORS.values()) | set(VERIFIER_OF.values())
    missing = [m for m in sorted(need) if not os.environ.get(MODELS[m]["key_env"])]
    if missing or "--dry" in sys.argv:
        print("  缺 key:", {m: MODELS[m]["key_env"] for m in missing} or "无")
        recs, log = generate(bases[:1], asg, dry=True)
        print(f"  [dry] 单 base 走通流程, 产出 {len(recs)} 条记录, "
              f"全部 {recs[0].get('status')}")
        sys.exit(0 if "--dry" in sys.argv else 1)
    recs, log = generate(bases, asg)
    ok = [r for r in recs if "text" in r]
    out = ROOT / "tests" / "data" / "phase2" / "stimuli_frozen.json"
    out.write_text(json.dumps({"status": "ONTOLOGY_BLINDED_SYNTHETIC",
                               "generators": GENERATORS, "verifier_of": VERIFIER_OF,
                               "verifier_mode": VERIFIER_MODE,
                               "assign_seed": ASSIGN_SEED, "max_regen": MAX_REGEN,
                               "len_bounds": [LEN_LO, LEN_HI],
                               "n_ok": len(ok), "n_failed": len(recs) - len(ok),
                               "variants": recs, "attempts": log},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  产出 {len(ok)}/{len(recs)} 通过机器验收 → {out.relative_to(ROOT)}")


def preflight():
    """花钱之前先探活。每个现役模型发一次最小请求，报可用性与真实报错。

    ★ 存在的理由: 上一次「模型可用性」是 2026-08-01 记的, 早已可能过期。
      断言现状必须查来, 不能想来 —— 探活比读旧笔记可靠。
    """
    out = {}
    for tag, mk in sorted({**{f"gen:{k}": v for k, v in GENERATORS.items()},
                           **{f"verify:{k}": v for k, v in VERIFIER_OF.items()}}.items()):
        txt, meta = call_model(mk, "Reply with the single word: ok", temperature=0.0)
        out[tag] = {"model": MODELS[mk]["model"], "alive": bool(txt.strip()),
                    "reply": txt.strip()[:40], "error": meta.get("error")}
    return out
