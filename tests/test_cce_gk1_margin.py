"""G-K1 的余量与离群规则 —— 数字必须**在测试时重算**, 不许和产物脱节。

## 为什么
2026-09-07 G-K1 通过: top2=0.9042(阈≥0.8) · JS=0.2321(阈≤0.25)。
但两项的**余量厚度差了 5 倍**:
· top2 余量 0.1042 = **2.85 个**跨对 SD
· JS  余量 0.0179 = **0.55 个**跨对 SD  ← ★ 余量比散布还小

⇒ 「G-K1 通过」这句话不该被引用成一个二值事实。**它卡在 JS 上, 而且卡得很紧。**

## ★★ 以及一条不改规则、只记录的发现
离群规则是「与其余成员平均JS > **面板中位数 + 2SD**」, 而**面板包含候选离群者自己** ——
偏高的成员会把 SD 抬上去, **从而保护它自己**。
实测 Text-01 **两次差不到千分之一没触发**:
  2026-08-09: 0.3082 vs 线 0.3092(差 0.0010) · 2026-09-07: 0.2586 vs 线 0.2592(差 **0.0006**)
留一法(用其余三人算线)则**会触发**: 线 0.2341 < 0.2586。

★★★ **本闸不改规则。** 规则 2026-08-09 冻结; 看到结果之后去改它, 就是在挑一个让自己喜欢的答案 ——
而且方向恰好是「剔掉最差的 ⇒ 指标变好」, 那是最该警惕的方向。
本闸只做一件事: **把这个结构性性质钉住**, 让它不能被悄悄遗忘。
"""
import json
import pathlib
import statistics as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "accuracy" / "out" / "gates_result.json"
DOC = ROOT / "tests" / "data" / "gk1_margin_analysis.json"


def _g():
    return json.loads(RES.read_text(encoding="utf-8"))["G_K1v2_分布一致性"]


def _doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


def _thr(vals):
    s = (sum((v - st.mean(vals)) ** 2 for v in vals) / len(vals)) ** 0.5
    return st.median(vals) + 2 * s


def test_margins_are_recomputed_not_copied():
    """★ 余量数字必须与产物**现算一致** —— 否则文档会悄悄和结果脱节。"""
    g, d = _g(), _doc()
    m = d["★finding_1_margin_is_thinner_than_the_spread"]
    assert abs(m["JS"]["mean"] - g["mean_JS"]) < 1e-9, "★ JS 均值与产物不符"
    assert abs(m["top2"]["mean"] - g["mean_top2_hit"]) < 1e-9, "★ top2 均值与产物不符"
    assert abs(m["JS"]["margin_over_sd"] - (0.25 - g["mean_JS"]) / g["sd_JS"]) < 0.01
    assert abs(m["top2"]["margin_over_sd"] - (g["mean_top2_hit"] - 0.80) / g["sd_top2_hit"]) < 0.01


def test_js_margin_is_recorded_as_thin():
    """★ JS 余量 < 1 个 SD 这件事必须被记着 —— 一旦它变厚了, 这条断言会红并提醒更新。"""
    g = _g()
    ratio = (0.25 - g["mean_JS"]) / g["sd_JS"]
    assert ratio < 1.0, (
        f"★ JS 余量现在是 {ratio:.2f} 个 SD(>=1) —— 情况变好了, 请更新本文件与 "
        "tests/data/gk1_margin_analysis.json 的说法, 别让一句过时的警告继续挂着"
    )
    assert "余量(0.0179)比六对之间的 SD" in json.dumps(_doc(), ensure_ascii=False)


