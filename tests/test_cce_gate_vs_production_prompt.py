"""★★★ 验收闸的标注者 prompt 与生产 s2 分类器的 prompt **不是同一台仪器** —— 零 API。

## 为什么要一条闸守着它
2026-09-08 给 suspend 定修法时才发现: 改 `negative_examples_prompt`
**instrument_hash 一字不变** —— 因为生产 `_stage2_template` 根本不读它。
顺藤查下去发现两侧喂的分类学字段是**双向差异**(各独占 3 个), 不是包含关系。

★ 这**不是**「G-K1 有 bug」。G-K1 完全可以正当地只是一次信度研究。
   要防的是**读数被跨作用域引用** ——「G-K1 通过」被拿去支持「生产分类器可靠」。
   此前这件事**无处可查**, 所以它必然会被遗忘。

## 本闸只做两件事
① 字段清单**现算**, 与留档不符就红(防文档腐烂)。
② 钉死「改 negative_examples 不动 instrument_hash」这条**换代路由的事实依据** ——
   一旦它变了(比如有人把负例塞进生产 prompt), 换代路由就得重定, 必须红。
"""
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
DOC = ROOT / "tests" / "data" / "gate_vs_production_prompt_gap.json"
FIX_TARGET = "negative_examples_prompt"


def _live():
    import gate_vs_production_prompt_gap as P
    return P.fields()


def _doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


def _taxo():
    return json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))


