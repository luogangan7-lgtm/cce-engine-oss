"""★★★ 排除标注者的通道**不止一条** —— 我今天修了资格考, 漏了离群规则。零 API。

## 发现经过
2026-09-07 我把资格考改成 v2 三态, 核心是「**只有 DISQUALIFIED 才排除, UNRESOLVED 留在 primary**」。
同日 Run C(确证验收)跑完, 发现 run_gates 报的指标是 **4 人**的, 而 v2 资格考给出的 primary 是 **5 人**。

★ 原因: `accuracy/run_gates.py` 里还有**第二条独立的排除通道** —— **离群规则**
(「与其余成员平均 JS > 面板中位数 + 2SD」, 2026-08-09 冻结)。它在 Run C 上**第一次真的触发**,
把 `MiniMax-Text-01` 剔了(平均 JS 0.2645 vs 其余 0.1805~0.1961)。

★★ 而此前它两次**差不到千分之一没触发**: 2026-08-09 差 0.0010 · 2026-09-07 早 差 0.0006。
   ⇒ 它一直贴在触发线上, 我早上分析过它, 却没把它和 v2 联系起来。

## ★★ 本闸不改规则
离群规则 2026-08-09 冻结, 而这个冲突是**在看到 Run C 结果之后**才发现的 ——
此刻改它就是用结果选规则。⇒ **只钉住「有两条通道」这个事实**, 以及两个面板的数各是多少,
让下一个人不能把 4 人的数当成 v2 primary 的数引用。

## ★ 为什么这条值得单独立闸
「修了一条 fail-open, 另一条还在」在本仓已经是**第四次**同族:
① `passed or MODELS`(资格考回退全员) → 修
② v2 自己造的 `of==0 ⇒ UNRESOLVED ⇒ 默认通过` → 修
③ 消融的 code_refs 被登记表骗 → 修
④ **本条: 离群规则绕过 v2** → **未改, 已钉**
"""
import ast
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
SRC = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")
RC = ROOT / "tests/data/run_c_confirmatory_result.json"
# ★ Run C 的产物在**识别层保险库**(外部语料含真实 reddit handle), 不在公开仓。
#   缺席时**只跑**能从仓内数据验的那几条(两面板的数已去识别地存在
#   tests/data/run_c_confirmatory_result.json 里), 并在末行明写「无本机素材, 未比对离群剔除名单」。
#   ★ 静默跳过不行: 那会让「本机绿 / CI 也绿」与「本机绿 / CI 其实没验」不可区分。
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/run_c_confirm/gates_result.json")
HAVE_VAULT = os.path.exists(VAULT)
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_there_really_are_two_exclusion_channels():
    """★★ 源码层面确认: admit_annotators **之外**还有一处会缩小面板。"""
    assert "outliers_excluded" in SRC, "★ 离群规则不见了 —— 若真删了, 请更新本闸与 Run C 的记录"
    assert "outlier_rule" in SRC
    # ★ 两条通道都会改变参与指标计算的标注者集合
    import run_gates as RG
    assert callable(RG.admit_annotators) and callable(RG.qualification_state)
    tree = ast.parse(SRC)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.unparse(fn)
    assert "admit_annotators" in body, "★ 通道一(资格考)不在 main 里了"
    assert "outlier" in body.lower() or "lo[" in body, "★ 通道二(离群)不在 main 里了"


def test_the_conflict_is_recorded_and_not_silently_fixed():
    """★★★ 冲突必须留档, 且必须写明**没有当场改规则**。"""
    d = _j(RC)["★★★which_panel_is_primary"]
    t = json.dumps(d, ensure_ascii=False)
    assert "第二条独立的排除通道" in t, "★ 「有两条通道」这句不见了"
    assert "已记, 未改" in t, "★★ 「未改」的声明不见了 —— 少了它, 下一个人会以为已经修好了"
    assert "用结果选规则" in t, "★ 「此刻改就是用结果选规则」这条理由不见了"


