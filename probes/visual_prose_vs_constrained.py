#!/usr/bin/env python3
"""现有 VLM 视觉字段: 自由散文 vs 受约束输出的双模型一致度。零 API 调用。

## 为什么做这一支
「VLM 场景/对象识别」是图片链的未完成项。但**先翻已有数据**发现:
`cce_video_parse` 的 `visual` 字段**早就在产出** scene/persons/actions/objects/on_screen_text,
且有 **301 帧带两个模型**(M3 + Qwen3.8)。

## 它能说什么, 不能说什么
· **不能**当判据: 跨模型一致 != 重测信度; 且**跨模型共识闸 2026-08-18 已否决**(8 条理由)。
· **能**给方向: 若两个模型对同一帧的描述几乎不重叠, 那这个字段形态很难有可复现读数。
  这是**关门方向**(负结论), 低风险。

## ★ 中途我的测量坏过一次, 留作教训
第一版用 `re.findall(r'[一-鿿]{2,}')` 当中文分词 —— 中文无空格, 它抓出的是
**8–11 字的整句短语**(实测: '金属竖条栏杆围栏' / '背景中可见一头灰色大象'),
两个模型几乎不可能吐出一模一样的长短语 ⇒ Jaccard≈0.008 **是分词造出来的, 不是模型的分歧**。
与「零命中可能是零扫描」同族: **先验证测量本身, 再报数。**
现改用字符二元组(中文标准的免依赖做法)。
"""
import glob
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = "/Volumes/data/viral-skill-eval/results/video_parse"
OUT = ROOT / "tests" / "data" / "visual_prose_vs_constrained.json"
PROSE = ("scene", "persons", "actions", "objects")
CONSTRAINED = ("on_screen_text",)


def bigrams(s):
    if not isinstance(s, str):
        return set()
    zh = re.sub(r"[^一-鿿]", " ", s)
    g = {seg[i:i + 2] for seg in zh.split() for i in range(len(seg) - 1)}
    return g | {w.lower() for w in re.findall(r"[A-Za-z]{3,}", s)}


def run():
    J = defaultdict(list)
    for f in glob.glob(f"{SRC}/*.json"):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for _ts, per in (d.get("visual") or {}).items():
            if not isinstance(per, dict) or len(per) < 2:
                continue
            ms = list(per)[:2]
            a, b = per[ms[0]], per[ms[1]]
            if not (isinstance(a, dict) and isinstance(b, dict)):
                continue
            for k in PROSE + CONSTRAINED:
                ta, tb = bigrams(a.get(k)), bigrams(b.get(k))
                if ta and tb:
                    J[k].append(len(ta & tb) / len(ta | tb))
    per_field = {k: {"mean": round(statistics.mean(v), 4),
                     "median": round(statistics.median(v), 4), "n": len(v)}
                 for k, v in J.items() if v}
    prose = [x for k in PROSE for x in J.get(k, [])]
    cons = [x for k in CONSTRAINED for x in J.get(k, [])]
    return {"kind": "cce.visual.prose_vs_constrained.v1",
            "★status": "EXPLORATORY_directional_only",
            "★usable_for": "关门(说明自由散文字段难有可复现读数) —— **不得**当判据",
            "★why_not_a_gate": ("跨模型一致 != 重测信度; 且跨模型共识闸 2026-08-18 已否决(8 条理由)。"),
            "★tokenizer_bug_fixed": (
                "第一版用 [一-鿿]{2,} 当中文分词, 抓出的是 8–11 字整句短语, "
                "Jaccard≈0.008 是分词造出来的。已改字符二元组。**先验证测量本身, 再报数。**"),
            "per_field": per_field,
            "prose": {"mean": round(statistics.mean(prose), 4), "n": len(prose)} if prose else None,
            "constrained": {"mean": round(statistics.mean(cons), 4), "n": len(cons)} if cons else None,
            "ratio_constrained_over_prose": (round(statistics.mean(cons) / statistics.mean(prose), 2)
                                             if prose and cons else None)}


def main():
    r = run()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'字段':<18}{'双模型 Jaccard 均值':>20}{'中位':>9}{'样本':>7}")
    for k, v in r["per_field"].items():
        tag = "(受约束)" if k in CONSTRAINED else "(散文)"
        print(f"{k + tag:<18}{v['mean']:>20.3f}{v['median']:>9.3f}{v['n']:>7}")
    print(f"\n散文合计 {r['prose']['mean']} vs 受约束 {r['constrained']['mean']} "
          f"⇒ **受约束高 {r['ratio_constrained_over_prose']} 倍**")
    print(f"★ {r['★status']} —— {r['★usable_for']}")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
