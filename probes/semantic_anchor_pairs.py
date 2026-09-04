#!/usr/bin/env python3
"""生成语义锚的**盲评对** —— 供 >=3 名独立人类评分者使用。

## 契约(来自 cce_ksep.SIGNIFICANCE_CONTRACT['interpretive']['human']['unblock_requires'])
· 3 名独立评分者 · 30–50 对 · 必含 L0b_same / B1 / B2 / A1 / A2 / A3 六个臂
· 盲: ontology-free 提问 + **随机顺序**
· **先验收人类锚自身**(一致性/内部一致/序性), 再去关联 CCE 的 T

## ★ 评分者看不到什么(逐条对应 blinding_contract)
九结 taxonomy · CCE prompt · T 与任何读数 · 臂标签(A1/A2/…) · 上游 appraisal/prior。
**只看随机顺序的两段原始文本。**

## ★ 为什么要有 L0b_same
L0b 是同一底文的**同义改写**, 人类应判「基本相同」。它是**注意力/一致性检查** ——
若评分者把 L0b 判成「有意义地不同」, 那这位评分者的数据不可用。
★ 这不是给评分者的陷阱题, 是**锚自身的验收**: 契约明写「先验收人类锚自身的性质」。
"""
import hashlib, json, os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAN = json.load(open(os.path.join(ROOT, "tests/data/phase2/panel_manifest.json"), encoding="utf-8"))
ARMS_REQUIRED = ("L0b", "B1", "B2", "A1", "A2", "A3")
N_PAIRS = 40                 # 契约区间 30–50 的中位
SEED = 20260904              # 冻结的随机种子 —— 换种子 = 换样本, 属判据变更


def build():
    by = {}
    for a in MAN["arms"]:
        by.setdefault(a["base_id"], {})[a["arm"]] = a["text"]
    # 只用**六个臂都齐**的底文, 保证每个臂都能配到对
    usable = sorted(b for b, d in by.items() if "L0" in d and all(x in d for x in ARMS_REQUIRED))
    rng = random.Random(SEED)
    pairs, quota = [], {arm: 0 for arm in ARMS_REQUIRED}
    per_arm = N_PAIRS // len(ARMS_REQUIRED)
    for arm in ARMS_REQUIRED:
        for b in rng.sample(usable, min(per_arm, len(usable))):
            left, right = by[b]["L0"], by[b][arm]
            if rng.random() < 0.5:                      # ★ 随机顺序
                left, right = right, left
            pid = hashlib.sha256(f"{b}|{arm}|{SEED}".encode()).hexdigest()[:12]
            pairs.append({"pair_id": pid, "a": left, "b": right,
                          "★hidden_base": b, "★hidden_arm": arm})
            quota[arm] += 1
    rng.shuffle(pairs)                                   # ★ 呈现顺序也随机
    return pairs, quota, usable


def main():
    pairs, quota, usable = build()
    print(f"可用底文(六臂齐全): {len(usable)} 个 · 生成 {len(pairs)} 对")
    print("每臂配额:", quota)
    assert set(quota) == set(ARMS_REQUIRED) and all(v > 0 for v in quota.values()), \
        "★ 契约要求六个臂都必须有"
    assert 30 <= len(pairs) <= 50, f"★ 契约要求 30–50 对, 实得 {len(pairs)}"

    # ★ 交付给评分者的那份**不含**任何隐藏字段
    blind = [{"pair_id": p["pair_id"], "a": p["a"], "b": p["b"]} for p in pairs]
    key = {p["pair_id"]: {"base": p["★hidden_base"], "arm": p["★hidden_arm"]} for p in pairs}
    for b in blind:
        assert not any(k.startswith("★") or k in ("arm", "base", "T", "readout") for k in b), b
    out = os.path.join(ROOT, "tests/data/phase2")
    json.dump({"kind": "cce.semantic_anchor.blind_pairs.v1", "seed": SEED,
               "n": len(blind),
               "★question": "这两段文字，在你读来是——完全一样的意思 / 有点不同但无关紧要 / 有实质不同？",
               "★no_ontology_words": "提问里不含任何九结/CCE 词汇",
               "pairs": blind},
              open(os.path.join(out, "semantic_anchor_blind_pairs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"kind": "cce.semantic_anchor.key.v1", "seed": SEED,
               "★do_not_show_to_raters": "本文件是**解盲钥匙**, 评分完成前不得给评分者看",
               "key": key},
              open(os.path.join(out, "semantic_anchor_key.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"盲评对已写: {len(blind)} 对(无隐藏字段) · 解盲钥匙另存")
    print(f"L0b 对(一致性检查)共 {quota['L0b']} 对 —— 判成「有实质不同」的评分者数据不可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
