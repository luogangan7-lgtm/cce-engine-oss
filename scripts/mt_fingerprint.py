#!/usr/bin/env python3
"""量一份机翻英文的「翻译器指纹」，判断 style_check.py 的 --translated 档还能不能直接用。

背景（决定这个脚本存在的理由）：
`--translated` 档不是放宽标准，是换对基准。它的基准是拿 DeepL 实测标定的 ——
**DeepL 会把中文逗号停顿系统性转成 em dash**，实测 321 词出 8 处、412 词出 10 处，
所以该档不清洗 em dash（真人用翻译工具后不会回头逐个改标点，清洗本身才不自然）。

换翻译器 = 换仪器。若新翻译器根本不产 em dash，那 `--translated` 档在它身上
既没有必要也没有依据；若产出密度差一个量级，阈值也不能沿用。

**这个脚本不判译文好坏。** 译文质量要人读，它只回答「基准能不能沿用」。

用法: mt_fingerprint.py <译文.txt> [--label 名称]
"""
import argparse
import json
import re
import sys
from pathlib import Path

# DeepL 实测锚点（来源：2026-08-11 中文起草+机翻工作流实测，两份稿）
DEEPL = {"samples": [(321, 8), (412, 10)]}
DEEPL_EM_PER_KW = sum(n for _, n in DEEPL["samples"]) / sum(w for w, _ in DEEPL["samples"]) * 1000
# 真人基准（style_check.py 同一份 104 条语料）
HUMAN_CONTRACTION = 0.793
HUMAN_EM_PER_KW = 1.0

CONTRACTIBLE = re.compile(
    r"\b(?:it is|that is|there is|they are|we are|you are|i am|do not|does not|did not|"
    r"is not|are not|was not|were not|will not|would not|cannot|can not|could not|"
    r"should not|have not|has not|had not|i will|you will|we will|they will|i have|"
    r"you have|we have|they have|i would|you would|let us)\b", re.I)
CONTRACTION = re.compile(r"\b\w+['’](?:s|t|re|ve|ll|d|m)\b", re.I)


def measure(text: str) -> dict:
    words = len(text.split())
    em = text.count("—") + text.count("–")
    contracted = len(CONTRACTION.findall(text))
    expandable = len(CONTRACTIBLE.findall(text))
    total = contracted + expandable
    return {
        "words": words,
        "em_dashes": em,
        "em_per_kw": round(em / words * 1000, 2) if words else 0.0,
        "contraction_rate": round(contracted / total, 3) if total else None,
        "contraction_sample": total,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--label", default="candidate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = args.path.read_text(encoding="utf-8").strip()
    if not text:
        print("译文为空 —— 上游翻译步骤没产出，不是指纹问题", file=sys.stderr)
        return 2
    m = measure(text)

    # 判据：em dash 密度与 DeepL 是否同量级（0.5x–2x 视为可沿用）
    ratio = m["em_per_kw"] / DEEPL_EM_PER_KW if DEEPL_EM_PER_KW else 0.0
    reusable = 0.5 <= ratio <= 2.0

    if args.json:
        print(json.dumps({**m, "deepl_em_per_kw": round(DEEPL_EM_PER_KW, 2),
                          "ratio_vs_deepl": round(ratio, 2),
                          "translated_profile_reusable": reusable}, ensure_ascii=False, indent=1))
        return 0

    print(f"翻译器指纹 · {args.label}")
    print(f"  译文长度        {m['words']} 词")
    print(f"  em dash         {m['em_dashes']} 处 = {m['em_per_kw']}/千词")
    print(f"  DeepL 实测锚点  {DEEPL_EM_PER_KW:.2f}/千词 (321词8处 + 412词10处)")
    print(f"  真人基准        约 {HUMAN_EM_PER_KW}/千词")
    if m["contraction_rate"] is None:
        print(f"  缩写占比        判不了(样本 0) —— 译文里既无缩写也无可缩写形")
    else:
        print(f"  缩写占比        {m['contraction_rate']:.1%} (样本 {m['contraction_sample']}) · 真人 {HUMAN_CONTRACTION:.1%}")
    print()
    print(f"  与 DeepL 的比值  {ratio:.2f}×")
    if reusable:
        print("  → --translated 档可沿用（同量级）")
    elif ratio < 0.5:
        print("  → --translated 档**不适用**：该翻译器几乎不产 em dash，")
        print("     沿用等于给它开一道它根本不需要的豁免。应按直接起草档判，或单独标定。")
    else:
        print("  → --translated 档**需重标定**：em dash 密度显著高于 DeepL，")
        print("     沿用会让阈值形同虚设。")
    print()
    print("  注：本脚本不判译文质量，只判基准能否沿用。质量要人读。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
