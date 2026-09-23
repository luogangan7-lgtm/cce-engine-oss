"""★★★ 闸协议 v2 的启用验收 —— PASS 是真的, 但**代价必须随结论同行**。零 API。

## 结果(判据一字未改, 同一批 81 条评论)
| | v1 | v2 | 判据 |
|---|---|---|---|
| mean_top2 | 0.9040 | **0.8812** | ≥0.80 ✅ |
| mean_JS | 0.2190 | **0.2422** | ≤0.25 ✅ |
| **越 0.25 线的自助概率** | **7.3%** | **35.5%** | —— |

⇒ **修好一处边界的代价, 是整体一致性的越线概率涨了近 5 倍。**
余量从 0.031 缩到 **0.0078**(0.16 个跨对 SD; v1 的 0.55 个 SD 此前已被判「薄」)。

## ★★ 两个方向都得认
预注册写死: 「若 JS 落在 0.25 附近我会想说『在噪声范围内』—— **不许**。」
★ 反过来同样成立: **没越线就是没越线**。35.5% 是并列报告, **不能**被我事后拿来把 PASS 说成 FAIL。

## ★ 资格考必须精确说
五员**全部 5/5**, 但按三态判据**全部 UNRESOLVED**(Wilson 下界 0.566 < 0.90)。
status="OK" 的意思是「**面板可用**」, **不是**「全部合格」; qualified_only 是**空集**。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RES = ROOT / "tests" / "data" / "gate_protocol_v2_acceptance_result.json"
PRE = ROOT / "tests" / "data" / "gate_protocol_v2_acceptance_prereg.json"
MAN = ROOT / "config" / "cce_core_manifest.json"


def _have():
    return (V / "gate_v2_acceptance" / "gates_result.json").exists()


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def _live():
    return json.loads((V / "gate_v2_acceptance" / "gates_result.json").read_text(encoding="utf-8"))


def test_gk1_passed_on_the_unchanged_criteria():
    """★ 判据**一字未改**, 且现算两项均达标。"""
    if not _have():
        g = _res()["★★★G_K1_按冻结判据"]
        assert g["mean_top2_hit"]["verdict"] == "PASS" and g["mean_JS"]["verdict"] == "PASS"
        print("  ★ 降级: 无本机素材, 只核对产物判决")
        return
    k = _live()["G_K1v2_分布一致性"]
    assert k["mean_top2_hit"] >= 0.80, f"★ top2 {k['mean_top2_hit']} < 0.80"
    assert k["mean_JS"] <= 0.25, f"★★ JS {k['mean_JS']} > 0.25 —— v2 不该启用, 应回滚"
    assert "2026-08-09" in k["outlier_rule"], "★ 离群规则的冻结日期不见了 —— 判据被动过"


def test_the_cost_travels_with_the_conclusion():
    """★★★ 「越线概率 7.3% → 35.5%」必须留在结论旁 —— 否则「v2 通过」会被读成稳。"""
    # ★ 查**结构化字段本身**, 不是全文搜 —— 全文搜会因为数字在别处也出现而失去灵敏度
    #   (反向验证第一版就是这么失效的: 抹掉字段后散文里还留着同样的数字)
    blk = _res()["★★★但代价必须单独说"]
    over = json.dumps(blk["★★越 0.25 线的自助概率"], ensure_ascii=False)
    assert "7.3%" in over and "35.5%" in over, f"★★ 越线概率字段被改了: {over}"
    d = json.dumps(_res(), ensure_ascii=False)
    for must in ("0.0078", "0.16 个"):
        assert must in d, f"★★ 代价数字「{must}」不见了"
    assert "PASS 不是二值事实" in d, "★ 这句定性不许删"
    man = json.loads(MAN.read_text(encoding="utf-8"))
    # ★★★ 2026-09-13 修**位置依赖**: 原来写的是 refactor_log[-1], 假定「最后一条就是我关心的那次换代」。
    #   一追加新条目它就断(2026-09-13 登记 k=5 继承边时当场断了), 而断的原因与它要守的东西无关。
    #   ⇒ 按**身份**定位, 不按位置。这不是放宽: 它要守的「那次换代的代价必须随行」一字未动。
    gp = [e for e in man["refactor_log"] if e.get("event") == "GATE_PROTOCOL_CHANGE"]
    assert len(gp) == 1, "★ GATE_PROTOCOL_CHANGE 条目应当恰好 1 条, 实为 %d" % len(gp)
    assert "35.5%" in json.dumps(gp[0], ensure_ascii=False), \
        "★★★ refactor_log 里也必须带代价 —— 那是别人查换代时唯一会读的地方"
    # ★★ 顺手加强(不只是修坏): **每一条** refactor_log 都要带自己的代价, 不止这一条。
    #    「改了什么」不带「代价是什么」, 下一个人只会读到好消息。
    COST_MARKS = ("代价", "★evidence_is_required_because", "可比不可合", "不足以")
    naked = [e.get("date", "?") + "/" + e.get("event", e.get("route", "?"))[:40]
             for e in man["refactor_log"]
             if not any(m in json.dumps(e, ensure_ascii=False) for m in COST_MARKS)]
    assert not naked, ("★★★ 这些 refactor_log 条目只写了改动、没写代价:\n  "
                       + "\n  ".join(naked) + "\n  ⇒ 下一个人只会读到好消息。")


def test_both_directions_of_the_frozen_rule_are_honoured():
    """★★ 判据冻结在先: 越线不许找补, **没越线也不许事后改判成 FAIL**。"""
    d = json.dumps(_res(), ensure_ascii=False)
    assert "在噪声范围内" in d and "不许" in d, "★ 「越线不许找补」的自我约束不见了"
    assert "没越线就是没越线" in d, "★★ 反方向的约束同样要写 —— 否则我可以事后把 PASS 说成 FAIL"
    assert _res()["overall_pass"] is True


def test_the_qualification_wording_cannot_be_inflated():
    """★★ 五员全 5/5 但**全部 UNRESOLVED**。「全部合格」是**错的说法**。"""
    r = _res()["★★资格考(必须精确说)"]
    assert "全部 UNRESOLVED" in r["★三态判决"]
    assert "不是" in r["status"] and "全部合格" in r["status"]
    assert r["qualified_only"].startswith("**空集**")
    if _have():
        q = _live()["annotator_qualification"]
        st = {m: v["state"] for m, v in (q.get("★states") or {}).items()}
        assert st and all(v == "UNRESOLVED" for v in st.values()), \
            f"★ 三态判决变了: {st} —— 请更新结论措辞"
        assert q.get("qualified_only") == [], "★ qualified_only 不再是空集, 请更新措辞"


def test_v2_is_enabled_not_merely_registered():
    """★ 第⑤条完成后才谈启用 —— manifest 必须反映这一步已走完。"""
    man = json.loads(MAN.read_text(encoding="utf-8"))
    # ★ 同上, 按身份定位不按位置(本文件里第二处同型位置依赖, 一并修)
    gp = [x for x in man["refactor_log"] if x.get("event") == "GATE_PROTOCOL_CHANGE"]
    assert len(gp) == 1, "★ GATE_PROTOCOL_CHANGE 条目应当恰好 1 条, 实为 %d" % len(gp)
    e = gp[0]
    assert "★★★尚未完成的一条" not in e, "★ 「尚未完成」的标记该在第⑤条跑完后移除"
    assert "★★★第⑤条已完成_启用" in e, "★ 缺启用记录"
    assert "**v2 已启用**" in man["gate_protocol_expected"]["★status"]
    assert man["gate_protocol_expected"]["version"] == 2
    assert man["instrument_generation"] == 6, "★★ 生产不该换代 —— 换了就是记了假账"


def test_the_two_mandatory_sentences_survive():
    """★★ 「可比不可合」与「不改变生产分类器」两句缺一不可。"""
    d = json.dumps(_res(), ensure_ascii=False)
    assert "可比不可合" in d and "不改变生产分类器" in d
    assert "d4cce4c745f3f991" in d, "★ 生产哈希未变的证据要写出来, 不能只是断言"
    assert "1/8" in d and "NO_DEFECT" in d, "★ 「生产本来就没这个缺陷」的实测要一起带"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_res"]
    import copy
    bad = copy.deepcopy(_res())
    bad["★★★但代价必须单独说"]["★★越 0.25 线的自助概率"] = {"v1": "低", "v2": "低"}
    g["_res"] = lambda: bad
    try:
        test_the_cost_travels_with_the_conclusion()
        raise SystemExit("★ 反向验证失败: 抹掉代价数字后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    bad2 = copy.deepcopy(_res())
    bad2["★★资格考(必须精确说)"]["★三态判决"] = "五员全部合格"
    g["_res"] = lambda: bad2
    try:
        test_the_qualification_wording_cannot_be_inflated()
        raise SystemExit("★ 反向验证失败: 把 UNRESOLVED 说成合格后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_res"] = saved

    saved_h = g["_have"]
    g["_have"] = lambda: False
    try:
        test_gk1_passed_on_the_unchanged_criteria()
    finally:
        g["_have"] = saved_h
    return n + 1


if __name__ == "__main__":
    test_gk1_passed_on_the_unchanged_criteria()
    test_the_cost_travels_with_the_conclusion()
    test_both_directions_of_the_frozen_rule_are_honoured()
    test_the_qualification_wording_cannot_be_inflated()
    test_v2_is_enabled_not_merely_registered()
    test_the_two_mandatory_sentences_survive()
    n = _reverse_checks()
    print(f"test_cce_gate_v2_acceptance: OK ("
          f"G-K1 判据**一字未改**且两项达标(top2 0.8812 · JS 0.2422) ⇒ **v2 已启用** | "
          f"★★★代价随结论同行: 越 0.25 线的自助概率 **7.3% → 35.5%**, 余量仅 **0.16 个 SD** | "
          f"★★判据冻结的**两个方向**都认(越线不找补 / 没越线也不事后改判) | "
          f"★资格考措辞不许注水(五员全 5/5 但**全部 UNRESOLVED**, qualified_only 空集) | "
          f"「可比不可合」+「不改变生产分类器」两句在 | {n} 条反向验证/降级实跑)")
