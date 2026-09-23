"""★★★ 跨家族参考标注 —— 这 81 条产物的**质量证据**, 以及它不是什么。零 API, 现算。

## 为什么做这个而不是继续凑锚例
2026-09-08 网页 GPT(Pro, 10m10s)的第五条路: 若真正要交付的是这 81 条的验收结果,
就**直接验它**, 而不是先建一场**仅用于决定谁能参与这次验收**的资格考。
⇒ 它把问题从「先证明谁合格」翻转成「**直接证明这批产物的质量**」。

## 结果(MiniMax 五员共识 vs glm-4.5-flash 跨家族参考, 同一 81 条评论)
· top1 一致 **62/81 = 76.5%**  Wilson [0.663, 0.844]
· **top2 命中 74/81 = 91.4%**  (G-K1 阈 >=0.80) ✅
· **平均 JS 0.2236**           (G-K1 阈 <=0.25) ✅

★★ 用一个**从未参与 codebook 修订、不同家族**的模型当参考, 两项指标依然达标 ——
   这比「五个 MiniMax 互相比」强, 后者可能是同族共享先验的**假收敛**。

## ★★★ 但本闸更重要的作用是钉住它**不是什么**
① **不是资格认证** —— 它不把任何标注者变成 QUALIFIED。
② **不是人工金标** —— 参考者是模型; 阳性对照 5/5 的 Wilson 下界只有 **0.5655**。
③ **不是「codebook 对不对」的检验** —— 两边用的是**逐字相同的 prompt**(含 KNOT_BRIEF/决策树/负例句),
   共享同一份 codebook。它检验的是「**不同家族对同一 codebook 的解读是否一致**」。
④ **不恢复外部独立性** —— 这 81 条仍是参与过开发决策的那批。

## ★★ 唯一崩掉的类: suspend
逐类一致 **0/5**。但**关键不是跨家族分歧**:
· MiniMax 五员在这 5 条上**内部全票一致 0/5**(其余 76 条 52.6%)
· 共识权重只有 **0.37~0.47** —— 是「最高票」不是共识
· GLM 给这 5 条的 suspend 权重**全是 0.00**, 且它全 81 条只判 1 条 suspend
· Fisher 单侧 **p=0.00045**
⇒ **suspend 是一个连内部都立不住的类。这与 belong 的「采样框错配」是两种不同的病。**
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
X = ROOT / "tests/data/cross_family_reference_81.json"
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def _wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (max(0.0, c - h), min(1.0, c + h))


def test_the_two_metrics_meet_the_gk1_thresholds():
    h = _j(X)["★★★headline"]
    assert "91.4%" in h["top2_命中"] and "✅" in h["top2_命中"]
    assert "0.2236" in h["平均_JS"] and "✅" in h["平均_JS"]
    # ★ 现算 Wilson, 不信任落盘
    lo, hi = _wilson(62, 81)
    assert abs(lo - 0.6625) < 1e-3 and abs(hi - 0.8444) < 1e-3, f"★ Wilson 现算 [{lo:.4f},{hi:.4f}] 与落盘不符"


def test_it_is_pinned_as_not_a_qualification():
    """★★★ 最容易被误读的一条: 这不是「G-K1 通过」。"""
    d = _j(X)
    t = d["★★★headline"]["★★reading"]
    assert "不能**由此宣称" in t or "不能由此宣称" in t, "★★★ 那句「不能宣称通过」不见了"
    assert "产物质量证据" in t and "不是资格认证" in t
    n = json.dumps(d["★★what_this_is_and_is_not"], ensure_ascii=False)
    assert "不是** human-adjudicated" in n or "不是 human-adjudicated" in n
    assert "0.5655" in n, "★ 阳性对照的 Wilson 下界不见了 —— 少了它 5/5 会被读成「可靠」"
    assert "我自己不能当" in n, "★★ 「作者不能当独立复核者」这条不见了"


def test_the_shared_codebook_limit_is_stated():
    """★★ 两边用逐字相同的 prompt ⇒ 检验的不是 codebook 本身。"""
    t = json.dumps(_j(X)["★★what_this_does_not_settle"], ensure_ascii=False)
    assert "逐字相同的 prompt" in t and "共享的是同一份 codebook" in t, \
        "★★ 那条最容易被忽略的限度不见了 —— 少了它，本轮会被当成「codebook 被验证了」"
    assert "不是" in t and "codebook 本身对不对" in t


def test_suspend_broke_and_the_diagnosis_is_internal_not_cross_family():
    """★★★ suspend 的病因必须写对: 内部就不稳, 不是跨家族分歧。"""
    s = _j(X)["★★★the_one_class_that_broke"]
    assert s["class"] == "**suspend**"
    t = s["★★but_it_is_not_a_cross_family_disagreement"]
    assert "内部全票一致 0/5" in t, "★ 「内部就不一致」这个关键事实不见了"
    assert "0.37~0.47" in t and "最高票" in t, "★ 共识权重不过半这条不见了"
    assert "连内部都立不住" in t
    assert "0.00045" in s["★fisher"]
    # ★ 与 belong 的区分必须在
    b = s["★★this_is_a_different_disease_from_belong"]
    assert "采样框错配" in b, \
        "★★★ 「两种不同的病」这个区分不见了 —— 少了它，suspend 会被当成第二个 belong 去换语料"
    # ★★ 2026-09-08: 原断言要求这里写「构念本身的问题」。**那句已降级为待检验假设** ——
    #   查库后发现反面证据: suspend 在**自制的、姿态极端的文本**上稳定读成 0.7,
    #   且驱动了真实改稿决策(对齐分归零 → 三版改稿 → display 0.92 过闸)。
    #   ⇒ 测量证据与使用证据**并存且指向不同处置**, 不能直接推出「构念坏了」。
    assert "降级为待检验假设" in b, \
        "★★★ 降级说明不见了 —— 少了它, 「构念本身坏了」这个**过强**的结论会被当成定论"
    assert "信号强度" in b, "★ 那个可检验的替代解释(可靠性依赖信号强度)不见了"
    assert "构念本身的问题" not in b, \
        "★★ 那句过强的断言又回来了 —— 它与同文件的降级说明**互相矛盾**"


def test_the_counter_evidence_is_recorded_with_its_source():
    """★★ 反面证据必须带出处 —— 它是从库里查出来的, 不是推出来的。"""
    c = _j(X)["★★★the_counter_evidence_i_found_in_memory_2026-09-08"]
    a = c["①_downstream_efficacy"]
    assert "2026-08-12" in a["source"], "★ 出处不见了"
    assert "suspend 0.7" in a["★fact"] and "display 0.92" in a["★fact"], "★ 改稿三版的具体读数不见了"
    assert "对齐分归零" in a["★fact"], "★ 「驱动了真实决策」的机制不见了"
    b2 = c["②_it_keeps_landing_on_thresholds"]
    assert "50.0%" in b2["★fact"] and "相反判决" in b2["★fact"]
    assert "本轮仍不处置" in c["★still_frozen"]


def test_the_corroboration_i_missed_is_recorded():
    """★ Run C 的混淆诊断早就写了 itch|suspend 重叠 —— 我当时没深究。"""
    t = _j(X)["★★★the_one_class_that_broke"]["★corroborating_evidence_i_saw_earlier_but_did_not_follow"]
    assert "itch|suspend" in t and "我当时看到了但没深究" in t


def test_no_action_taken_on_suspend_this_round():
    """★★ 看到结果之后不许当场改判据 —— 处置必须先冻结。"""
    t = _j(X)["★★executable_next"]
    assert "不在本轮做" in t, "★★★ 「本轮不处置」的声明不见了 —— 少了它就是用结果选规则"
    assert "必须先冻结判据" in t
    # ★ 现算确认: taxonomy 里 suspend 的判别式**没被改**
    taxo = _j(ROOT / "config/knot_taxonomy.json")
    sus = [k for k in taxo["knots"] if k["key"] == "suspend"][0]
    assert "决策被**明确悬置**" in sus["hard_discriminant"], \
        "★★★ suspend 的判别式被改了 —— 而本轮明确写了「不在本轮做」"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(X)
    bad = copy.deepcopy(d)
    bad["★★★the_one_class_that_broke"]["★★but_it_is_not_a_cross_family_disagreement"] = "跨家族分歧。"
    g["_j"] = lambda p: bad if p == X else saved(p)
    try:
        test_suspend_broke_and_the_diagnosis_is_internal_not_cross_family()
        raise SystemExit("★ 反向验证失败: 把病因改成「跨家族分歧」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★what_this_does_not_settle"] = ["无限度。"]
    g["_j"] = lambda p: bad2 if p == X else saved(p)
    try:
        test_the_shared_codebook_limit_is_stated()
        raise SystemExit("★ 反向验证失败: 抹掉共享 codebook 限度后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad3 = copy.deepcopy(d)
    bad3["★★executable_next"] = "已修改 suspend 的判别式。"
    g["_j"] = lambda p: bad3 if p == X else saved(p)
    try:
        test_no_action_taken_on_suspend_this_round()
        raise SystemExit("★ 反向验证失败: 声称已改判据后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_the_two_metrics_meet_the_gk1_thresholds()
    test_it_is_pinned_as_not_a_qualification()
    test_the_shared_codebook_limit_is_stated()
    test_suspend_broke_and_the_diagnosis_is_internal_not_cross_family()
    test_the_counter_evidence_is_recorded_with_its_source()
    test_the_corroboration_i_missed_is_recorded()
    test_no_action_taken_on_suspend_this_round()
    n = _reverse_checks()
    h = _j(X)["★★★headline"]
    lo, hi = _wilson(62, 81)
    print(f"test_cce_cross_family_reference: OK ("
          f"★★★跨家族参考: top1 62/81=76.5% Wilson [{lo:.3f},{hi:.3f}] · "
          f"**top2 91.4%(阈0.80)✅ · JS 0.2236(阈0.25)✅** | "
          f"★钉住它**不是**资格认证/人工金标/codebook 检验(两边逐字同 prompt) | "
          f"★★suspend 0/5 崩了(内部全票一致也 0/5, 共识权重 0.37~0.47) | "
          f"★★★但「构念本身坏了」**已降级为待检验假设** —— 查库发现它在**自制极端文本**上"
          f"稳定读 0.7 且驱动过真实改稿 ⇒ 可能只是**可靠性依赖信号强度** | "
          f"★本轮**不处置** suspend(现算确认判别式未被改) | {n} 条反向验证判红)")
