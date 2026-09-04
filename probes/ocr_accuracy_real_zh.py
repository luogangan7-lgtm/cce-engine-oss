#!/usr/bin/env python3
"""真实素材上的中文 OCR 准确率 —— n=6, 单标注者。

## 与 ocr_quality_curve 的分工
· ocr_quality_curve: 合成图 + 受控退化 ⇒ **上界曲线**(真实只会更差)
· 本探针: **真实素材** + 人工逐字标注 ⇒ 中文域的实际准确率, n=6

## 标注为什么不在这个仓里
标注含屏幕上的创作者名与水印(识别层数据)。边界闸是文本闸, 这些字一旦进公开仓就是明文泄露。
⇒ 标注在 /Volumes/data/cce-identified-vault/annotations/, 本仓只落**聚合数字**, 不落转写。
★ 缺席时(CI / 别的机器)本探针**不出结论**, 也不降级成「合成图那条曲线」—— 那是两件事。

## 单标注者为什么可以
转写是**有客观答案**的任务。语义 SESOI 需要 >=3 名评分者是因为要聚合主观判断; 逐字转写不需要。
★ 但 n=6 很小 ⇒ 报**逐张分布**, 不报一个均值当基线。

## 一个零文字对照
life_kitchen.jpg 图上确实没有字。它检验的是 OCR 会不会**无中生有** ——
只看「读到的对不对」会漏掉这一类错。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GT = "/Volumes/data/cce-identified-vault/annotations/ocr_ground_truth_zh_v1.json"
MATERIAL = "/Volumes/data/viral-skill-eval/assets/image-text"


def _cer(ref: str, hyp: str) -> float:
    import difflib
    if not ref:
        return 0.0 if not hyp else 1.0
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    return max(0.0, min(1.0, 1.0 - sum(b.size for b in sm.get_matching_blocks()) / len(ref)))


def run():
    if not (os.path.exists(GT) and os.path.isdir(MATERIAL)):
        return None
    import cce_image_ingest as II
    spec = json.load(open(GT, encoding="utf-8"))
    rows, accs, hallucinated = [], [], 0
    for it in spec["items"]:
        p = os.path.join(MATERIAL, it["file"])
        if not os.path.exists(p):
            continue
        vo = II.visual_observation(p)
        got = [o["value"] for o in vo["observations"] if o["channel"] == "ocr_text"]
        ref = "".join(it["lines"]).replace(" ", "")
        hyp = "".join(got).replace(" ", "")
        if not ref:
            # 零文字对照: 读出任何东西都是无中生有
            hall = len(hyp) > 0
            hallucinated += hall
            rows.append({"file": it["file"], "kind": "零文字对照",
                         "acc": None, "hallucinated": hall, "n_got": len(got)})
            continue
        acc = round(1.0 - _cer(ref, hyp), 3)
        accs.append(acc)
        rows.append({"file": it["file"], "kind": "有文字", "acc": acc,
                     "ref_chars": len(ref), "hyp_chars": len(hyp), "n_got": len(got)})
    import statistics
    return {"block": "OCR_ACCURACY_REAL_ZH_GEN1", "measured_at": "2026-09-04",
            "language": "zh", "n_with_text": len(accs), "n_blank_control": len(rows) - len(accs),
            "per_image": rows,                       # ★ 只有文件名与数字, 无转写
            "acc_median": round(statistics.median(accs), 3) if accs else None,
            "acc_min": min(accs) if accs else None, "acc_max": max(accs) if accs else None,
            "hallucinated_on_blank": hallucinated,
            "★n_is_small": "n=6(其中 1 张零文字对照) ⇒ 区间宽, **不得当作稳定基线**",
            "★single_annotator": "转写有客观答案, 单标注者可; 但与语义评分不同, 不可类推",
            "★english_still_blocked": "英文域仍无标注素材 ⇒ 那一项仍 BLOCKED"}


def main():
    r = run()
    if r is None:
        print(f"★ 标注或素材不在本机({GT}) —— 本探针只在本机成立, **不出结论**, "
              "也不降级成合成图那条曲线(那是两件事)。")
        return 2
    print(f"真实素材中文 OCR 准确率 · n={r['n_with_text']} 有文字 + "
          f"{r['n_blank_control']} 零文字对照\n" + "-" * 66)
    for row in r["per_image"]:
        if row["kind"] == "零文字对照":
            print(f"  {row['file']:22} 零文字对照 · 无中生有={row['hallucinated']} "
                  f"(读出 {row['n_got']} 条)")
        else:
            print(f"  {row['file']:22} 准确率 {row['acc']:.3f} "
                  f"(参考 {row['ref_chars']} 字 / 读到 {row['hyp_chars']} 字)")
    print("-" * 66)
    print(f"中位 {r['acc_median']} · 范围 {r['acc_min']}–{r['acc_max']} · "
          f"零文字上无中生有 {r['hallucinated_on_blank']} 次")
    print(f"★ {r['★n_is_small']}")
    print(f"★ {r['★english_still_blocked']}")
    out = os.path.join(ROOT, "tests/data/phase2/ocr_accuracy_real_zh.json")
    json.dump(r, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
