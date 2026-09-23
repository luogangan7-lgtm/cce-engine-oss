"""★★★ 生产完整流程重测 —— 第四本账的**首条**证据。零 API。

## 结果
q = **19/22 = 0.8636**(3 题翻转) · 翻转率单侧 95% 精确上限 **0.3159**
九类转移: reward→display · suspend→inertia · inertia→suspend

## ★★★ 本轮真正的发现: **汇总稳而逐题不稳**
两次运行的**汇总数字完全相同**(C1 八题 1/8 · 16 道负例误判 3/16 · 阳性对照 6/6),
但**三题翻转, 且在负例组上恰好互相抵消**。
⇒ **任何基于「生产在某一题上判对/判错」的推理都不可靠。**
★ 我此前所有逐组对照(生产 0/2、0/4 之类)**每一格都带着这个不稳定度, 而我从没标过**。

## ★★ 不能签发的
**没有事先定义允许的翻转率 ⇒ 不签发「信度合格」**, 不报告「生产稳定性已建立」。
**也不能**说「汇总量稳健」—— n=2 无法区分「稳健」与「碰巧抵消」。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RAW = V / "production_retest" / "raw.json"
RES = ROOT / "tests" / "data" / "production_retest_reliability_result.json"
PRE = ROOT / "tests" / "data" / "production_retest_reliability_prereg.json"


def _have():
    return RAW.exists()


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def test_it_was_a_real_retest_same_instrument():
    """★★★ 前提: 两次跑的必须是**同一台生产仪器**, 否则不构成重测。"""
    p1 = json.loads((V / "production_suspend_defect/run_params.json").read_text(encoding="utf-8"))
    if not (V / "production_retest/run_params.json").exists():
        raise AssertionError("★ 第二次运行缺 run_params —— 无法核验仪器同一性")
    p2 = json.loads((V / "production_retest/run_params.json").read_text(encoding="utf-8"))
    for k in ("instrument_hash", "KNOT_N", "MEASUREMENT_MODEL"):
        assert p1[k] == p2[k], f"★★★ {k} 两次不同({p1[k]} vs {p2[k]}) —— **这不是重测**"
    assert "**s1 与 s2 都重跑**" in p2["★完整重跑"], (
        "★★ 必须完整重跑 s1 和 s2 —— 复用旧 s1 测到的是「条件于固定 s1 的 s2 稳定性」")


def test_q_is_recomputed_and_failures_are_not_counted_as_stable():
    """★ q 现算; 无合法读数的条目**不计入 q, 也不当作稳定**。"""
    if not _have():
        assert _res()["★★★主读数 q"]["值"] is not None
        print("  ★ 降级: 无本机素材, 只核对产物")
        return
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    ok = [r for r in rows if r.get("top1_run2")]
    same = sum(1 for r in ok if r["same"])
    q = same / len(ok)
    g = _res()["★★★主读数 q"]
    assert abs(g["值"] - q) < 5e-5, f"★ 产物 q={g['值']} 与现算 {q} 不符(产物按 4 位取整)"
    assert g["算式"] == f"{same}/{len(ok)}"
    assert len(ok) + len(_res()["★无合法读数(不计入 q, 也不当作稳定)"]) == 22, \
        "★★ 有效 + 无效 必须等于 22 个设计单元 —— 少了就是被默默删掉了"


def test_no_reliability_certificate_is_issued():
    """★★★ 没有事先定义允许的翻转率 ⇒ **不签发「信度合格」**。"""
    d = json.dumps(_res(), ensure_ascii=False)
    assert "不签发「信度合格」" in d and "不报告「生产稳定性已建立」" in d
    assert "首条局部重测证据" in d, "★ 本轮定位不许被抬高"
    p = json.loads(PRE.read_text(encoding="utf-8"))
    assert "没有事先定义允许的翻转率" in json.dumps(p, ensure_ascii=False), \
        "★ 这条限制必须是**发起前**就写在预注册里的"


def test_the_aggregate_stable_itemwise_unstable_finding_is_recorded():
    """★★★ 本轮真正的发现: **汇总稳而逐题不稳**, 且我第一句结论说错了。"""
    b = _res().get("★★★汇总稳而逐题不稳_这是本轮真正的发现")
    assert b, "★★★ 这条发现被删了"
    assert "我第一句结论说错了" in json.dumps(b, ensure_ascii=False), \
        "★ 「我当场说错了」的记录不许抹 —— 那是同一段输出里既算对又写错"
    assert len(b["★★实际形状"]["逐题明细"]) == 3, "★ 三题翻转的逐题明细不完整"
    assert "互相抵消" in b["★★实际形状"]["★逐题"]
    assert "n=2 无法区分" in b["★★不许由此得出的"], \
        "★★ 必须写明 n=2 分不清「汇总稳健」与「碰巧抵消」"
    assert "每一格都带着这个不稳定度而我从没标过" in json.dumps(b, ensure_ascii=False), \
        "★★★ 这条自我指认不许删 —— 它说明此前所有逐组对照都缺一个标注"


def test_the_next_step_follows_the_frozen_three_tier_gate():
    """★ 采购 gate 的三档是**发起前**写死的, 判决必须落在其中一档。"""
    r = _res()
    q = r["★★★主读数 q"]["值"]
    nxt = r["★★★下一步(按预注册的三档)"]
    if q >= 0.9:
        assert "q 高" in nxt
    elif q >= 0.7:
        assert "q 中" in nxt and "任何基于单次生产读数的比较都要带这个数" in nxt
    else:
        assert "q 低" in nxt and "全部降级" in nxt


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_res"]
    import copy
    bad = copy.deepcopy(_res())
    del bad["★★★汇总稳而逐题不稳_这是本轮真正的发现"]
    g["_res"] = lambda: bad
    try:
        test_the_aggregate_stable_itemwise_unstable_finding_is_recorded()
        raise SystemExit("★ 反向验证失败: 删掉核心发现后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    bad2 = copy.deepcopy(_res())
    bad2["★★★不能签发的东西"] = "生产稳定性已建立"
    g["_res"] = lambda: bad2
    try:
        test_no_reliability_certificate_is_issued()
        raise SystemExit("★ 反向验证失败: 签发信度合格后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved
    return n


if __name__ == "__main__":
    test_it_was_a_real_retest_same_instrument()
    test_q_is_recomputed_and_failures_are_not_counted_as_stable()
    test_no_reliability_certificate_is_issued()
    test_the_aggregate_stable_itemwise_unstable_finding_is_recorded()
    test_the_next_step_follows_the_frozen_three_tier_gate()
    n = _reverse_checks()
    r = _res()
    print(f"test_cce_production_retest: OK ("
          f"★仪器同一性已断言(instrument_hash 两次相同) + **s1/s2 都完整重跑** | "
          f"q = {r['★★★主读数 q']['算式']} = {r['★★★主读数 q']['值']}, "
          f"翻转率单侧95%上限 {r['★★★主读数 q']['★翻转率的单侧95%精确上限']} | "
          f"★★★**汇总稳而逐题不稳**(两次汇总全同, 但三题翻转在负例组上互相抵消) —— "
          f"此前所有逐组对照**每格都带这个不稳定度而我从没标过** | "
          f"★★不签发「信度合格」· n=2 也不许说「汇总稳健」 | {n} 条反向验证判红)")