def _ihash(taxo):
    import cce_knot_classify as CK
    r = CK.instrument_id(taxo, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    return (r[1] if isinstance(r, tuple) else r)["instrument_hash"]


def test_field_table_is_recomputed_not_copied():
    """★ 留档的字段表必须与源码**现算一致**, 否则文档会悄悄和 prompt 脱节。"""
    live, doc = _live(), _doc()
    assert doc["per_field"] == live, (
        f"★ 留档字段表与现算不符。现算={live}\n留档={doc['per_field']}\n"
        "⇒ 有人改了某一侧的 prompt。重跑 probes/gate_vs_production_prompt_gap.py 并复核结论。")


def test_the_difference_is_two_way_not_containment():
    """★★ 核心事实: **双向**各有独占字段 ⇒ 不能说「闸更严所以是乐观上界」。"""
    live = _live()
    only_gate = {k for k, v in live.items() if v["验收闸"] and not v["生产s2"]}
    only_prod = {k for k, v in live.items() if v["生产s2"] and not v["验收闸"]}
    assert only_gate and only_prod, (
        f"★ 差异不再是双向的(只有闸={only_gate} 只有生产={only_prod})。"
        "若两侧已被对齐, 这是**好事**, 但必须更新 gate_vs_production_prompt_gap.json 的结论 —— "
        "别让一句过时的「不可互相引用」继续挂着。")
    d = _doc()
    assert set(d["★only_the_gate_sees"]) == only_gate
    assert set(d["★only_production_sees"]) == only_prod
    assert "方向未知" in json.dumps(d, ensure_ascii=False), \
        "★ 「方向未知」这句必须留着 —— 我第一版就是在这里overclaim 成「乐观上界」的"


def test_negative_examples_does_not_enter_instrument_hash():
    """★★★ 换代路由的事实依据: 改负例 **不动 instrument_hash**。

    ⇒ 走「递增 instrument_generation」那条路是**错的** —— 那会假称结分类仪器变了,
      白白作废仍然有效的标定(manifest 第五条路自己写明的反模式)。
    """
    t0 = _taxo()
    t1 = copy.deepcopy(t0)
    for k in t1["knots"]:
        if k["key"] == "suspend":
            k[FIX_TARGET] = k[FIX_TARGET] + "; ★闸探针追加"
            break
    else:
        raise AssertionError("★ suspend 结不见了")
    assert _ihash(t0) == _ihash(t1), (
        "★★★ 负例现在**会**改变 instrument_hash 了 —— 说明有人把它接进了生产 prompt。"
        "这是好事(闸与生产对齐了), 但换代路由必须重定: 此时改负例就是真换仪器, 要走第一条路。")


def test_production_prompt_really_lacks_the_fix_target():
    """★ 直接断言生产 s2 prompt 里**找不到** suspend 的负例原文 —— 比查哈希更直白。"""
    import cce_knot_classify as CK
    t = _taxo()
    neg = [k for k in t["knots"] if k["key"] == "suspend"][0][FIX_TARGET]
    prod = CK._build_stage2_prompt(t, "<T>", {"tops": "<S>", "appraisal": "<A>"})
    assert neg[:30] not in prod, \
        "★ 生产 prompt 里出现了 suspend 负例 ⇒ 与上一条断言矛盾, 先查是哪一条错了"


def test_the_production_side_fail_reading_is_read_live_not_quoted():
    """★★ 文档说「生产侧已有一个 test-retest FAIL」—— 这句必须**从判决产物现读**。

    若哪天 K1 重跑转绿, 本条会红并强制更新说法 ——
    防止一句过时的「生产已 FAIL」永远挂在那里当结论。
    """
    v = json.loads((ROOT / "tests/data/phase2/k1_reliability_verdict.json").read_text(encoding="utf-8"))
    assert v["verdict"] == "FAIL", (
        f"★ K1 test-retest 现在判 {v['verdict']} —— 情况变了。"
        "请更新 tests/data/gate_vs_production_prompt_gap.json 里「生产侧已有一个 FAIL 读数」的说法。")
    failed = set(v["failed"])
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "32.1%" in d and "5/8" in d, "★ 文档引的两个失败读数必须与产物一致"
    assert len(failed) == 2, f"★ 失败项从 2 项变成 {len(failed)} 项 ⇒ 文档的「过 2 项败 2 项」已过时"
    rc = json.loads((ROOT / "tests/data/phase2/k1_rootcause_verdict.json").read_text(encoding="utf-8"))
    assert "稀有结" in rc["root_cause"], "★ K1 根因文本变了, 请复核文档里引用它的那段"
    assert "已诊断" in d or "根因" in d, (
        "★★ 文档引用了生产侧的 FAIL 却没带根因 —— 会被读成「有个没查清的大问题」。"
        "根因在 tests/data/phase2/k1_rootcause_verdict.json, 必须一起引。")
    assert "未被测量" not in d or "那是错的" in d, (
        "★★ 文档里不许出现没被更正的「生产是未被测量的仪器」—— 我第一版就是这么写错的")


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_live"]

    # ① 字段表脱节 ⇒ 红
    bad = copy.deepcopy(_live())
    bad["decision_tree"]["生产s2"] = True
    g["_live"] = lambda: bad
    try:
        test_field_table_is_recomputed_not_copied()
        raise SystemExit("★ 反向验证失败: 字段表脱节后仍绿")
    except AssertionError:
        n += 1

    # ② 差异变成单向包含 ⇒ 红(提醒更新结论)
    bad2 = copy.deepcopy(_live())
    for k in ("family", "levers_not_knots", "typical_codes"):
        bad2[k]["验收闸"] = True
    g["_live"] = lambda: bad2
    try:
        test_the_difference_is_two_way_not_containment()
        raise SystemExit("★ 反向验证失败: 差异变单向后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_live"] = saved

    # ③ 负例真被接进生产 prompt ⇒ 红
    import cce_knot_classify as CK
    real = CK._build_stage2_prompt
    t = _taxo()
    neg = [k for k in t["knots"] if k["key"] == "suspend"][0][FIX_TARGET]
    CK._build_stage2_prompt = lambda *a, **kw: real(*a, **kw) + neg
    try:
        test_production_prompt_really_lacks_the_fix_target()
        raise SystemExit("★ 反向验证失败: 负例进生产 prompt 后仍绿")
    except AssertionError:
        n += 1
    finally:
        CK._build_stage2_prompt = real
    return n


if __name__ == "__main__":
    test_field_table_is_recomputed_not_copied()
    test_the_difference_is_two_way_not_containment()
    test_negative_examples_does_not_enter_instrument_hash()
    test_production_prompt_really_lacks_the_fix_target()
    test_the_production_side_fail_reading_is_read_live_not_quoted()
    n = _reverse_checks()
    live = _live()
    og = sorted(k for k, v in live.items() if v["验收闸"] and not v["生产s2"])
    op = sorted(k for k, v in live.items() if v["生产s2"] and not v["验收闸"])
    print(f"test_cce_gate_vs_production_prompt: OK ("
          f"字段表现算一致 | **双向差异**: 只有闸 {og} · 只有生产 {op} | "
          f"改负例不动 instrument_hash(⇒ 换代路由不走第一条路) | "
          f"生产 prompt 确无 suspend 负例原文 | "
          f"生产侧 K1 test-retest **FAIL** 现读一致 | {n} 条反向验证判红)")
