"""★★★ 闸字段集 vs 生产字段集 —— 判决必须现算, 且必须带外推限度。零 API。

## 结果(本闸从原始读数现算, 不引用产物里的数字)
| | mean_JS | 自助 95%CI | 越 0.25 线的自助概率 |
|---|---|---|---|
| **arm A** 闸字段集(决策树+负例+锚例) | **0.2163** | [0.176, 0.257] | **5.9%** |
| **arm B** 生产字段集(family+typical_codes+levers) | **0.3008** | [0.263, 0.338] | **99.7%** |

配对自助差 **+0.0845**, 95%CI [0.0395, 0.1276] **不含 0** ⇒ 预注册的 **D2** 成立:
**闸是乐观代理** —— 「G-K1 通过」对**闸的字段集**成立, 对**生产分类器实际看到的字段集**不成立。

## ★★ 唯一变量
条目/模型/温度/截断/任务措辞/输出 schema **两臂逐字相同**, 只换分类学材料。
模板手术由 probes/fieldset_arm_b.py 的 import 期 assert 守住(切点唯一、任务形态保留)。

## ★★★ 它**不**说什么(这几条比结论更容易被丢掉)
· arm B **不是生产**: 没吃 s1 四层、没出完整 schema、k=1 而非 3 ⇒ **只隔离了字段集合这一个变量**
· 因此**不得**说「生产分类器 G-K1 不达标」
· **不改判** 2026-09-07 的 G-K1 PASS —— 另一台仪器的读数, 可比不可合
· 两臂 body 截断是否一致**无法核实**(run_a_repeat 没记参数) —— 这条限度在发起前就写进预注册
"""
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RAW_A = V / "run_a_repeat" / "raw_annotations.json"
RAW_B = V / "fieldset_arm_b" / "raw.json"
PRE = ROOT / "tests" / "data" / "gate_vs_production_fieldset_prereg.json"
RES = ROOT / "tests" / "data" / "gate_vs_production_fieldset_result.json"
THR = 0.25
sys.path.insert(0, str(ROOT / "probes"))


def _have_vault():
    return RAW_A.exists() and RAW_B.exists()


def _pre():
    return json.loads(PRE.read_text(encoding="utf-8"))


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def _arms():
    import fieldset_arm_b_adjudicate as J
    A = json.loads(RAW_A.read_text(encoding="utf-8"))
    models, da = A["annotators"], A["dists"]
    db = {m: {} for m in models}
    for r in json.loads(RAW_B.read_text(encoding="utf-8")):
        if r["dist"]:
            db[r["model"]][r["id"]] = r["dist"]
    ids = [i for i in A["sample_ids"]
           if all(da[m].get(i) for m in models) and all(db[m].get(i) for m in models)]
    return J, models, da, db, ids


def test_the_difference_is_recomputed_and_the_CI_excludes_zero():
    """★ D1/D2 现算: 配对自助的差值 CI 不含 0, 且方向是 B 更差。"""
    if not _have_vault():
        g = _res()["★diff_JS_B_minus_A"]
        lo, hi = g["配对自助95%CI"]
        assert lo > 0 and g["点估计"] > 0.02, "★ 产物里的差值不再支持 D2"
        print("  ★ 降级: 无本机素材, 只核对产物内部一致(未重算原始读数)")
        return
    J, models, da, db, ids = _arms()
    ja, jb = J.metrics(da, models, ids)[0], J.metrics(db, models, ids)[0]
    rnd = random.Random(20260908)
    diffs = []
    for _ in range(2000):
        s = [ids[rnd.randrange(len(ids))] for _ in ids]
        x, y = J.metrics(da, models, s)[0], J.metrics(db, models, s)[0]
        if x is not None and y is not None:
            diffs.append(y - x)
    diffs.sort()
    lo = diffs[int(.025 * len(diffs))]
    assert jb > ja, f"★ arm B 不再更差(A={ja:.4f} B={jb:.4f}) —— D2 不成立了, 请复核结论"
    assert lo > 0, f"★ 配对自助 95%CI 下界 {lo:.4f} 不再排除 0 —— 差异不显著了"
    assert jb - ja > 0.02, f"★ 差值 {jb-ja:.4f} 已落到 D4 的「影响小」区间, 请更新结论"


def test_arm_b_is_over_the_gate_threshold_and_arm_a_is_under():
    """★★★ 最要紧的一条: **闸字段集在线下, 生产字段集在线上**。"""
    if not _have_vault():
        t = _res()["★★★relative_to_the_G_K1_threshold"]
        assert t["armB_生产字段集"]["mean_JS"] > THR >= t["armA_闸字段集"]["mean_JS"]
        print("  ★ 降级: 无本机素材, 只核对产物里的两个均值与阈值的相对位置")
        return
    J, models, da, db, ids = _arms()
    ja, jb = J.metrics(da, models, ids)[0], J.metrics(db, models, ids)[0]
    assert ja <= THR, f"★ arm A 的 JS {ja:.4f} 也越线了 —— 结论要重写(不再是「闸达标生产不达标」)"
    assert jb > THR, f"★★ arm B 的 JS {jb:.4f} 不再越线 —— 结论要重写"


