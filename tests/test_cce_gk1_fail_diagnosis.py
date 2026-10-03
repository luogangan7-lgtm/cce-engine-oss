"""G-K1 在真实端到端(2026-10-01)没过的诊断 —— 结论必须能从落盘数字现算出来。

钉住四句话, 任何一句不成立就红:
  ① 两次运行是同一台仪器(闸协议 v2 同 hash、同 81 条、同 5 人、同截断), 且重算复现两份落盘值
  ② 0.2422 → 0.2601 的差**分不出噪声**: 条目配对自助 95% 区间含 0
  ③ 差几乎全来自 Text-01 的四个对; 留一去掉 Text-01 两次都 < 0.25
  ④ Text-01 离盲规则离群线只差 <0.001 —— 过/不过取决于这根刀刃
识别层原始数据(仓外)在本机时额外现算复核; 不在(如 CI)时只核落盘文件的内部一致性。
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "tests/data/gk1_fail_diagnosis_2026-10-03.json")
VAULT = "/Volumes/data/cce-identified-vault/cce_runs/gate_v2_acceptance/raw_annotations.json"


def _d():
    return json.load(open(DOC, encoding="utf-8"))


def test_same_instrument_and_recompute_matches():
    d = _d()
    c = d["②comparability_run_params(A, B)"]
    for k, (a, b) in c.items():
        assert a == b, f"★ 两次运行 {k} 不同 ⇒ 不可比, 诊断前提不成立"
    r = d["①instrument_check_recompute_equals_stored"]
    assert r["A_recomputed"] == r["A_stored"] == 0.2422 and r["B_recomputed"] == r["B_stored"] == 0.2601


def test_difference_is_not_distinguishable_from_noise():
    lo, hi = _d()["⑨item_cluster_bootstrap"]["paired_diff_B_minus_A_CI95"]
    assert lo < 0 < hi, "★ 配对差区间不含 0 ⇒ 不能再说「这次不过是噪声」, 要另查回归"


def test_text01_drives_the_shift_and_loo_passes_both_runs():
    d = _d()
    assert d["③headline"]["Text01_share_of_delta"] > 0.9
    loo = d["⑧leave_one_annotator_out_mean_JS"]["MiniMax-Text-01"]
    assert loo["A"] < 0.25 and loo["B"] < 0.25
    for m, v in d["⑧leave_one_annotator_out_mean_JS"].items():
        if m != "MiniMax-Text-01":
            assert v["B"] > 0.25, f"★ 去掉 {m} 也能过 ⇒ 「主要由 Text-01 驱动」这句要改"


def test_outlier_rule_knife_edge():
    o = _d()["⑥outlier_rule_median_plus_2SD"]
    assert o["excluded_B"] == [] and 0 < o["B_Text01_margin_below_cut"] < 0.001


def test_both_runs_fail_an_interval_criterion():
    b = _d()["⑨item_cluster_bootstrap"]
    assert b["A_CI95"][1] > 0.25 and b["B_CI95"][1] > 0.25, \
        "★ 若某次区间上界 <=0.25, 「区间判据下两次都不过」这句要改"


def test_recompute_from_vault_when_available():
    if not os.path.exists(VAULT):
        return   # CI 上没有识别层; 落盘数字已由上面几条核过
    before = open(DOC, "rb").read()
    subprocess.run([sys.executable, "-B", os.path.join(ROOT, "probes/gk1_fail_diagnosis.py")],
                   check=True, capture_output=True)
    assert open(DOC, "rb").read() == before, "★ 现算结果与落盘文件不一致 —— 有人改了数据或探针"


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("test_cce_gk1_fail_diagnosis: OK")
