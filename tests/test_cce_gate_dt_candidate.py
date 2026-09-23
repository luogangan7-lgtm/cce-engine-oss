"""★★★ 闸材料候选 v3c: **判决 FAIL, 但判据无检定力 ⇒ 结论是「无结论」不是「候选不好」**。零 API。

## 结果(判据发起前冻结)
| | v2 | v3c | |
|---|---|---|---|
| R1 仅收藏 | 5/10 · 题级 1/2 | **2/10 · 题级 0/2** | PASS |
| R2 真悬置 | 20/20 | **20/20** | PASS(我赌它会掉, **赌错**) |
| R2 C1 失败方向题级 | 0/8 | 0/8 | PASS |
| R3 历史悬置→现已决定 | 2/20 | **3/20** | ★变坏(差 **1 个读数**) |
| R3 纯向往 | 0/10 | **1/10** | ★变坏(差 **1 个读数**) |

## ★★★ 判据本身的缺陷(经 2026-09-09 第四轮更正)
★ 我第一版写「闸噪声 9.1% ⇒ 6 组里至少一个变化几乎必然 ⇒ R3 无检定力」——**三处都推过头了**:
· **口径错**: 9.1% 是「top-1 完全相同」; R3 关心的是「**suspend 正误状态**」⇒ 实测 **4.5%**(5/110)
· **忽略抵消**: 实测组级净效应 **8 组里 6 组为 0**; 我却把「至少一个单元变化」当「组错误率增加」
· **非 iid**: 各组基线错误率差异巨大(仅收藏 5/10 vs 真悬置 0/20), 不能均匀铺
⇒ 「几乎必然 FAIL」**撤回**; 也不宜只叫「无检定力」(同时涉及误拒风险与识别能力)。
★★ 但换来**更强的零调用证据**: 纯噪声对照(v2 vs V1, 同材料)中负例组 Δ=**+0.100**
   ⇒ **R3 在这一次纯噪声对照中确实会 FAIL**(n=1 观察, 不是概率估计)。
★★★ 且有界均值区间在 n=2~4 上**全是 [-1,+1]** ⇒ **这个规模做不了非劣效判断** —— 不是阈值定错。

★★ 本仓同族: playbook 那轮的 0.95 线在 n=8 下等价于零容差, 纯噪声期望达标 ≈4.8/8。
   **我又写了一条零容差判据**, 而且噪声底是同一轮顺带买到的 —— 本可以先算再定判据。

## ★★ 判决不因此改
判据冻结在先。**不许**因结果不利说「在噪声范围内」—— 那是我自己在 v2 那轮写死的自我约束。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ 本闸**不需要**仓外原始读数 —— 全部判据从**仓内产物**现读, 故不引用保险库路径。
#   (元闸 test_cce_no_offrepo_dependency 抓到过第一版引用了它却没写缺席降级;
#    正确的修法不是补一个用不上的降级分支, 而是**去掉那个用不到的依赖**。)
RES = ROOT / "tests" / "data" / "gate_decision_tree_candidate_result.json"
PRE = ROOT / "tests" / "data" / "gate_decision_tree_candidate_prereg.json"


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def test_the_verdict_is_fail_and_was_not_loosened():
    """★★ 判决维持 FAIL, 现网未动, 判据未被放宽。"""
    r = _res()
    ov = r["★★★overall"]
    # ★ 2026-09-09: overall 已换成网页版 GPT 的**逐字措辞**。旧断言查的是我原来写的字样,
    #   换措辞后失效。**守的东西不变**(判决 FAIL / 未启用 / 判据未放宽), 改查新措辞的等价内容。
    assert "未通过冻结的 R3" in ov and "因此未启用" in ov, f"★★ overall 不再声明未启用: {ov[:80]}"
    assert "未建立候选的总体净收益或保护项非劣效性" in ov, (
        "★★★ 「未建立」这半句不许删 —— 它是「无结论」而非「候选不好」的载体")
    assert "也未证明这些增加由纯噪声造成" in ov, (
        "★★★ 「也未证明由纯噪声造成」这半句同样不许删 —— "
        "**两个方向都没证明**, 少任何一半都会把结论读成单边")
    assert r["★R3_全组剖面"]["verdict"].startswith("★FAIL")
    # ★ 判据未被放宽: 冻结的预注册里 R3 的原文必须还在
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    assert "不得出现预定义的关键新错误" in json.dumps(pre, ensure_ascii=False), \
        "★★ 预注册里 R3 的原文被改了 —— 判据冻结后不许改"
    # ★ 现网决策树必须仍是旧的
    t = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    dt = t["annotation_protocol"]["decision_tree_prompt"]
    assert any("明确悬置决策(还没定/再看看+犹豫理由)?" in l for l in dt), (
        "★★★ 现网决策树被改了 —— 候选未通过就**不该**上线")
    assert not any("三者缺一不判 suspend" in l for l in dt), "★★ 候选文本进了现网, 立即回滚"


def test_the_criterion_has_no_power_and_that_is_recorded():
    """★★★ R3 零容忍 + 9.1% 噪声 ⇒ 几乎必然 FAIL。这条必须与判决同时出现。"""
    b = _res().get("★★★R3的判据本身没有检定力_2026-09-09")
    assert b, "★★★ 判据缺陷的记录被删了 —— 只留 FAIL 会让人以为候选不好"
    n = b["★★但判据本身有缺陷, 必须同时报"]
    assert "9.1%" in n["噪声底(本轮顺带买到)"]
    assert n["★★★在 9.1% 噪声下"]["20 单元的组完全不变的概率"] < 0.2
    assert "几乎是必然事件" in n["★★★在 9.1% 噪声下"]["⇒"]
    assert "没有检定力" in n["★★结论"]
    assert "差 1 个读数" in json.dumps(n["两个「变坏」的规模"], ensure_ascii=False)


def test_no_conclusion_is_not_the_same_as_candidate_is_bad():
    """★★★ 「无结论」与「候选不好」的区别是实质的, 不许混。"""
    d = json.dumps(_res(), ensure_ascii=False)
    assert "无结论」, 不是「候选不好" in d or "「无结论」" in d and "不是「候选不好」" in d, \
        "★★★ 这个区分不许删: 判据无检定力时, 不许我说它坏, 也不许我采用它"
    assert "不许我采用它, 但也不许我说它坏" in d or "前者不许我采用它" in d


def test_the_next_round_may_not_reverse_engineer_the_threshold():
    """★★ 下一轮定噪声容忍时, **不许拿本轮数据反推阈值** —— 那是用结果选判据。"""
    b = _res()["★★★R3的判据本身没有检定力_2026-09-09"]
    assert "不许**拿本轮数据去反推那个阈值" in b["★下一轮若要重测这个候选"].replace("*", "*") \
        or "用结果选判据" in b["★下一轮若要重测这个候选"]


def test_my_bet_on_R2_was_wrong_and_recorded():
    """★ 我赌真悬置会掉, 它一点没掉。赌注的用处就在赌错时。"""
    b = _res()["★★my_bet_result"]
    assert "R2 赌错" in b["★结果"], "★ 赌错的记录被改了"
    assert "直觉是**错的**" in b["★结果"] or "直觉是错的" in b["★结果"].replace("*", "")


def test_the_single_change_really_was_single():
    """★★ 候选必须是**单一改动** —— 不许打包 typical_codes / itch 优先 / 新负例。"""
    f = json.loads(PRE.read_text(encoding="utf-8"))["★★★the_single_change_verbatim"]
    assert f["target"].endswith("**只改这一条**")
    no = json.dumps(f["★★不做的三件事(GPT 明令, 逐条钉)"], ensure_ascii=False)
    for m in ("typical_codes", "itch 一律优先", "堆一条负例"):
        assert m in no, f"★ 「不做{m}」这条约束不见了"
    assert "★★我承认的判断成分" in f["★为什么这不算改产品主张(对照 GPT 的四项判据)"], \
        "★★ 「通道行为是伴随现象」那句是我加的措辞 —— 这条自认不许删"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_res"]
    import copy
    bad = copy.deepcopy(_res())
    del bad["★★★R3的判据本身没有检定力_2026-09-09"]
    g["_res"] = lambda: bad
    try:
        test_the_criterion_has_no_power_and_that_is_recorded()
        raise SystemExit("★ 反向验证失败: 删掉判据缺陷记录后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    bad2 = copy.deepcopy(_res())
    bad2["★★★overall"] = "候选通过"
    g["_res"] = lambda: bad2
    try:
        test_the_verdict_is_fail_and_was_not_loosened()
        raise SystemExit("★ 反向验证失败: 把 FAIL 改成通过后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved
    return n


if __name__ == "__main__":
    test_the_verdict_is_fail_and_was_not_loosened()
    test_the_criterion_has_no_power_and_that_is_recorded()
    test_no_conclusion_is_not_the_same_as_candidate_is_bad()
    test_the_next_round_may_not_reverse_engineer_the_threshold()
    test_my_bet_on_R2_was_wrong_and_recorded()
    test_the_single_change_really_was_single()
    n = _reverse_checks()
    r = _res()
    print(f"test_cce_gate_dt_candidate: OK ("
          f"R1 仅收藏 5/10→**2/10**(题级 1/2→**0/2**) ✅ · R2 真悬置 20/20→**20/20**(我赌它会掉, **赌错**) ✅ | "
          f"★R3 两组各**变坏 1 个读数** ⇒ 判决 **FAIL**, 现网未动, 判据未放宽 | "
          f"★★★噪声底**更正**: 我用的 top-1 口径 9.1% 高估了一倍, "
          f"R3 关心的**正误状态**口径实测 **4.5%**(5/110); 且 8 组里 6 组净变化为 0 | "
          f"★★「几乎必然 FAIL」**已撤回**(未经误拒率校准); 换来更强的: "
          f"**纯噪声对照(v2 vs V1)中 R3 确实会 FAIL**(n=1 观察, 非概率估计) | "
          f"★★★有界均值区间在 n=2~4 上**全是 [-1,+1]** ⇒ **这个规模做不了非劣效判断** | "
          f"结论用 GPT 逐字措辞: 未建立净收益/非劣效, **也未证明由纯噪声造成**(两半都不许删) | "
          f"单一改动已钉(未打包) | "
          f"{n} 条反向验证判红)")
