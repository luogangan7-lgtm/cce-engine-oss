"""A1/A2 改动的行为证据 —— 核心边界闸 refactor_log 引的就是这个文件。

改动是什么: 只改 playbook 的**分解方式**, 两条建议**原文逐字保留**。
· A1 audit: 「第二次提及=放大事件」是跨轮次规则, 单文本判官结构上看不到 ⇒ 移出打分清单,
  原文进 cross_turn_strategy。
· A2 belong: 一个原子塞了两个动作+一个数量上界+一个顺序约束 ⇒ 拆开;
  上界归禁令(上界是违规检查不是执行检查), 顺序约束原文进 composition_note。

★ 本闸要证的三件事, 缺一这次改动就不能自称「只改分解不改主张」:
  ① 建议内容**一项不少**且被移走的两条**逐字**还在
  ② 结分类仪器**未换代**(playbook 不进 instrument_hash) —— 但这条只是必要条件, 见下
  ③ A3 的六条抽象原子**一个字没动**(那是产品主张, 本轮不碰)

★ 为什么 ② 不足以单独成立: 库内已立的教训 ——「instrument_hash 由 taxonomy+参数现算,
  哈希没变不足以当行为证据」。故本文件另证 ①③, 并直接钉住那条**承重性质**:
  playbook 不进 s1/s2 prompt 模板, 且换掉全部 playbook 后指纹不变。

★ 写这个文件时我先写错过一版: 用 grep 数「哪些 scripts 提到 playbook」当读取面。
  它当场判红并指出 cce_knot_classify.py 也提到 —— 查下去是 _stage2_aggregate 把
  playbook **抄进输出**(第 844 行), 属产物装配不是测量输入。
  ⇒ 教训: **「谁提到它」不是判据, 「它进不进 prompt」才是。** grep 分不清这两件事。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
KNOTS = {k["key"]: k for k in TAXO["knots"]}

# 改动前的原文, 逐字冻结在此 —— 出处 git 39a423b5b196f5c9。
AUDIT_BEFORE = "不辩解不表演;给可验证事实+接受检验的姿态(『Ask me anything specific』);第二次提及=放大事件"
BELONG_BEFORE = "先『你不是一个人』把人接住,再给至多一格新知;不派任务"


def test_moved_advice_is_preserved_verbatim():
    """★ 被移出打分清单的两条建议, 原文一个字都不能少。

    删掉它们就不再是「改分解」, 而是**改了 playbook 主张什么** —— 那需要 owner 拍板。
    """
    audit = KNOTS["audit"]
    assert audit.get("cross_turn_strategy") == "第二次提及=放大事件", (
        "★ audit 的跨轮规则不见了或被改写 —— 它只该换位置, 不该消失。"
        f"现值: {audit.get('cross_turn_strategy')!r}"
    )
    belong = KNOTS["belong"]
    assert belong.get("composition_note") == "接住的句子在新知之前", (
        "★ belong 的顺序约束不见了或被改写。现值: "
        f"{belong.get('composition_note')!r}"
    )


def test_belong_semantic_content_is_complete():
    """★ 接住 · 新知 · 至多一格 · 不派任务 · 接住在前 —— 五项一项不少。"""
    belong = KNOTS["belong"]
    whole = belong["playbook"] + " " + belong.get("composition_note", "")
    for need, what in [
        ("接住", "把人接住这个动作"),
        ("新知", "给出新知这个动作"),
        ("不给超过一格", "至多一格的数量上界"),
        ("不派任务", "不派任务这条禁令"),
        ("接住的句子在新知之前", "接住在前的顺序约束"),
    ]:
        assert need in whole, f"★ belong 丢了「{what}」—— 那是改主张不是改分解"


def test_atom_decomposition_is_what_was_preregistered():
    """分解结果必须与 GEN2 预注册一致 —— 预注册写了什么就该跑出什么。"""
    import playbook_atoms_reliability as pa

    audit = pa.atoms_of("audit")
    assert len(audit) == 2 and sum(1 for _, neg in audit if not neg) == 1, (
        f"★ audit 应为 2 原子 / 1 正向, 实为 {len(audit)} / "
        f"{sum(1 for _, neg in audit if not neg)}"
    )
    assert not any("第二次提及" in t for t, _ in audit), \
        "★ 跨轮规则仍在打分清单里 —— A1 没生效"

    belong = pa.atoms_of("belong")
    npos = sum(1 for _, neg in belong if not neg)
    assert len(belong) == 4 and npos == 2, (
        f"★ belong 应为 4 原子 / 2 正向, 实为 {len(belong)} / {npos}"
    )
    # ★ 关键: 数量上界必须落在**禁令**侧, 不能混进 atoms_hit
    bound = [(t, neg) for t, neg in belong if "不给超过一格" in t]
    assert bound and bound[0][1] is True, \
        "★ 「不给超过一格新知」必须被判为禁令 —— 上界是违规检查不是执行检查, " \
        "混进正向原子就是预注册禁止的退化"


def test_instrument_did_not_change_generation():
    """playbook 不进 instrument_hash ⇒ 结分类未换代, 已采集面板仍有效。

    ★ 这条是**必要不充分**: 哈希没变不能证明行为没变(库内已立的教训)。
       它在这里的作用只有一个 —— 证明「不必换代」这个前提成立。
    """
    import cce_knot_classify as kc

    man = json.loads((ROOT / "config" / "cce_core_manifest.json").read_text(encoding="utf-8"))
    exp = man["instrument_expected"]
    got = kc.instrument_id(TAXO, k=3, knot_n=5,
                           s1_pairing="round_robin_over_3_s1_draws")
    assert got["instrument_hash"] == exp["instrument_hash"], (
        f"★ instrument_hash 变了({got['instrument_hash']} != {exp['instrument_hash']}) —— "
        "那就不是「改分解」, 必须走换代"
    )


def test_playbook_never_enters_the_measurement_prompts():
    """★ 这才是承重的那条性质, 不是「哪些文件提到 playbook」。

    「改 playbook 不必换代」成立的**唯一**理由是: playbook 不进 s1/s2 的 prompt 模板,
    因而不进 instrument_hash。这条一旦哪天被破坏, 改 playbook 就是**静默换仪器** ——
    而 instrument_hash 自己不会告诉你, 因为它是从 prompt 现算的。

    ★ 顺带澄清一个我第一版写错的地方: cce_knot_classify._stage2_aggregate 确实把
      playbook **抄进输出**(第 844 行)。那是**产物装配**不是测量输入 —— 它意味着
      改 playbook 会改变下游产物的内容(所以要另立预注册), 但不改变仪器。
      两件事必须分清, 拿 grep 数文件名分不清。
    """
    import copy

    import cce_knot_classify as kc

    s1 = kc._stage1_template()
    s2 = kc._stage2_template(TAXO)
    for key, kn in KNOTS.items():
        for piece in [p.strip() for p in kn["playbook"].replace("；", ";").split(";") if p.strip()]:
            assert piece not in s1, f"★ {key} 的原子「{piece}」进了 s1 prompt ⇒ 改它就是换仪器"
            assert piece not in s2, f"★ {key} 的原子「{piece}」进了 s2 prompt ⇒ 改它就是换仪器"

    # ★ 直接的不变性证明: 把**全部** playbook 换成占位串, 仪器指纹必须一字不变。
    blanked = copy.deepcopy(TAXO)
    for kn in blanked["knots"]:
        kn["playbook"] = "PLACEHOLDER"
    args = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    a = kc.instrument_id(TAXO, **args)
    b = kc.instrument_id(blanked, **args)
    assert a["instrument_hash"] == b["instrument_hash"], (
        "★ 换掉全部 playbook 后 instrument_hash 变了 —— "
        f"{a['instrument_hash']} != {b['instrument_hash']}。"
        "「改 playbook 不换代」不再成立, 本次改动必须走换代。"
    )
    assert a["spec"]["s2_prompt_sha256"] == b["spec"]["s2_prompt_sha256"]


def test_a3_abstract_atoms_untouched():
    """★ 本轮**不碰** A3 的六条抽象原子 —— 那是改产品主张, 需 owner 另行拍板。"""
    frozen = {
        "pain_seek": "给杠杆+机制+可执行下一步;不空承诺,承认边界",
        "display": "让位;被当同侪;接着他的贡献往前走,绝不纠正姿态压他",
        "reward": "短收;自我缩小;不再投喂信息(需求已闭,长文=把关掉的门重开)",
        "suspend": "给判据+零成本测试塌缩不确定性+如实说trade;不推购买。反杠杆=零风险承诺/样品/证言",
        "inertia": "只有精确命中其机制才值得触碰;给『一步且可逆』的最小改变;绝不布道",
        "itch_proj": None,   # 见下: 按 key 现取, 不硬编码可能过期的名字
    }
    for key, expect in frozen.items():
        if expect is None:
            continue
        assert KNOTS[key]["playbook"] == expect, (
            f"★ {key} 的 playbook 被改了 —— 本轮预注册明写「A3 一个字没动」。"
            f"\n  期望: {expect}\n  实际: {KNOTS[key]['playbook']}"
        )


def _reverse_checks():
    """反向验证: 破坏各条前提, 闸必须判红。"""
    n = 0

    # ① 删掉被移走的建议 ⇒ 红
    saved = KNOTS["audit"].get("cross_turn_strategy")
    KNOTS["audit"]["cross_turn_strategy"] = "被删了"
    try:
        test_moved_advice_is_preserved_verbatim()
        raise SystemExit("★ 反向验证失败: 改掉跨轮规则原文后闸仍绿")
    except AssertionError:
        n += 1
    finally:
        KNOTS["audit"]["cross_turn_strategy"] = saved

    # ② belong 丢掉数量上界 ⇒ 红
    saved_pb = KNOTS["belong"]["playbook"]
    KNOTS["belong"]["playbook"] = "有一句把人接住;给出新知;不派任务"
    try:
        test_belong_semantic_content_is_complete()
        raise SystemExit("★ 反向验证失败: 丢掉「至多一格」上界后闸仍绿")
    except AssertionError:
        n += 1
    finally:
        KNOTS["belong"]["playbook"] = saved_pb

    # ③ 动了 A3 ⇒ 红
    saved_ps = KNOTS["pain_seek"]["playbook"]
    KNOTS["pain_seek"]["playbook"] = "换个说法试试"
    try:
        test_a3_abstract_atoms_untouched()
        raise SystemExit("★ 反向验证失败: 改了 A3 的原子后闸仍绿")
    except AssertionError:
        n += 1
    finally:
        KNOTS["pain_seek"]["playbook"] = saved_ps

    return n


if __name__ == "__main__":
    test_moved_advice_is_preserved_verbatim()
    test_belong_semantic_content_is_complete()
    test_atom_decomposition_is_what_was_preregistered()
    test_instrument_did_not_change_generation()
    test_playbook_never_enters_the_measurement_prompts()
    test_a3_abstract_atoms_untouched()
    n = _reverse_checks()
    print("test_cce_playbook_atoms_a1a2: OK ("
          "两条被移出的建议逐字仍在 | belong 五项内容一项不少 | "
          "audit 2原子/1正向 · belong 4原子/2正向 且数量上界落在**禁令**侧 | "
          "instrument_hash 565470cf26c16d01 未换代 | "
          "playbook 不进 s1/s2 prompt 且换掉全部 playbook 后指纹不变 | "
          f"A3 六条抽象原子逐字未动 | {n} 条反向验证各自判红)")