def test_both_panels_numbers_are_kept_and_labelled():
    """★★ 两个面板的数都要在, 且必须写明**引用哪一个**。"""
    d = _j(RC)["★★★which_panel_is_primary"]
    a, b = d["全5人_v2_primary"], d["4人_离群剔除后"]
    assert a["top2"] != b["top2"] and a["JS"] != b["JS"], "★ 两个面板的数一样了?"
    assert a["JS"] > b["JS"], "★ 剔除离群者后 JS 应更好(更小) —— 若反了, 需重新解释"
    assert "用全 5 人那套" in d["★which_to_quote"], "★ 「引用哪一个」的指示不见了"
    assert "sensitivity analysis" in d["★which_to_quote"]


def test_the_outlier_rule_finally_fired_after_two_near_misses():
    """★ 它此前两次差不到千分之一 —— 这个背景必须在, 否则「第一次触发」失去分量。"""
    t = json.dumps(_j(RC), ensure_ascii=False)
    assert "0.0010" in t and "0.0006" in t, "★ 两次「差不到千分之一」的数不见了"
    assert "第一次真的触发" in t
    if not HAVE_VAULT:
        # ★ 降级路径也要有断言, 否则恒绿
        assert not os.path.exists(VAULT.parent / "raw_annotations.json"), \
            "★ 原始标注在但 gates_result 不在 —— 半份数据比没有更危险"
    else:
        g = _j(VAULT)["G_K1v2_分布一致性"]
        assert g.get("outliers_excluded") == ["MiniMax-Text-01"], (
            f"★ Run C 的离群剔除名单变了: {g.get('outliers_excluded')}")
        js = g["annotator_mean_JS"]
        assert max(js, key=js.get) == "MiniMax-Text-01", "★ 最离群的不再是 Text-01"


def test_this_is_the_fourth_of_the_same_family():
    """★ 同族计数必须在 —— 它是「再找一遍还有没有第三条」的提醒。"""
    doc = (ROOT / "tests/test_cce_second_exclusion_channel.py").read_text(encoding="utf-8")
    assert "第四次" in doc and "passed or MODELS" in doc and "of==0" in doc, \
        "★ 四次同族的清单不完整 —— 它是本闸存在的理由"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(RC)
    bad = copy.deepcopy(d)
    bad["★★★which_panel_is_primary"]["★★the_conflict_i_created"] = "已修复。"
    g["_j"] = lambda p: bad if p == RC else saved(p)
    try:
        test_the_conflict_is_recorded_and_not_silently_fixed()
        raise SystemExit("★ 反向验证失败: 把「未改」改成「已修复」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★★which_panel_is_primary"]["4人_离群剔除后"]["JS"] = bad2["★★★which_panel_is_primary"]["全5人_v2_primary"]["JS"]
    g["_j"] = lambda p: bad2 if p == RC else saved(p)
    try:
        test_both_panels_numbers_are_kept_and_labelled()
        raise SystemExit("★ 反向验证失败: 两面板数抹平后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    saved_src = g["SRC"]
    g["SRC"] = saved_src.replace("outliers_excluded", "xxx")
    try:
        test_there_really_are_two_exclusion_channels()
        raise SystemExit("★ 反向验证失败: 抹掉离群规则后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["SRC"] = saved_src
    return n


if __name__ == "__main__":
    test_there_really_are_two_exclusion_channels()
    test_the_conflict_is_recorded_and_not_silently_fixed()
    test_both_panels_numbers_are_kept_and_labelled()
    test_the_outlier_rule_finally_fired_after_two_near_misses()
    test_this_is_the_fourth_of_the_same_family()
    n = _reverse_checks()
    d = _j(RC)["★★★which_panel_is_primary"]
    print(f"test_cce_second_exclusion_channel: OK ("
          f"★★★源码确认**两条**排除通道(资格考 + 离群规则), 我今天只修了第一条 | "
          f"Run C 离群规则**第一次真的触发**(剔 Text-01; 此前两次差 0.0010/0.0006) | "
          f"两面板都留档: v2 primary 5 人 JS={d['全5人_v2_primary']['JS']} vs "
          f"离群剔除后 4 人 JS={d['4人_离群剔除后']['JS']}, 且写明**引用前者** | "
          f"★**未改规则**(冻结在前, 冲突是看到结果后才发现的 ⇒ 此刻改就是用结果选规则) | "
          f"同族第 **4** 次 | "
          f"{'离群名单已比对' if HAVE_VAULT else '★**无本机素材, 未比对离群剔除名单**(只跑了仓内可验的部分)'} | "
          f"{n} 条反向验证判红)")
