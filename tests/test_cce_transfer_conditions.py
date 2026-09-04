#!/usr/bin/env python3
"""跨域标定: 扣发不变, 但理由从「不知道」升为「知道它不成立」。

## 变了什么
`across_domains = NOT_ESTABLISHED` 原来是**默认的保守态**(没测过所以不许搬)。
今天的抽取质量实测恰好就是转移性的证据 ⇒ 它变成**有实测支撑的结论**。

## ★ 但必须分清两个断言
我变化的是 **语言 / 场景密度 / 录音难度**, **不是「域」**(助听器 vs 生活方式 vs 广告)。
把「条件转移失败」说成「域转移失败」是两个不同的断言 —— 本测试就是钉住这个区分。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = json.load(open(os.path.join(ROOT, "tests/data/phase2/transfer_across_conditions.json"),
                   encoding="utf-8"))

# ── ① 每条转移失败都要由**真实产物**复核, 不信摘要 ─────────────────
ocr = json.load(open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_en.json"), encoding="utf-8"))
zh = json.load(open(os.path.join(ROOT, "tests/data/phase2/ocr_accuracy_real_zh.json"), encoding="utf-8"))
clean = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2.json"), encoding="utf-8"))
other = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_other.json"), encoding="utf-8"))

m = T["measured_transfer_failures"]
assert abs(m["language(OCR)"]["zh_real_cover"] - zh["acc_median"]) < 1e-6, "★ 中文数与产物不符"
assert abs(m["language(OCR)"]["en_dense_scene"]
           - ocr["word_f1_order_insensitive"]["median"]) < 1e-6, "★ 英文数与产物不符"
assert abs(m["difficulty(ASR)"]["test_clean_mean_wer"] - clean["wer"]["mean"]) < 1e-6
assert abs(m["difficulty(ASR)"]["test_other_mean_wer"] - other["wer"]["mean"]) < 1e-6
for k in ("language(OCR)", "difficulty(ASR)"):
    assert m[k]["ratio"] > 2.0, f"★ {k} 的倍数不足以支撑「转移不成立」"

# ── ② ★ 条件转移 ≠ 域转移, 这个区分必须写死 ────────────────────────
assert "不是「域」" in T["★what_this_does_NOT_establish"], \
    "★ 我变化的是语言/密度/难度, 不是域 —— 这条区分不许含糊"
assert "手抄" in T["★numbers_are_derived_not_transcribed"], \
    "★ 数字必须从产物现读 —— 手抄会漂移, 第一版就抄错了一位"
assert "远不足以判" in T["★what_this_does_NOT_establish"], \
    "★ 现有真实素材 6 张分 3 类, 每类 2 张, 必须写明不足以判"
assert "两个不同的断言" in T["★what_this_does_NOT_establish"]

# ── ③ 扣发不许因此放行 ──────────────────────────────────────────────
assert "保持 NOT_ESTABLISHED" in T["★consequence"], \
    "★ 有了证据是**更该**扣发, 不是可以放行了"
CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}
for cid in ("standalone_image_ingest", "video_multimodal_parse_v5"):
    assert "跨域标定" in " ".join(CAPS[cid]["missing"]), f"★ {cid}: 跨域标定不许被划掉"

# ── ④ 下一步要什么, 必须写明(否则「未测」永远只是个标签) ────────────
assert "带逐字标注" in T["★next_if_resumed"] and ">=30" in T["★next_if_resumed"]

print(f"test_cce_transfer_conditions: OK (三条轴上的转移失败均由**产物复核**: "
      f"语言 {m['language(OCR)']['ratio']}x · 难度 {m['difficulty(ASR)']['ratio']}x · "
      "合成 vs 真实 | ★ 我变的是语言/密度/难度**不是域** —— 两个断言不许混 | "
      "有了证据是**更该**扣发, across_domains 保持 NOT_ESTABLISHED | 下一步要什么已写明)")