def test_outlier_rule_including_self_vs_leave_one_out_is_recorded():
    """两种算法在同一份数据上结论相反 —— 这件事必须留档。"""
    g, d = _g(), _doc()
    J = g["annotator_mean_JS"]
    allv = list(J.values())
    flips = []
    for name, v in J.items():
        others = [x for k, x in J.items() if k != name]
        if (v > _thr(others)) != (v > _thr(allv)):
            flips.append(name)
    assert flips, (
        "★ 两种算法不再出现结论相反的成员 —— 若面板变了, 请更新 gk1_margin_analysis.json 的说法"
    )
    rec = {r["annotator"] for r in d["★finding_2_the_outlier_rule_protects_the_outlier"]["per_annotator"]
           if r["fires_leave_one_out"] != r["fires_including_self"]}
    assert rec == set(flips), f"★ 文档记的翻转成员 {rec} 与现算 {set(flips)} 不符"


def test_the_rule_itself_was_not_changed():
    """★★ 核心: 规则**没有被改**。看到结果后改规则 = 挑一个让自己喜欢的答案。"""
    g = _g()
    assert "面板中位数+2SD" in g["outlier_rule"].replace(" ", ""), \
        "★ 离群规则的文字变了 —— 若是有意改动, 必须先冻结再跑, 不能拿本轮数据当依据"
    assert "2026-08-09" in g["outlier_rule"], "★ 规则的冻结日期不见了"
    d = _doc()
    assert "本轮判决维持" in json.dumps(d, ensure_ascii=False), \
        "★ 文档必须写明本轮不改判 —— 否则下一个人会以为发现了问题就该改结论"


def test_run_persists_raw_annotations():
    """★ 那次跑丢了 430+ 次调用的原始数据。现在必须落盘, 否则误差棒还得再花一次钱。"""
    src = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")
    assert "raw_annotations.json" in src, \
        "★ run_gates 不再落盘逐条原始标注 ⇒ 下次要置信区间又得重跑 430 次"
    assert '"dists": dists' in src, "★ 落盘的内容里没有逐条分布"


def _reverse_checks():
    n = 0
    g = globals()
    saved_g, saved_d = g["_g"], g["_doc"]
    res, doc = _g(), _doc()

    # ① 余量与产物脱节 ⇒ 红
    import copy
    bad = copy.deepcopy(doc)
    bad["★finding_1_margin_is_thinner_than_the_spread"]["JS"]["mean"] = 0.1
    g["_doc"] = lambda: bad
    try:
        test_margins_are_recomputed_not_copied()
        raise SystemExit("★ 反向验证失败: 余量与产物脱节后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_doc"] = saved_d

    # ② 规则文字被改 ⇒ 红
    bad2 = copy.deepcopy(res)
    bad2["outlier_rule"] = "与其余成员平均JS > 留一法中位数+2SD(2026-09-07 改)"
    g["_g"] = lambda: bad2
    try:
        test_the_rule_itself_was_not_changed()
        raise SystemExit("★ 反向验证失败: 规则被改成留一法后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_g"] = saved_g

    # ③ 翻转成员记错 ⇒ 红
    bad3 = copy.deepcopy(doc)
    for r in bad3["★finding_2_the_outlier_rule_protects_the_outlier"]["per_annotator"]:
        r["fires_leave_one_out"] = r["fires_including_self"]
    g["_doc"] = lambda: bad3
    try:
        test_outlier_rule_including_self_vs_leave_one_out_is_recorded()
        raise SystemExit("★ 反向验证失败: 抹掉翻转记录后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_doc"] = saved_d
    return n


if __name__ == "__main__":
    test_margins_are_recomputed_not_copied()
    test_js_margin_is_recorded_as_thin()
    test_outlier_rule_including_self_vs_leave_one_out_is_recorded()
    test_the_rule_itself_was_not_changed()
    test_run_persists_raw_annotations()
    n = _reverse_checks()
    g = _g()
    print(f"test_cce_gk1_margin: OK ("
          f"余量现算一致 | JS 余量 {(0.25-g['mean_JS'])/g['sd_JS']:.2f} 个 SD(<1, 已记为薄) vs "
          f"top2 {(g['mean_top2_hit']-0.80)/g['sd_top2_hit']:.2f} 个 SD | "
          f"含自身 vs 留一法结论相反的成员已留档 | **规则未被改动**且本轮不改判 | "
          f"原始标注已落盘 | {n} 条反向验证判红)")