def test_the_scope_limits_are_not_deleted():
    """★★★ 四条外推限度比结论更容易被丢掉, 逐条钉住。"""
    d = json.dumps(_res(), ensure_ascii=False)
    for must in ("arm B **不是生产**", "不得**说「生产分类器 G-K1 不达标」",
                 "可比不可合", "无法核实"):
        assert must.replace("**", "") in d.replace("**", ""), f"★ 外推限度「{must}」不见了"


def test_the_panel_choice_was_frozen_before_running():
    """★ 用全 5 人面板还是核心 4 人面板, 是**发起前**定的 —— 否则就是按结果挑面板。"""
    d = json.dumps(_pre(), ensure_ascii=False)
    assert "全 5 人面板" in d and "离群规则会在两臂" in d, "★ 面板选择的冻结记录不见了"
    assert "★★which_panel_frozen_before_running" in _pre(), "★ 冻结块被删了"


def test_the_missing_rule_was_frozen_and_reported():
    """★★ 缺失怎么办是**在有结果之前**写死的(suspend 那轮吃过亏), 且结果里必须报缺失。"""
    assert "★★★missing_readings_rule_frozen_before_results" in _pre(), "★ 缺失规则的冻结块不见了"
    r = _res()
    assert "★★缺失报告" in r, "★ 结果里没有缺失报告"
    m = r["★★缺失报告"]
    assert "预注册触发条件" in json.dumps(m, ensure_ascii=False), "★ 触发条件没被报出来"


def test_my_directional_bet_is_recorded_either_way():
    """★ 赌注是**发起前**写的, 且记的是「赌对/赌错」而不是事后编的理由。"""
    b = _res()["★my_bet"]
    assert b["信心"] == "低", "★ 预先声明的信心水平被改了"
    assert b["★结果"] in ("**赌对**", "**赌错**", "持平"), "★ 赌注结果被改成了别的东西"
    assert "赌错时同一条记录会把我钉住" in json.dumps(b, ensure_ascii=False), \
        "★ 「这条记录存在的理由是赌错时钉住我」这句不许删"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_res"]
    import copy

    bad = copy.deepcopy(_res())
    for k in ("arm B **不是生产**: 它没吃 s1 的四层输出、没出完整 schema、k=1 而非 3。本轮**只隔离了分类学字段集合这一个变量**。",):
        bad["★★★what_this_still_does_not_say"] = ["随便一句"]
    g["_res"] = lambda: bad
    try:
        test_the_scope_limits_are_not_deleted()
        raise SystemExit("★ 反向验证失败: 抹掉外推限度后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    bad2 = copy.deepcopy(_res()); bad2["★my_bet"]["信心"] = "高"
    g["_res"] = lambda: bad2
    try:
        test_my_directional_bet_is_recorded_either_way()
        raise SystemExit("★ 反向验证失败: 事后改高信心后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    saved_h = g["_have_vault"]
    g["_have_vault"] = lambda: False
    try:
        test_the_difference_is_recomputed_and_the_CI_excludes_zero()
        test_arm_b_is_over_the_gate_threshold_and_arm_a_is_under()
    finally:
        g["_have_vault"] = saved_h
    n += 2      # ★ 降级分支**实跑**过, 不靠读代码推断
    return n


if __name__ == "__main__":
    test_the_difference_is_recomputed_and_the_CI_excludes_zero()
    test_arm_b_is_over_the_gate_threshold_and_arm_a_is_under()
    test_the_scope_limits_are_not_deleted()
    test_the_panel_choice_was_frozen_before_running()
    test_the_missing_rule_was_frozen_and_reported()
    test_my_directional_bet_is_recorded_either_way()
    n = _reverse_checks()
    r = _res()
    t = r["★★★relative_to_the_G_K1_threshold"]
    print(f"test_cce_fieldset_arm_b: OK ("
          f"armA(闸字段集) JS {t['armA_闸字段集']['mean_JS']} 越线率 {t['armA_闸字段集']['自助越线率']:.1%} · "
          f"armB(生产字段集) JS {t['armB_生产字段集']['mean_JS']} 越线率 {t['armB_生产字段集']['自助越线率']:.1%} | "
          f"★★★配对差 {r['★diff_JS_B_minus_A']['点估计']} CI {r['★diff_JS_B_minus_A']['配对自助95%CI']} 不含 0 ⇒ "
          f"**D2 闸是乐观代理** | 四条外推限度在 | 面板选择与缺失规则均**发起前冻结** | "
          f"方向赌注(信心低)记为{r['★my_bet']['★结果']} | {n} 条反向验证/降级实跑)")
