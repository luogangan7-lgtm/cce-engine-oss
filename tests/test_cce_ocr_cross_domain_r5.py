#!/usr/bin/env python3
"""跨内容域 OCR 第五轮(过滤器确证 + 跨域): keep_v3b 源码 sha 先于转写钉死; 帧是 r1–r4 都没看过的; I6 逐格前置闸 = H_filter;
闸不过 ⇒ 密度/域两个假设无判定; 注册表的数从产物现读; across_domains 不因 OCR 抽取层探针改动。

真值与素材在仓外, CI 不重测, 只验仓内产物的一致性与纯函数行为(过滤器源码 sha / keep_v3b / 同框前缀计数, 合成框)。
"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
PH = "tests/data/phase2/"
PRE, FZ, R = J(PH + "ocr_cross_domain_r5_prereg.json"), J(PH + "ocr_cross_domain_r5_gt_freeze.json"), J(PH + "ocr_cross_domain_r5.json")
G = R["instrument_gate"]
C = R["cells"]["keep_v3b"]["cells"]
sha = lambda p: hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()
import ocr_cross_domain_r5 as R5

# ① 过滤器/度量源码、密度文件、已看帧自检文件都是预注册钉死的那份; 真值是冻结那份; 标注者照实写
assert R5.filter_sha() == PRE["filter"]["source_sha256"] == R["filter_source_sha256"], "★ keep_v3b 调用链在预注册后被改过(那是 r6)"
assert R5.metric_sha() == PRE["metric"]["source_sha256"], "★ 1−CER 度量源码在预注册后被改过"
assert sha(PH + "ocr_cross_domain_r4_density.json") == PRE["density"]["r4_density_file_sha256"]
assert sha(PH + "ocr_cross_domain_r5_density.json") == PRE["density"]["r5_density_file_sha256"]
assert sha("probes/text_density_vision.swift") == PRE["density"]["swift_source_sha256"]
assert sha(PH + "ocr_cross_domain_r5_seencheck.json") == PRE["seen_frame_selfcheck"]["file_sha256"]
assert R["gt_sha256"] == FZ["gt_sha256"] and G["I3_gt_frozen"]
assert R["annotator"] == "Claude_single_non_human" and "非人类" in PRE["annotation"]["annotator"]
assert R["domains_chosen"] == PRE["domains"]["chosen"] and R["tier_edges"] == PRE["density"]["tier_edges"] == [30]
assert PRE["domains"]["selection_rule"] == J(PH + "ocr_cross_domain_r4_prereg.json")["domains"]["selection_rule"], "★ 选域规则须沿用第四轮"
for k in ("SESOI", "interval", "creator_robustness"):
    assert PRE["criterion"][k].split("seed")[0] == J(PH + "ocr_cross_domain_r4_prereg.json")["criterion"][k].split("seed")[0], k

# ② 需要仓外素材才能复算的闸由 run 现算
assert G["D3_density_files_frozen"] and G["D4_domains_as_preregistered"] and G["D5_density_recomputed_equal"]
assert G["F0_filter_source_pinned"] and G["M0_metric_source_pinned"] and G["I5_no_seen_frame"] and G["X1_new_frames_unchanged"]

# ③ 纯函数(合成框): keep_v3b 保住锚框左侧正文(keep_v3 会吃掉 ⇒ 能观察到失败); 同框前缀计数器认得这种版式
import ocr_cross_domain_r3 as R3, ocr_cross_domain_r4 as R4
rows = [("示例免责声明文字抖音号: demo0000001", [98, 732, 342, 25]), ("Q示例昵称", [349, 763, 88, 22])]
assert R3.keep_v3(rows, "示例昵称") == [] and R4.keep_v3b(rows, "示例昵称") == ["示例免责声明文字"]
assert R5.prefix_boxes(rows) == 1 and R5.prefix_boxes([("抖音号: demo0000001", None)]) == 0

# ④ 闸与判定一致: H_filter = 基础闸都过 且 逐格 I6 <= 上限; 任一不过 ⇒ 两个假设都是 INSTRUMENT_GATE_FAILED
I6 = R["I6_mean_acc_loss_vs_no_filter"]
assert set(I6) == {c for c, d in C.items() if d["per_frame"]}, "★ I6 必须逐格算(含 INSUFFICIENT 格)"
base_ok = all(v for k, v in G.items() if k != "I6_filter_preserves_text")
i6_ok = all(v <= R["I6_max"] == 0.02 for v in I6.values())
assert G["I6_filter_preserves_text"] == i6_ok
assert R["H_filter"] == ("INSTRUMENT_GATE_FAILED" if not base_ok else
                         "CONFIRMED_ON_UNSEEN_FRAMES" if i6_ok else "FAILED_ON_UNSEEN_FRAMES")
gate_ok = all(G.values())
assert (R["H_density"] == "INSTRUMENT_GATE_FAILED") == (not gate_ok) == (R["H_domain_given_density"] == "INSTRUMENT_GATE_FAILED")
if not gate_ok:
    assert "within_tier_pairs" not in R["verdicts"], "★ 闸不过却出了判定"
for c, d in C.items():
    n = d["n_text_frames"]
    assert d["status"] == ("OK" if n >= 45 else "OK_REDUCED" if n >= 20 else "INSUFFICIENT"), c
    if d["status"] == "INSUFFICIENT" and gate_ok:
        assert not any(c.split("|")[0] in k and k.startswith(c.split("|")[1]) for k in R["verdicts"]["within_tier_pairs"]), \
            f"★ {c} 不够数却进了档内比较"
assert R["cells_reaching_30"] == sorted(c for c, d in C.items() if d["n_text_frames"] >= 30)

# ⑤ 仓里不许有转写
ALLOWED = {"aweme_id", "frame", "sha256", "video", "creator", "source", "ref_zh_chars", "hyp_zh_chars", "acc_zh",
           "n_ocr_lines", "n_ocr_lines_after_watermark_filter", "n_anchor_prefix_boxes", "video_seen_r1_r4", "flags"}
for o in R["cells"].values():
    for d in o["cells"].values():
        for row in d["per_frame"]:
            assert set(row) <= ALLOWED, f"★ 逐帧记录多了字段: {set(row) - ALLOWED}"

# ⑥ 注册表的数从产物现读; across_domains 不因 OCR 抽取层探针改; P3 状态不动
CAPS = {c["id"]: c for c in J("config/cce_capability_registry_v1.json")["capabilities"]}
P3 = [p for p in J("config/cce_chain_conformance.json")["phases"] if p.get("phase") == "P3 Multimodal"][0]
texts = [CAPS[cid]["missing"][0] for cid in ("standalone_image_ingest", "video_multimodal_parse_v5")] + [P3["★condition"]]
for m in texts:
    assert "第五轮" in m and "非人类" in m and "across_domains" in m, "★ 第五轮段落缺失"
    for k in ("H_filter", "H_density", "H_domain_given_density"):
        assert f"{k} {R[k]}" in m, k
    assert f"I6 最大 {max(I6.values()):.3f}" in m
    for c, d in C.items():
        assert f"{c} r5 {d['acc_zh_mean']:.3f}(n={d['n_text_frames']})" in m, f"★ {c} 的读数与产物不符"
    if gate_ok and R["verdicts"]["cross_tier_sparse_vs_dense"]:
        cr = R["verdicts"]["cross_tier_sparse_vs_dense"]
        assert f"跨档差 {cr['mean_diff']:.3f} [{cr['ci90'][0]:.3f}, {cr['ci90'][1]:.3f}] {cr['verdict']}" in m
assert P3["status"] == "DONE_WITH_SCOPED_WITHHOLDING", "★ OCR 抽取层探针不许改 P3 状态"
assert "不因本探针改动" in PRE["writeback_rule"]["across_domains"]

print(f"test_cce_ocr_cross_domain_r5: OK (H_filter {R['H_filter']} | I6 max {max(I6.values()):.4f} | "
      f"H_density {R['H_density']} | H_dom|D {R['H_domain_given_density']} | "
      + " · ".join(f"{c} {d['acc_zh_mean']:.3f}(n={d['n_text_frames']})" for c, d in C.items()) + ")")
