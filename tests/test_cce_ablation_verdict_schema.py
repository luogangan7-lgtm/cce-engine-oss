"""消融判决表的 schema 闸 —— 判决必须带工况, 且「装饰」这个词被废除。

## 为什么要有这条闸
两轮消融审计(2026-09-05/06, 合计 88 个 agent)的**系统性错误**是:
都在问「换成平凡基线后输出会不会变」, **却从没定义过「相对于什么工况」**。
· 第一轮的隐含参照系 = **仪器指纹**(重言) ⇒ 20/20 全判承重
· 第二轮换成 = **存量语料**(单点: 硬编 --intl + 单一 profile + k∈{3,5} + 合成单语种语料)
  ⇒ 13/30 判装饰
**参照系换了, 但「参照系本身要先被验收」这一步, 两轮都没做。**

★★ 后果是可预测的: **一个只在存量数据上做的消融审计, 天然会把所有保险丝判成装饰** ——
因为保险丝的定义就是「平时永远不动」, 而「不可达」与「不承重」在**单一工况上观测不可区分**。

## 这条闸强制三件事
1. **`DECORATIVE` 这个词被废除。** 它把两种东西合并了, 而它们的处置**相反**。
2. **每条判决必须能追到工况**, 且工况在**测试时被重新实测** ——
   ★ 一旦工况漂移(比如有人拿掉了硬编的 `--intl`), 依赖它的 UNREACHABLE 判决**当场失效**,
   这条闸会红。工况是活的, 不是一句陈年注解。
3. **`deletable` 与 verdict 分离。** NO_CONSUMER **不蕴含**可删 ——
   audio.capabilities / prosody 都是真没消费者, 结论却是「**该接线不该删**」;
   sesoi 的产出**就是一次拒绝**, 删了读者会以为问题已被回答。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "tests" / "data" / "ablation_verdicts_v2.json"

ALLOWED = {"LOAD_BEARING_L2", "LOAD_BEARING_L1_ONLY", "NO_CONSUMER",
           "UNREACHABLE", "CIRCULAR", "INCONCLUSIVE", "COULD_NOT_RUN"}
BANNED = {"DECORATIVE"}


def _load():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_the_word_decorative_is_retired():
    """★ 裸的 `DECORATIVE` 不许再作为判决出现 —— 只允许在解释里作为**历史标签**提及。"""
    d = _load()
    for v in d["verdicts"]:
        assert v["verdict"] not in BANNED, (
            f"★ {v['component']}: 判决仍是 {v['verdict']} —— 这个词合并了两种处置相反的东西, "
            "必须拆成 NO_CONSUMER(真死) 或 UNREACHABLE(本工况不可达)"
        )
        assert v["verdict"] in ALLOWED, f"★ 未知判决 {v['verdict']}"


def test_every_verdict_carries_an_operating_point():
    d = _load()
    assert "★operating_point" in d, "★ 判决表没有工况块 —— 没有工况的判决没有意义"
    for v in d["verdicts"]:
        assert v.get("operating_point_ref"), f"★ {v['component']} 没有指向工况"


def test_unreachable_must_say_what_would_make_it_reachable():
    """★ UNREACHABLE 不写「什么条件下它会活」, 就只是「我不知道」换了个说法。"""
    d = _load()
    n = 0
    for v in d["verdicts"]:
        if v["verdict"] != "UNREACHABLE":
            continue
        n += 1
        cond = v.get("what_would_make_it_reachable")
        assert cond and len(cond) > 5, (
            f"★ {v['component']} 判 UNREACHABLE 却没写达成条件 —— "
            "那与「查不了」无异, 而本项目禁止把「查不了」写成结论"
        )
    assert n >= 1, "★ 一条 UNREACHABLE 都没有 —— 检查表是否被改坏"


def test_deletable_is_independent_of_verdict():
    """★★ 核心: `deletable` 不许由 verdict 推导出来。

    若「NO_CONSUMER ⇒ 可删」成立, 这个字段就是冗余的; 而它**不成立** ——
    表里必须存在 NO_CONSUMER 且 deletable=false 的条目, 否则说明有人把它退化成了别名。
    """
    d = _load()
    nc = [v for v in d["verdicts"] if v["verdict"] == "NO_CONSUMER"]
    assert nc, "★ 没有 NO_CONSUMER 条目"
    not_deletable = [v for v in nc if not v.get("deletable")]
    assert not_deletable, (
        "★★ 所有 NO_CONSUMER 都被标成可删 ⇒ `deletable` 退化成了 verdict 的别名。"
        "而实测存在反例: audio.capabilities / prosody 真没消费者, 结论却是「该接线不该删」"
    )
    for v in d["verdicts"]:
        assert "deletable" in v, f"★ {v['component']} 缺 deletable"
        assert v.get("deletable_why"), f"★ {v['component']} 的 deletable 没写理由"
    # UNREACHABLE 一律不可删 —— 它是保险丝
    for v in d["verdicts"]:
        if v["verdict"] == "UNREACHABLE":
            assert not v["deletable"], (
                f"★ {v['component']} 判 UNREACHABLE 却标为可删 —— "
                "本工况不可达 ≠ 无用。删它就是拆保险丝。"
            )


def test_operating_point_is_still_true_right_now():
    """★★★ 工况必须**现测**, 不是陈年注解。

    一旦工况漂移, 依赖它的 UNREACHABLE 判决就失效 —— 这条闸必须当场红,
    而不是让一张过期的判决表继续被引用。
    """
    d = _load()
    op = d["★operating_point"]

    # ① market: --intl 是否仍是无条件硬编
    src = (ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8")
    still_hardcoded = '"--intl"' in src
    assert still_hardcoded == (op["market"]["value"] == "intl"), (
        "★★ 工况漂移: cce_full_run 里 `--intl` 的硬编状态变了 ⇒ "
        "所有依赖 market=intl 的 UNREACHABLE 判决(adlaw_cn 等)**当场失效**, 必须重判"
    )

    # ② profile 表里有哪些 key
    prof = list(json.loads((ROOT / "data" / "compliance_profiles.json")
                           .read_text(encoding="utf-8")).get("profiles", {}).keys())
    assert prof == op["guard_profile"]["profiles_available_in_config"], (
        f"★★ 工况漂移: compliance_profiles 的 key 从 "
        f"{op['guard_profile']['profiles_available_in_config']} 变成 {prof} ⇒ "
        "三张 PROFILE_* 表的 UNREACHABLE 判决必须重判"
    )

    # ③ 语料指纹
    import hashlib
    for rel, want in op["corpus_sha"].items():
        got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]
        assert got == want, (
            f"★★ 语料漂移: {rel} 的 sha 从 {want} 变成 {got} ⇒ "
            "在它上面做出的判决**不再适用于当前语料**, 需重跑"
        )


def test_needs_rerun_is_recorded_not_swallowed():
    """审计期间语料被污染过的那几条, 必须**显式标注需重跑**, 不许当作有效判决用。"""
    d = _load()
    n = sum(1 for v in d["verdicts"] if "★needs_rerun" in v)
    assert n == d["★needs_rerun_count"] and n >= 1, (
        "★ 受污染判决的标注数对不上 —— 那是把「结论可能是错的」这件事悄悄抹掉了"
    )


def test_tally_matches_rows():
    d = _load()
    t = {}
    for v in d["verdicts"]:
        t[v["verdict"]] = t.get(v["verdict"], 0) + 1
    assert t == d["★tally"], f"★ 汇总与明细不符: {t} vs {d['★tally']}"


def _reverse_checks():
    """反向验证: 破坏各条前提, 闸必须判红。全部在内存里做, 不写文件。"""
    import copy
    n = 0
    base = _load()
    g = globals()
    orig = g["_load"]

    def with_(mut):
        d = copy.deepcopy(base)
        mut(d)
        return lambda: d

    cases = [
        ("退回 DECORATIVE", test_the_word_decorative_is_retired,
         lambda d: d["verdicts"][0].__setitem__("verdict", "DECORATIVE")),
        ("UNREACHABLE 不写达成条件", test_unreachable_must_say_what_would_make_it_reachable,
         lambda d: [v.pop("what_would_make_it_reachable", None)
                    for v in d["verdicts"] if v["verdict"] == "UNREACHABLE"]),
        ("把 deletable 退化成 verdict 的别名", test_deletable_is_independent_of_verdict,
         lambda d: [v.__setitem__("deletable", True)
                    for v in d["verdicts"] if v["verdict"] == "NO_CONSUMER"]),
        ("UNREACHABLE 标成可删", test_deletable_is_independent_of_verdict,
         lambda d: [v.__setitem__("deletable", True)
                    for v in d["verdicts"] if v["verdict"] == "UNREACHABLE"]),
        ("抹掉需重跑标注", test_needs_rerun_is_recorded_not_swallowed,
         lambda d: [v.pop("★needs_rerun", None) for v in d["verdicts"]]),
        ("汇总与明细不符", test_tally_matches_rows,
         lambda d: d["★tally"].__setitem__("LOAD_BEARING_L2", 999)),
        ("工况里的语料 sha 过期", test_operating_point_is_still_true_right_now,
         lambda d: d["★operating_point"]["corpus_sha"].__setitem__(
             "config/knot_taxonomy.json", "deadbeefdeadbeef")),
    ]
    for name, fn, mut in cases:
        g["_load"] = with_(mut)
        try:
            fn()
            raise SystemExit(f"★ 反向验证失败: 「{name}」后 {fn.__name__} 仍绿")
        except AssertionError:
            n += 1
        finally:
            g["_load"] = orig
    return n


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 2026-09-07 补: probe 自己说「本轮判决作废」, 而**没有任何测试在读它**
# ──────────────────────────────────────────────────────────────────────────
# knot_taxonomy 的消融 probe 带阳性/阴性对照, 不过就在 stdout 打印
# 「对照: ★★ 未通过 —— 本轮判决作废」。但 CI 里一条闸都没断言 `controls_passed`
# ⇒ **probe 判自己作废, 测试照样绿**。与本仓反复栽的「结果报了但不进判决」同族。
#
# ★★ 而它当时确实是红的, 原因比「忘了断言」更根本:
#    消融的 `code_refs` 在源码里 grep 字段名, **命中了 consistency_check.py 的
#    `TOPLEVEL_DOC_ONLY` 登记表** —— 那张表逐字列着 8 个 changelog 的名字。
#    ⇒ **「声明它没有消费者」这个动作本身, 被算成了一个消费者。**
#    ⇒ 8 条纯文档全被推成 INCONCLUSIVE, 阴性对照(纯文档必须判 NO_CONSUMER)长期红。
#    修法不是给对照开后门, 而是 code_refs **先按 AST 挖掉登记表的行区间** ——
#    因为这是**系统性偏置**: 任何登记进 TOPLEVEL_DOC_ONLY / DESCRIPTIVE 的字段,
#    都永远拿不到 NO_CONSUMER。越诚实地记录一个死字段, 它看起来越活。
#    实测修完 **14 个字段从 INCONCLUSIVE 掉到 NO_CONSUMER**(24→10, 1→15)。
# ══════════════════════════════════════════════════════════════════════════
KT = ROOT / "tests" / "data" / "knot_taxonomy_ablation.json"


def test_ablation_controls_are_actually_enforced():
    """★ probe 的对照结论必须**进判决**, 不许只打印。"""
    d = json.loads(KT.read_text(encoding="utf-8"))
    c = d["controls"]
    assert d["controls_passed"] is True, (
        f"★★★ 消融的对照未通过 ⇒ **本轮判决作废**, 不得引用 tally/rows: {c}")
    assert c["positive_knots_key"]["passed"], "★ 阳性对照(knots[].key 必须承重)未过 ⇒ 方法坏了"
    assert c["negative_changelogs"]["passed"], (
        "★ 阴性对照(纯 changelog 必须判 NO_CONSUMER)未过 ⇒ 判据是重言式的")
    assert c["negative_changelogs"]["verdicts"] == ["NO_CONSUMER"], \
        f"★ 阴性对照出现了非 NO_CONSUMER 的判决: {c['negative_changelogs']['verdicts']}"


def test_ref_counter_excludes_declaration_registries():
    """★★ 计数器不许再被登记表骗 —— 这是它判死规则的能力本身。"""
    src = (ROOT / "probes" / "knot_taxonomy_ablation.py").read_text(encoding="utf-8")
    assert "_srcs_without_registries" in src and "_REGISTRY_NAMES" in src, \
        "★ code_refs 不再剔除声明式登记表 ⇒ 登记一个死字段就会让它看起来是活的"
    cc = (ROOT / "scripts" / "consistency_check.py").read_text(encoding="utf-8")
    import ast as _ast
    names = {t.id for n in _ast.walk(_ast.parse(cc)) if isinstance(n, _ast.Assign)
             for t in n.targets if isinstance(t, _ast.Name) and t.id.isupper()
             and isinstance(n.value, (_ast.Set, _ast.List, _ast.Tuple, _ast.Dict))}
    import re as _re
    known = set(_re.search(r"_REGISTRY_NAMES = \{(.*?)\}", src, _re.S).group(1).replace('"', "").split(", "))
    missed = {n for n in names if ("DOC_ONLY" in n or "DESCRIPTIVE" in n or "EXEMPT" in n)} - known
    assert not missed, (
        f"★★ consistency_check 新增了声明式登记表 {missed} 但 _REGISTRY_NAMES 没跟上 ⇒ "
        "计数器会再次被自己骗")


def test_dead_changelogs_are_no_consumer_not_inconclusive():
    """把那 14 个字段的迁移钉住 —— 一旦它们又变回 INCONCLUSIVE, 说明偏置回来了。"""
    d = json.loads(KT.read_text(encoding="utf-8"))
    ch = [r for r in d["rows"] if r["field"].startswith("changelog")]
    assert ch and all(r["verdict"] == "NO_CONSUMER" for r in ch), \
        f"★ changelog 不再全是 NO_CONSUMER: {[(r['field'], r['verdict']) for r in ch]}"
    assert all(r["code_refs"] == 0 for r in ch), \
        f"★ 纯 changelog 又拿到非零引用数了: {[(r['field'], r['code_refs']) for r in ch]}"
    assert d["tally"].get("NO_CONSUMER", 0) >= 9, \
        f"★ NO_CONSUMER 只剩 {d['tally'].get('NO_CONSUMER')} 个 —— 修完应有 15 个左右"


if __name__ == "__main__":
    test_the_word_decorative_is_retired()
    test_every_verdict_carries_an_operating_point()
    test_unreachable_must_say_what_would_make_it_reachable()
    test_deletable_is_independent_of_verdict()
    test_operating_point_is_still_true_right_now()
    test_needs_rerun_is_recorded_not_swallowed()
    test_tally_matches_rows()
    test_ablation_controls_are_actually_enforced()
    test_ref_counter_excludes_declaration_registries()
    test_dead_changelogs_are_no_consumer_not_inconclusive()
    n = _reverse_checks()
    d = _load()
    print("test_cce_ablation_verdict_schema: OK ("
          f"{len(d['verdicts'])} 条判决 {d['★tally']} | "
          "「DECORATIVE」已废除 | UNREACHABLE 逐条写明达成条件 | "
          f"deletable 与 verdict 分离(可删仅 {d['★deletable_count']} 条) | "
          "工况**现测**(--intl 硬编 / profile key / 三份语料 sha)一旦漂移即红 | "
          "★消融对照**进判决**(此前只打印) | 计数器不再被登记表骗 | "
          f"{d['★needs_rerun_count']} 条受污染判决显式标注 | "
          f"{n} 条反向验证各自判红)")