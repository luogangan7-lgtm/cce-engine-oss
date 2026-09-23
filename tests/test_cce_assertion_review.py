#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 离线复核本身。它会推翻我自己的 FAIL, 所以要钉住**它没有偷偷放水**。"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "tests/data/assertion_review_v2_offline.json").read_text(encoding="utf-8"))
A = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8"))
V = json.loads((ROOT / "results/gen8_shipping/verdict.json").read_text(encoding="utf-8"))


def test_bias_direction_is_declared_up_front():
    """★★★ 这次复核若判我错, FAIL 就消失。这个偏误方向必须**自己先说**。"""
    b = R["★★★★我先声明自己的偏误方向"]
    assert "FAIL 消失" in b and "最该被怀疑的方向" in b
    assert "一视同仁" in b and "不许只对造成 FAIL 的那 8 条网开一面" in b
    assert "也不许为了保住 FAIL 而硬撑" in b, "★ 两个方向都要挡, 只挡一边等于选边"


def test_principle_was_fixed_before_application_and_is_not_new():
    p = R["①先定原则"]
    for tag in ("(甲)", "(乙)", "(丙)", "(丁)"):
        assert tag in p["★★★判定原则"], f"★ 原则缺 {tag}"
    assert "不许靠常识补" in p["★这条原则不是我为本轮新造的"], \
        "★ 必须指出这条原则是我在「仅收藏」上已写下的那条 —— 否则它就是为本轮量身定做"


def test_all_eight_categories_were_actually_run_through_the_principle():
    """★ 原则要对全部 82 条一视同仁 —— 八类都要有判, 不能只判 display。"""
    c = R["②逐类套用"]
    assert len(c) == 8, f"★ 只套用了 {len(c)} 类"
    for k, v in c.items():
        assert v["判"] in ("**成立**", "**不成立, 撤销**"), f"★ {k} 判语不合法"
        assert v["依据"].startswith(("甲", "乙", "丙", "★★★ **丁")), f"★ {k} 没标依据类别"
    assert c["display(8)"]["判"] == "**不成立, 撤销**"
    assert sum(1 for v in c.values() if v["判"] == "**成立**") == 7


def test_the_two_alternative_routes_were_tried_and_reported_as_failing():
    """★ 我另外找过两条能救回 display 断言的路, 都不成立 —— 必须写出来, 不能只报结论。"""
    r = R["③我另外查过、也不成立的两条替代路线"]
    assert "恰好出现 2 次" in r["路线一_对象域"], "★ 对象域那条要给出实际文本证据"
    assert "只是用例, 不是定义" in r["路线一_对象域"]
    assert "从未定义" in r["路线二_need_status"] and "N01–N14 的含义在 taxonomy 里只有代号" in r["路线二_need_status"]
    assert "规范补完" in r["★结论"]


