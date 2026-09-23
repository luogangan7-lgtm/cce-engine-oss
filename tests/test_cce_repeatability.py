"""重复性的三条发现必须**在测试时重算** —— 零 API。

## 三条
① **G-K1 通过不是二值事实**: 自助 10000 次, 用 run1 的 4 人面板有 **23%** 不过, 全部来自 JS。
② **资格考是抽签**: 同一份 5 题考卷三次跑出 3/5、5/5、4/5。
③ **那次剔除损害了指标**: 剔 M2.7 的 4 人面板失败率 23%, 保留它的 5 人面板 7%。

★ 本闸不重跑自助(1 万次 ×2 面板要几分钟), 而是校验**落盘的数字与产物一致**,
  并把「余量薄」「区间跨阈值」这两个**结构性性质**钉住 —— 一旦它们变好, 断言会红并提醒更新。
"""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BS = ROOT / "tests/data/gk1_bootstrap.json"
REP = ROOT / "tests/data/run_a_repeatability_result.json"
QUAL = ROOT / "tests/data/qualification_exam_resolution.json"
R1 = ROOT / "accuracy/out/gates_result.json"
# ★ run2 的产物在**识别层保险库**(语料含真实 handle), 不在公开仓。
#   缺席时**只跑**能从仓内数据验的那几条, 并在末行明写「无本机素材, 未比对 run2 产物」——
#   ★ 静默跳过是不行的: 那会让「本机绿 / CI 也绿」与「本机绿 / CI 其实没验」不可区分。
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/run_a_repeat/gates_result.json")
HAVE_VAULT = os.path.exists(VAULT)

_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_bootstrap_numbers_match_the_products():
    """★ 落盘的自助结果必须与两次运行的点估一致 —— 否则文档会悄悄脱节。"""
    b, g1 = _j(BS), _j(R1)["G_K1v2_分布一致性"]
    assert sorted(b["★run1_panel"]) == sorted(g1["annotator_mean_JS"]), "★ run1 面板记错了"
    a4 = b["★A4_run_to_run_vs_sampling"]
    assert abs(a4["run1_point"]["JS"] - g1["mean_JS"]) < 1e-9
    assert abs(a4["run1_point"]["top2"] - g1["mean_top2_hit"]) < 1e-9
    if HAVE_VAULT:   # 保险库侧, 公开仓 CI 上可能不在
        g2 = _j(VAULT)["G_K1v2_分布一致性"]
        assert len(b["★run2_panel"]) == len(g2["annotator_mean_JS"]), "★ run2 面板人数不符"


def test_the_pass_is_not_a_binary_fact():
    """★★ JS 的自助 95%CI **跨过 0.25** —— 两套面板都是。"""
    b = _j(BS)
    for tag in ("run2_5panel_as_run", "run2_restricted_to_run1_4panel"):
        o = b[tag]
        assert o["★JS_CI_crosses_0.25"] is True, (
            f"★ [{tag}] JS 的区间不再跨 0.25 了 —— 情况变好了, 请更新 "
            "tests/data/run_a_repeatability_result.json 里「不是二值事实」的说法")
        assert o["★top2_CI_crosses_0.80"] is False, \
            f"★ [{tag}] top2 的下界跌破 0.80 了 —— 这是新情况, 必须重判"
    rep = _j(REP)
    txt = json.dumps(rep, ensure_ascii=False)
    assert "23.0%" in txt and "7.0%" in txt, "★ 两个失败率数字不见了"
    assert "不是二值事实" in txt


def test_exclusion_made_the_panel_less_stable():
    """★★★ 剔除 M2.7 让失败率从 7% 涨到 23% —— 这个方向必须留档。"""
    b = _j(BS)
    j5 = b["run2_5panel_as_run"]["point"]["JS"]
    j4 = b["run2_restricted_to_run1_4panel"]["point"]["JS"]
    assert j4 > j5, (
        f"★ 剔除后 JS 不再更差了(4人 {j4} vs 5人 {j5}) —— 若面板变了请重判, "
        "并更新 run_a_repeatability_result.json 里「剔除损害了稳健性」的说法")
    s4 = b["run2_restricted_to_run1_4panel"]["bootstrap_95CI"]["JS"]["se"]
    s5 = b["run2_5panel_as_run"]["bootstrap_95CI"]["JS"]["se"]
    assert s4 >= s5, f"★ 4 人面板的 SE 不再更大了({s4} vs {s5})"


def test_qualification_exam_has_no_resolution():
    """★★ 三次跑出三个结果这件事必须钉住。"""
    q = _j(QUAL)
    runs = q["★★three_runs_three_answers"]["MiniMax-M2.7"]
    assert len(set(x.split()[0] for x in runs)) >= 3, f"★ 不再是三个不同结果: {runs}"
    assert q["★the_exam_has_no_resolution"]["anchors_needed"]["现有"] == 5
    need = q["★the_exam_has_no_resolution"]["anchors_needed"]["区分 p=0.60 vs 0.95"]
    assert need > 5, f"★ 所需锚例数 {need} 不再大于现有 5 —— 若考卷扩充了, 请重算并更新"
    # ★ 现算二项数字, 不信任落盘值
    from math import comb
    P = lambda p: sum(comb(5, k) * p ** k * (1 - p) ** (5 - k) for k in (4, 5))
    assert 0.25 < P(0.7) < 0.75, f"★ p=0.7 时通过率 {P(0.7):.3f} 不在掷硬币区间了?"
    assert abs(1 - P(0.8) - 0.263) < 0.01, "★ p=0.8 的误判率算错了"


