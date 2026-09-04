#!/usr/bin/env python3
"""真实素材上的 OCR 准确率: 中文有 n=6 估计了, 英文仍 BLOCKED —— 两者不许混为「已测」。

## 为什么这条测试值得存在
「抽取质量未测」这一项在清单上挂了很久。现在中文域有实测了, 最容易犯的错是
顺手把整项划掉 —— 而英文域**一张标注素材都没有**, 且该能力被登记为**语言相关**。

## 标注不在本仓
含屏幕上的创作者名与水印。本仓只有聚合数字与文件名, 没有转写。
缺席时(CI)本测试**不重测**, 只验「已记录的结论仍在且自洽 + 英文仍在 missing」。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
P = os.path.join(ROOT, "tests/data/phase2/ocr_accuracy_real_zh.json")
D = json.load(open(P, encoding="utf-8"))

# ── ① 产物里不许有转写(那是识别层数据) ──────────────────────────────
_blob = json.dumps(D, ensure_ascii=False)
for row in D["per_image"]:
    assert set(row) <= {"file", "kind", "acc", "ref_chars", "hyp_chars", "n_got",
                        "hallucinated"}, f"★ 逐图记录多了字段, 可能夹带转写: {row}"
assert "鹤立" not in _blob and "神物" not in _blob, "★ 产物里出现了转写内容 —— 那是识别层数据"

# ── ② 零文字对照必须在 ───────────────────────────────────────────────
assert D["n_blank_control"] >= 1, \
    "★ 必须有零文字对照 —— 只看「读到的对不对」会漏掉**无中生有**这一整类错"
assert D["hallucinated_on_blank"] == 0, \
    f"★ 零文字图上读出了东西: {D['hallucinated_on_blank']} 次"

# ── ③ 报分布不报单点 ────────────────────────────────────────────────
assert D["acc_min"] is not None and D["acc_max"] is not None, "★ 必须报范围"
assert D["acc_max"] - D["acc_min"] > 0.2, \
    "★ 若逐图准确率几乎无差异, 中位数就没有信息量 —— 检查是不是素材太同质"
assert "不得当作稳定基线" in D["★n_is_small"], "★ n 小这件事要留在产物里"

# ── ④ 合成上界必须 >= 真实中位(否则「上界」这个说法就错了) ───────────
CURVE = json.load(open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_curve.json"),
                       encoding="utf-8"))
_upper = CURVE["by_language"]["zh"]["jpeg_quality"]["curve"][0]["acc_median"]
assert _upper >= D["acc_median"], \
    f"★ 合成「上界」{_upper} 低于真实中位 {D['acc_median']} —— 那它就不是上界, 框架错了"

# ── ⑤ 中文测了 ≠ 整项测了 ───────────────────────────────────────────
CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}
for cid in ("standalone_image_ingest", "video_multimodal_parse_v5"):
    _m = " ".join(CAPS[cid]["missing"])
    assert "抽取质量" in _m, f"★ {cid}: 中文有 n=6 估计**不等于**整项已测, 不许划掉"
    assert "英文" in _m, f"★ {cid}: 必须写明卡住的是英文域"

print(f"test_cce_ocr_accuracy_real: OK (真实中文 n={D['n_with_text']} 中位 {D['acc_median']} "
      f"范围 {D['acc_min']}–{D['acc_max']} | 零文字对照无中生有 {D['hallucinated_on_blank']} 次 | "
      f"合成上界 {_upper} >= 真实中位 ⇒ 上界框架成立 | "
      "★ 英文域仍无标注素材, 仍在 missing | 产物零转写(标注留在保险库))")