def test_withdrawn_assertions_are_kept_not_deleted():
    w = [a for a in A["断言"] if a["★★★断言状态"].startswith("**已撤销")]
    # ★★★ 2026-09-13: 原来钉的是「撤销 8 条」—— 那是 2026-09-10 **按类**撤销后的状态。
    #   当天逐条重判(probes/withdrawn_display_assertions_reclassify.py)发现: 其中 **6 条落 (乙)
    #   文本内正面反证**(原文里有正面陈述说取得尚未发生, 能指名片段), **不是 (丁) 证据缺席**
    #   ⇒ 6 条恢复, **只有 2 条**(明确放弃 ×2, 指不出片段)维持撤销。
    #   ★ 原则没错, 错在**一刀切地套** —— 8 条的撤销理由当时**逐字相同**, 即它是按类撤的。
    #   ⇒ 本条改钉 2, 并**另钉那 8 条一条都没被删**(见下)。
    assert len(w) == 2, f"★ 撤销了 {len(w)} 条, 应为 2(2026-09-13 重分类后)"
    MARKS = ("★★★撤销与恢复沿革", "★★★维持撤销的理由")
    all8 = [a for a in A["断言"] if any(m in a for m in MARKS)]
    assert len(all8) == 8, (
        "★★★ 2026-09-10 被撤销的那 8 条必须**一条不少地留着沿革**(恢复的与维持的都算), 实为 %d —— "
        "恢复不许变成「把撤销记录抹掉」" % len(all8))
    for a in all8:
        if "★★★撤销与恢复沿革" in a:
            g = a["★★★撤销与恢复沿革"]
            # ★ 锚在**键的前缀**上而不是我记忆里的全名(实际键是「★原文片段(代码逐字核过在原文里)」)。
            #   本仓反复踩「断言锚点按记忆写」—— 这里就踩了一次, 当场判红。
            spans = [v for k, v in g.items() if k.startswith("★原文片段")]
            assert spans and spans[0] and spans[0] in a["文本"], (
                "★★★ %s 恢复时指不出原文片段, 或片段不在原文里 —— 那它就该落 (丁)" % a["用例"])
            assert "P1 = 只含物" in str(g.get("★前提", "")), (
                "★★ %s 的恢复没写明它依赖 P1 —— P1 若改, 这条必须整体重判" % a["用例"])
    for a in w:
        assert a["★撤销理由"] and "沉默不是否定" in a["★撤销理由"]
        assert "撤销的是**我的断言可推导性**" in a["★撤销**不等于**判对了"]
        assert a["推导"], "★ 原推导被删了 —— 撤销要保留原记录"
    kept = [a for a in A["断言"] if a["★★★断言状态"] == "已裁定"]
    # ★★★ 每一项来源**具名现算**, 不硬编总数 —— 2026-09-14 又加了一批(P 支新断言),
    #   硬编的 80 当场判红, 而红的原因读起来像「对不上」, 实际是「少写了一项来源」。
    #   (84 行那处 74 查的是 **09-10 那份历史产物**, 不动。)
    restored = [a for a in kept if "★前提" in str(a.get("★★★2026-09-13 重分类", a))
                or "P1 = 只含物" in str(a.get("★前提", ""))]
    p_arm = [a for a in kept if "★★★与被撤那条的差别_这不是恢复" in a]
    terms = [("v2 冻结基数", 74), ("2026-09-13 重分类恢复", len(kept) - 74 - len(p_arm)),
             ("2026-09-14 P 支新断言", len(p_arm))]
    assert len(kept) == sum(n for _, n in terms) and len(p_arm) == 2, (
        f"★ 已裁定 {len(kept)} 条, 具名各项 {terms} —— "
        "要么真相源对不上, 要么**又加了一项来源却没在这里具名**")
    return len(w), len(kept)


def test_verdict_flip_is_recorded_with_all_four_brakes():
    f = V["★★★★2026-09-10 离线复核后改判"]
    assert f["★原判"].startswith("FAIL") and "PASS" in f["★改判"]
    assert f["现算复核"]["违例"] == 0 and f["现算复核"]["已裁定断言"] == 74
    # ★ 钉在**值**上: 必须说明「表缩小 ⇒ 证据变弱」, 而不是重复键名里的「更弱」
    assert "表缩小了证据强度就下降" in f["★★★这个 PASS 比原来的 PASS **更弱**"]
    assert "更小的表" in f["★★★这个 PASS 比原来的 PASS **更弱**"]
    brakes = f["★★★仍然不替换生产"]
    assert len(brakes) == 4, f"★ 只有 {len(brakes)} 条刹车"
    joined = " ".join(brakes)
    for must in ("DEV-001", "未裁定", "不等于", "不因候选 PASS 而结案"):
        assert must in joined, f"★ 刹车里缺: {must}"


def test_the_flip_cites_the_authorized_errata_path():
    f = V["★★★★2026-09-10 离线复核后改判"]
    assert "冻结不是禁止勘误" in f["★★★GPT 授权的勘误路径"]
    assert "永久保留一个已经知道为假的违例" in f["★★★GPT 授权的勘误路径"]


