#!/usr/bin/env python3
"""跨内容域 OCR 第二轮: 预注册主分析因仪器闸不过而作废 —— 探索性结果不许冒充判定。

真值在仓外, CI 不重测, 只验: 仪器闸不过 ⇒ 主分析无判定; 闸过的那份判定可由区间复算;
探索性结果标明事后; 仓里没有转写; 注册表的数从产物现读; 扣发不放行。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
PRE = J("tests/data/phase2/ocr_cross_domain_r2_prereg.json")
FZ = J("tests/data/phase2/ocr_cross_domain_r2_gt_freeze.json")
R = J("tests/data/phase2/ocr_cross_domain_r2.json")
G = R["instrument_gate"]

# ① 真值是冻结那份, 标注者照实写, 新样本不含第一轮帧
assert R["gt_sha256"] == FZ["gt_sha256"] and G["I3_gt_frozen"], "★ 跑 OCR 用的真值不是冻结的那份"
assert R["annotator"] == "Claude_single_non_human" and "非人类" in PRE["annotation"]["annotator"]
assert G["I5_no_round1_frame"], "★ 第二轮混进了第一轮看过的帧"
assert G["I0_readback"] and G["I2_versions"], "★ 仪器读不回已知原文 / 版本不对"

# ② 闸不过 ⇒ 无判定(主分析); 主过滤器 v2 吃真值文字这件事必须留在产物里
v2 = R["by_filter"]["v2_anchor"]
assert not G["I6_filter_preserves_text[v2_anchor]"], "★ 预期 v2 在 t=0 帧吃字; 若通过需重查 I6"
assert v2["overall"] == v2["H2_subset"] == R["overall"] == "INSTRUMENT_GATE_FAILED" and not v2["pairs"], \
    "★ 仪器闸不过却出了判定"
assert max(v2["I6_mean_acc_loss_vs_no_filter"].values()) > 0.02
assert "事后" in R["★I6_added_after_ocr"] and "不在预注册" in R["★I6_added_after_ocr"]

# ③ 有判定的那份: 判定由区间复算; 留一创作者不稳则降级; 只算够数的域
def judge(lo, hi, dl=0.10):
    return ("TRANSFERABLE" if -dl < lo and hi < dl else
            "NOT_TRANSFERABLE" if lo > dl or hi < -dl else "INCONCLUSIVE")


v1 = R["by_filter"]["v1_prereg_r1"]
assert v1["role"].startswith("EXPLORATORY_POST_HOC"), "★ v1 预注册为只描述, 拿来看必须标事后探索"
ok = {k for k, d in v1["domains"].items() if d["status"] != "INSUFFICIENT"}
assert v1["domains"]["游戏解说"]["status"] == "INSUFFICIENT" and v1["domains"]["游戏解说"]["n_text_frames"] < 60
for k, p in v1["pairs"].items():
    assert set(k.split("|")) <= ok, f"★ {k}: INSUFFICIENT 的域不许进对比"
    assert p["verdict_raw"] == judge(*p["ci90"]) and p["verdict"] == (p["verdict_raw"] if p["loco_all_same"] else "INCONCLUSIVE")
assert v1["overall"] == "STILL_UNDETERMINED", "★ 有域 INSUFFICIENT 且无不可搬对 ⇒ 只能是 STILL_UNDETERMINED"

# ④ 仓里不许有转写
ALLOWED = {"aweme_id", "frame", "sha256", "video", "creator", "ref_zh_chars", "hyp_zh_chars", "acc_zh",
           "acc_en", "ref_en_chars", "n_ocr_lines", "n_ocr_lines_after_watermark_filter", "flags"}
for o in R["by_filter"].values():
    for d in o["domains"].values():
        for row in d["per_frame"]:
            assert set(row) <= ALLOWED, f"★ 逐帧记录多了字段: {set(row) - ALLOWED}"

# ⑤ 注册表的数从产物现读; 无确证结论 ⇒ 扣发不放行
CAPS = {c["id"]: c for c in J("config/cce_capability_registry_v1.json")["capabilities"]}
for cid in ("standalone_image_ingest", "video_multimodal_parse_v5"):
    m = CAPS[cid]["missing"][0]
    assert R["overall"] in m and "不作判定" in m and "非人类" in m
    for k, d in v1["domains"].items():
        assert f"{k} r2 {d['acc_zh_mean']:.3f}" in m, f"★ {cid}: {k} 的数与产物不符"
    for k, x in v2["I6_mean_acc_loss_vs_no_filter"].items():
        assert f"{k} {x:.3f}" in m
P3 = [p for p in J("config/cce_chain_conformance.json")["phases"] if p.get("phase") == "P3 Multimodal"][0]
assert "第二轮" in P3["★condition"] and "p3.cross_domain_calibration" in P3["★condition"]
assert P3["status"] == "DONE_WITH_SCOPED_WITHHOLDING", "★ 无确证结论不许改 P3 状态"

print(f"test_cce_ocr_cross_domain_r2: OK (主分析 {R['overall']}: v2 过滤 t=0 帧吃字 "
      + " · ".join(f"{k} −{x:.3f}" for k, x in v2["I6_mean_acc_loss_vs_no_filter"].items())
      + f" | 游戏 n={v1['domains']['游戏解说']['n_text_frames']}<60 INSUFFICIENT | 探索 H2 {v1['H2_subset']}(不作判定) | 扣发不放行)")
