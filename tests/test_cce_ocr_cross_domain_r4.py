#!/usr/bin/env python3
"""跨内容域 OCR 第四轮(按文字密度分层): 密度量与被测 OCR/真值无关且先于转写冻结; 仪器闸(含逐格 I6)不过 ⇒ 无判定;
事后探索只描述; 注册表的数从产物现读; 判不了 ⇒ 扣发不放行, across_domains 不动。

真值与素材在仓外, CI 不重测, 只验仓内产物的一致性与纯函数行为(density / tier / keep_v3b, 合成框, 不调 Vision 与 OCR)。
"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
PH = "tests/data/phase2/"
PRE, FZ, R = J(PH + "ocr_cross_domain_r4_prereg.json"), J(PH + "ocr_cross_domain_r4_gt_freeze.json"), J(PH + "ocr_cross_domain_r4.json")
G = R["instrument_gate"]
C = R["cells"]["v3_bounded"]["cells"]
sha = lambda p: hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()

# ① 密度文件/仪器源码就是预注册冻结的那份; 真值是冻结那份; 标注者照实写
assert sha(PH + "ocr_cross_domain_r4_density.json") == PRE["density"]["density_file_sha256"], "★ 密度文件在预注册后被改过"
assert sha("probes/text_density_vision.swift") == PRE["density"]["swift_source_sha256"], "★ 密度仪器源码在预注册后被改过"
assert R["gt_sha256"] == FZ["gt_sha256"] and G["I3_gt_frozen"]
assert R["annotator"] == "Claude_single_non_human" and "非人类" in PRE["annotation"]["annotator"]
assert R["domains_chosen"] == PRE["domains"]["chosen"] and R["tier_edges"] == PRE["density"]["tier_edges"] == [30]
assert "RapidOCR" in PRE["density"]["★independence"] and "真值" in PRE["density"]["★independence"]

# ② 选域需要仓外 meta 才能复算 —— 由 run 的闸 D4_domains_as_preregistered 现算
assert G["D4_domains_as_preregistered"] and G["D3_density_file_frozen"] and G["D5_density_recomputed_equal"]

# ③ 纯函数行为(合成框): 水印块不计入密度; 档界; keep_v3b 保住锚框左侧正文而 keep_v3 会吃掉(能观察到失败)
import ocr_cross_domain_r4 as R4
wm = [[16, 14, 90, 32, 3, 1], [8, 56, 168, 20, 15, 1], [10, 84, 78, 20, 5, 0], [40, 300, 300, 30, 12, 0]]
assert R4.density(wm) == (12, 1, 3), R4.density(wm)
assert R4.density([b[:5] + [0] for b in wm])[0] == 35          # 不排除水印时会多算 ⇒ 排除逻辑真在起作用
assert [R4.tier(x, [30]) for x in (0, 29, 30, 200)] == ["SPARSE", "SPARSE", "DENSE", "DENSE"]
import ocr_cross_domain_r3 as R3
rows = [("示例免责声明文字抖音号: demo0000001", [98, 732, 342, 25]), ("Q示例昵称", [349, 763, 88, 22])]
assert R3.keep_v3(rows, "示例昵称") == [], "keep_v3 的已知缺陷(本轮 I6 不过的根因)应能复现"
assert R4.keep_v3b(rows, "示例昵称") == ["示例免责声明文字"]

# ④ 闸与判定一致: 任一闸不过 ⇒ 两个假设都是 INSTRUMENT_GATE_FAILED, verdicts 里没有对
assert G["I6_filter_preserves_text"] == all(v <= R["I6_max"] for v in R["I6_mean_acc_loss_vs_no_filter"].values())
assert set(R["I6_mean_acc_loss_vs_no_filter"]) == set(C), "★ I6 必须逐格算"
gate_ok = all(G.values())
assert (R["H_density"] == "INSTRUMENT_GATE_FAILED") == (not gate_ok) == (R["H_domain_given_density"] == "INSTRUMENT_GATE_FAILED")
if not gate_ok:
    assert "within_tier_pairs" not in R["verdicts"], "★ 闸不过却出了判定"
    E = R["exploratory_post_hoc"]
    assert E and E["role"].startswith("EXPLORATORY_POST_HOC") and "不作判定" in E["role"]
for c, d in C.items():
    n = d["n_text_frames"]
    assert d["status"] == ("OK" if n >= 45 else "OK_REDUCED" if n >= 20 else "INSUFFICIENT"), c

# ⑤ 仓里不许有转写
ALLOWED = {"aweme_id", "frame", "sha256", "video", "creator", "ref_zh_chars", "hyp_zh_chars", "acc_zh",
           "acc_en", "ref_en_chars", "n_ocr_lines", "n_ocr_lines_after_watermark_filter", "flags"}
for o in R["cells"].values():
    for d in o["cells"].values():
        for row in d["per_frame"]:
            assert set(row) <= ALLOWED, f"★ 逐帧记录多了字段: {set(row) - ALLOWED}"

# ⑥ 注册表的数从产物现读; 判不了 ⇒ 扣发不放行, across_domains 不因 OCR 改
CAPS = {c["id"]: c for c in J("config/cce_capability_registry_v1.json")["capabilities"]}
P3 = [p for p in J("config/cce_chain_conformance.json")["phases"] if p.get("phase") == "P3 Multimodal"][0]
texts = [CAPS[cid]["missing"][0] for cid in ("standalone_image_ingest", "video_multimodal_parse_v5")] + [P3["★condition"]]
for m in texts:
    assert "第四轮" in m and "非人类" in m and "across_domains" in m and R["H_density"] in m
    for c, v in R["I6_mean_acc_loss_vs_no_filter"].items():
        if v > R["I6_max"]:
            assert f"{c} {v:.3f}" in m
    if not gate_ok:
        for c, v in R["exploratory_post_hoc"]["acc_zh_mean"].items():
            assert f"{c} r4 {v:.3f}" in m, f"★ {c} 的探索读数与产物不符"
        cr = R["exploratory_post_hoc"]["verdict_shaped_readout"]["cross_tier_sparse_vs_dense"]
        assert f"{cr['mean_diff']:.3f} [{cr['ci90'][0]:.3f}, {cr['ci90'][1]:.3f}]" in m
        assert "不作判定" in m
if R["H_density"] != "SUPPORTED" or R["H_domain_given_density"] != "NO_RESIDUAL_DOMAIN_EFFECT_WITHIN_DELTA":
    assert P3["status"] == "DONE_WITH_SCOPED_WITHHOLDING", "★ 判不了不许改 P3 状态"
assert "不因本探针改动" in PRE["writeback_rule"]["across_domains"]

print(f"test_cce_ocr_cross_domain_r4: OK (gate_ok={gate_ok} | H_density {R['H_density']} | "
      + " · ".join(f"{c} {d['acc_zh_mean']:.3f}(n={d['n_text_frames']})" for c, d in C.items()) + ")")