def test_recompute_is_reproducible_from_frozen_files():
    """★★★ 现算: 2026-09-13 恢复 6 条之后, gen8 那一轮的违例**回来了**。

    ★ 本条原来钉的是「0 违例 74 条」—— 那是 **09-10 撤销之后**的状态。
      今天逐条重判把 6 条恢复(它们落 (乙) 文本内正面反证, 不是 (丁) 证据缺席)
      ⇒ **gen8 的三个违例依据恢复** ⇒ 那一轮的 PASS 不再成立。
    ★★ 但**不得**据此说「候选代确实 FAIL 在这三条上」—— 2026-09-13 的 gen9 双臂重测
      (n=8, 判据测量前冻结)显示: 这三条在候选臂上**全部落 violation_is_noise**
      (众数占比 4/8 · 6/8 · 4/8), 而候选构造器**在更大的面上违反**(A 臂 display 27/48 = 56%),
      且有一条**稳定**违例落在这三条之外。⇒ gen8 抓到那三条**带抽样偶然性**。
    ⇒ 本条只钉「现算结果与恢复一致」, **结论层面交给 results/gen9_verdict.json**。
    """
    rows = {r["id"]: r for r in json.loads((ROOT / "results/gen8_shipping/rows.json").read_text(encoding="utf-8"))}
    adj = [a for a in A["断言"] if a["★★★断言状态"] == "已裁定"]
    viol = sorted({a["用例"] for a in adj
                   if rows.get(a["用例"], {}).get("top1")
                   == re.search(r"top1 != '(\w+)'", a["输出谓词"]).group(1)})
    # ★ 2026-09-14 新增的 P 支断言**具名分出**: 它们指向 C_明确放弃_0/1, gen8 三代皆判 inertia
    #   ⇒ 对下面的违例集合**不产生影响**。数要对得上, 但不许把新来源混进旧基数里。
    p_arm = [a for a in adj if "★★★与被撤那条的差别_这不是恢复" in a]
    assert len(adj) == 80 + len(p_arm), (
        f"★ 现算 {len(adj)} 条 = 80(v2 基数+重分类恢复) + {len(p_arm)}(P 支新断言)? 对不上")
    assert viol == ["C_★已决定_未来时间词_0", "C_已决定_延后执行_0", "C_已决定_延后执行_1"], (
        "★★★ gen8 现算违例集合变了: %r —— 恢复的那 6 条与 gen8 读数的对应关系必须重核" % viol)
    # ★ 结论的限定必须存在于判决文件里, 不许只写在这段 docstring 里
    g9 = json.loads((ROOT / "results/gen9_verdict.json").read_text(encoding="utf-8"))
    assert g9["★★★按冻结决策规则的判决"] == "FAIL_ON_NOISE"
    assert "方向是更不利" in json.dumps(g9["★★★不得据此说"], ensure_ascii=False)
    return len(adj), viol


def test_new_owner_item_was_opened_not_swallowed():
    """★★★ 撤销不等于问题消失 —— 它必须变成一个**新的 owner 待决项**。"""
    o = R["⑥★★★新增的 owner 待决项"]
    assert "对象域" in o["问题"] and "规范决定" in o["为什么必须由 owner 定"]
    assert "恢复" in o["★它决定了什么"] and "作废" in o["★它决定了什么"]
    memo = (ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md").read_text(encoding="utf-8")
    assert "对象域" in memo, "★ 新待决项没进交办件"


if __name__ == "__main__":
    test_bias_direction_is_declared_up_front()
    test_principle_was_fixed_before_application_and_is_not_new()
    test_all_eight_categories_were_actually_run_through_the_principle()
    test_the_two_alternative_routes_were_tried_and_reported_as_failing()
    w, k = test_withdrawn_assertions_are_kept_not_deleted()
    test_verdict_flip_is_recorded_with_all_four_brakes()
    test_the_flip_cites_the_authorized_errata_path()
    test_recompute_is_reproducible_from_frozen_files()
    test_new_owner_item_was_opened_not_swallowed()
    print("test_cce_assertion_review: OK ("
          "★★★★复核**先声明偏误方向**(判我错则 FAIL 消失), 原则**先定后套**且对八类一视同仁 | "
          "★原则: 可推导 ⟺ (甲)文本内属性 / (乙)文本内正面反证 / (丙)合同明文二值前置; "
          "**不得**(丁)文本外事实的证据缺席 —— 这就是我在「仅收藏」上已写下的那条 | "
          f"★★★撤销 **{w}** 条 display(依据丁: 「已拥有**或**已经历」是析取, 文本对第二支**沉默**, 沉默不是否定), "
          f"维持 **{k}** 条(依据甲/乙/丙) | "
          "★另找的两条救回路线(对象域 / need_status)**都不成立**, 已写出证据而非只报结论 | "
          "★★09-10 那轮现算复核: 74 条 · **0 违例** ⇒ FAIL 改判 PASS(**历史记录, 已被 09-13 重分类取代**) | "
          "★★★09-13 重分类: 8 条一刀切撤销 ⇒ **恢复 6(乙·能指名原文片段) / 维持 2(丁)**, 表 74→80, "
          "gen8 三违例依据**回来了**; 但 gen9 双臂重测显示这三条**全落噪声**而候选在**更大面上违反**(A 臂 56%) | "
          "★★★但四条刹车全在: DEV-001 偏离 · 表缩小⇒证据更弱 · 撤销项变新待决项 · 旧缺陷不结案 | "
          "★撤销条目**原推导保留未删**)")
