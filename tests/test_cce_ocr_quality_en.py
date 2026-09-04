#!/usr/bin/env python3
"""英文 OCR 抽取质量 —— 从 BLOCKED 变成有实测, 以及一条**预注册判据不可执行**的如实记录。

## 我错在哪
原来登记「需英文域的带标注素材 ⇒ BLOCKED_EXTERNAL」。
我把「需要标注素材」理解成「需要**本域**的标注素材」。但本项目自己的分解是
**能力=域无关 / 抽取质量=语言相关 / 标定=域相关** —— 抽取质量既然只跟语言有关,
公开英文基准就是正确的素材。**这是分类错误, 不是资源短缺。**

## 三个数配成区间, 不给点估计
合成干净渲染 1.000(上界) > 真实中文封面 0.900 > 英文密集场景文字 0.317(下界)

## 两处「先验仪器」
① 顺序无关的词级 F1: 序列编辑距离对**我的拼接顺序**极敏感, 只报它会把我的拼接当成 OCR 的错
② 独立第二引擎: 预注册判据「与公开报告值比对」在 RapidOCR×TextOCR 上**无公开值、不可执行**
   ⇒ 如实记下, 并**追加**(不是替换)一个等价自检: 同 100 张图 tesseract 只有 0.0/均值 0.079
   ⇒ 我的集成没坏, 是基准难
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_en.json"), encoding="utf-8"))
P = json.load(open(os.path.join(ROOT, "tests/data/phase2/extraction_quality_en_prereg.json"),
                   encoding="utf-8"))

# ── ① 预注册必须早于结果, 且判据不是我拍的线 ─────────────────────────
assert P["★frozen_before_measurement"], "★ 预注册必须声明冻结在测量前"
assert "不设我自己拍的合格线" in P["★criterion_is_not_a_threshold_i_invented"]["rule"]

# ── ② 判据不可执行这件事必须留在产物里 ───────────────────────────────
assert "不可执行" in D["★criterion_as_written_was_unexecutable"], \
    "★ 判据执行不了就要说执行不了, 不许偷偷换一个"
x = D["independent_engine_crosscheck"]
assert "追加" in x["★status"] and "不是替换" in x["★status"], \
    "★ 交叉检查是**追加**的, 不得写成替代预注册判据"
assert x["word_f1"]["median"] < D["word_f1_order_insensitive"]["median"], \
    "★ 第二引擎若不比本管道差, 「我的集成没坏」这个结论就不成立"

# ── ③ 两档 profile 都要在, 且不许合成一个数 ──────────────────────────
for k in ("raw", "normalized", "word_f1_order_insensitive"):
    assert k in D and "median" in D[k], f"★ 缺 {k}"
assert "不合成一个" in D["★why_two_profiles"], "★ 不同 benchmark 的归一化不许合并成一个标准数"
assert "★why_word_f1" in D, "★ 为什么要顺序无关指标, 理由要留在原地"

# ── ④ 报区间不报点估计 ──────────────────────────────────────────────
w = D["★what_this_number_is_and_is_not"]
assert "下界" in w and "上界" in w and "0.900" in w, \
    "★ 三个数要配成区间: 合成上界 / 真实中文 / 英文密集场景下界"
assert D["degeneracy_pass"], "★ 逐图无变异 ⇒ 中位数没有信息量"
assert D["dontcare_excluded"] > 0, "★ TextOCR 的 don't-care 项要被排除并计数"

# ── ⑤ 语料不许进仓 ──────────────────────────────────────────────────
for bad in ("textocr_val_images", "LibriSpeech", ".jpg", ".wav"):
    assert not any(bad in f for f in os.listdir(os.path.join(ROOT, "tests/data/phase2"))), \
        f"★ 语料/媒体不许进仓: {bad}"

# ── ⑥ 英文测了 ≠ 跨域标定成立 ───────────────────────────────────────
assert "NOT_ESTABLISHED" in D["★still_not_established"], \
    "★ 抽取质量与跨域标定是两件事, 不许一起划掉"

print(f"test_cce_ocr_quality_en: OK (TextOCR v0.1 val CC BY 4.0, n={D['n_images']} | "
      f"RAW {D['raw']['median']} / NORM {D['normalized']['median']} / "
      f"**顺序无关词级F1 {D['word_f1_order_insensitive']['median']}** | "
      f"独立引擎 {x['engine']} 仅 {x['word_f1']['median']}(均值 {x['word_f1']['mean']}) ⇒ 集成没坏 | "
      "★ 预注册判据无公开值**不可执行**, 已如实记并追加自检 | "
      "区间: 合成 1.000 > 真实中文 0.900 > 英文密集场景 0.317)")