def test_belong_dead_class_claim_was_refuted_by_a_rerun():
    """★★★ 「belong 是死类」被同语料重跑推翻 —— 这条更正必须留着。"""
    rep = _j(REP)
    k = "★★★belong_is_not_a_dead_class_a_rerun_refuted_it"
    assert k in rep, "★ belong 的更正记录不见了"
    assert "0/308" in json.dumps(rep[k], ensure_ascii=False), "★ 单位错误的更正不见了"
    if HAVE_VAULT:
        prev = _j(VAULT)["G_K1v2_分布一致性"]["top1_prevalence"]
        assert prev.get("belong", 0) > 0, (
            "★★ run2 里 belong 又变成 0 了 —— 那「重跑推翻死类」这条要重新表述")
    r1 = _j(R1)["G_K1v2_分布一致性"]["top1_prevalence"]
    assert "belong" not in r1, "★ run1 里 belong 出现了? 那两次的对比要重写"


def test_bootstrap_metric_reproduces_run_gates_exactly():
    """★★ 自助用的 metrics() 必须与 run_gates 的口径**逐字同** —— 否则整个区间作废。

    ★ 「同口径」是一句**声称**; 这条把它变成**可证伪的**: 用我的函数在 run2 的原始标注上
      重算, 必须复现出 run_gates 自己产物里的那两个数。
    """
    if not HAVE_VAULT:
        # ★ 降级路径也要有断言, 否则恒绿
        assert not os.path.exists(VAULT.parent / 'raw_annotations.json'), \
            '★ 产物在但 gates_result 不在 —— 那是半份数据, 比没有更危险'
        return
    import sys
    sys.path.insert(0, str(ROOT / "probes"))
    import gk1_bootstrap as G
    raw = _j(VAULT.parent / "raw_annotations.json")
    g2 = _j(VAULT)["G_K1v2_分布一致性"]
    ids = sorted({i for m in raw["annotators"] for i in raw["dists"][m] if raw["dists"][m][i]})
    t, j = G.metrics(raw["dists"], raw["annotators"], ids)
    assert abs(t - g2["mean_top2_hit"]) < 5e-4, (
        f"★★★ top2 口径不一致: 我算 {t:.4f} vs 产物 {g2['mean_top2_hit']} ⇒ **自助区间作废**")
    assert abs(j - g2["mean_JS"]) < 5e-4, (
        f"★★★ JS 口径不一致: 我算 {j:.4f} vs 产物 {g2['mean_JS']} ⇒ **自助区间作废**")


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    b = _j(BS)
    bad = copy.deepcopy(b)
    bad["run2_restricted_to_run1_4panel"]["★JS_CI_crosses_0.25"] = False
    g["_j"] = lambda p: bad if p == BS else saved(p)
    try:
        test_the_pass_is_not_a_binary_fact()
        raise SystemExit("★ 反向验证失败: 抹掉「跨阈值」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(b)
    bad2["run2_restricted_to_run1_4panel"]["point"]["JS"] = 0.0
    g["_j"] = lambda p: bad2 if p == BS else saved(p)
    try:
        test_exclusion_made_the_panel_less_stable()
        raise SystemExit("★ 反向验证失败: 把剔除后的 JS 改好后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    q = _j(QUAL)
    bad3 = copy.deepcopy(q)
    bad3["★★three_runs_three_answers"]["MiniMax-M2.7"] = ["4/5 合格"] * 3
    g["_j"] = lambda p: bad3 if p == QUAL else saved(p)
    try:
        test_qualification_exam_has_no_resolution()
        raise SystemExit("★ 反向验证失败: 抹平三次结果后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_bootstrap_numbers_match_the_products()
    test_the_pass_is_not_a_binary_fact()
    test_exclusion_made_the_panel_less_stable()
    test_qualification_exam_has_no_resolution()
    test_belong_dead_class_claim_was_refuted_by_a_rerun()
    test_bootstrap_metric_reproduces_run_gates_exactly()
    n = _reverse_checks()
    b = _j(BS)
    c4 = b["run2_restricted_to_run1_4panel"]["bootstrap_95CI"]
    print(f"test_cce_repeatability: OK ("
          f"★JS 95%CI [{c4['JS']['lo']}, {c4['JS']['hi']}] **跨过 0.25** ⇒ 通过不是二值事实 | "
          f"top2 下界 {c4['top2']['lo']} 稳在 0.80 上 | "
          f"★剔除 M2.7 使 JS 从 {b['run2_5panel_as_run']['point']['JS']} 恶化到 "
          f"{b['run2_restricted_to_run1_4panel']['point']['JS']} | "
          f"★★资格考三次三答(3/5·5/5·4/5), p=0.8 时单次误判率 26.3% | "
          f"belong「死类」已被重跑推翻 | "
          f"{'★自助口径**复现** run_gates 产物' if HAVE_VAULT else '★**无本机素材, 未比对 run2 产物**(只跑了仓内可验的部分)'} | "
          f"{n} 条反向验证判红)")
