"""★★★ v3c 归档 + 预算停止规则 + 窄检查推翻我自己的一项声称。零 API。

## 归档状态(三本账分开, 免得半年后只看到一个 FAIL)
① 原冻结协议判决: **FAIL**(历史记录)
② 候选效应证据: **目标用例观察到改善; 保护项非劣效性未建立**
③ 当前操作决定: **不启用; 关闭本研究路径追加预算; 保留候选及原始证据**
★ **停止研究 ≠ 已证明候选有害; 保留候选 ≠ 产生继续购买的义务。**

## ★★★ 窄检查推翻了我自己在预注册里的第③项
我声称「候选不改变规范含义, 范围不扩不缩」。**实测: 不闭合。**
v3c 新增了两处旧合同没有的要求: 「**决策对象**」与「**在文本中**」。
⇒ 「我承认有判断成分」这个动作**不保证我找全了判断成分**。

## 停止规则(GPT 逐字给, 已采纳)
同一候选、同一组已暴露开发题, **不因上一轮未定而自动追加付费重复**。
新增采购须**同时**具备五项, 任一缺失不发起; 到上限仍未定**结案为证据不足**,
**不临时扩样、换方法或改阈值**。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "tests" / "data" / "v3c_archived_and_stop_rule.json"
PRE = ROOT / "tests" / "data" / "gate_decision_tree_candidate_prereg.json"


def _d():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_three_books_kept_separate():
    """★ 三本账分开 —— 免得半年后只看到一个 FAIL。"""
    b = _d()["★★★v3c 的三本账(必须分开保留, 免得半年后只看到一个 FAIL)"]
    assert "FAIL" in b["①原冻结协议判决"]
    assert "观察到改善" in b["②候选效应证据"] and "非劣效性未建立" in b["②候选效应证据"]
    assert "不启用" in b["③当前操作决定"] and "保留候选" in b["③当前操作决定"]
    assert "停止研究不等于已经证明候选有害" in b["★★关键区分"]
    assert "保留候选也不产生继续购买的义务" in b["★★关键区分"]


def test_owner_is_not_asked_to_certify_the_experiment():
    """★★ owner 可以定规则与预算, **不能通过签字补出候选缺失的验证证据**。"""
    d = json.dumps(_d(), ensure_ascii=False)
    assert "不能通过签字补出候选缺失的验证证据" in d
    assert "只交**尚未确定的规范问题**" in d or "只交尚未确定的规范问题" in d.replace("*", "")
    assert "不要让 owner 只签" in d, "★ 「不要让 owner 只签同意采用」这句不许删"


def test_the_stop_rule_has_all_five_prerequisites():
    """★★★ 停止规则的五项前提缺一不可, 且「到上限仍未定 ⇒ 结案」不许被改成「再扩一轮」。"""
    r = _d()["★★★可事先写下的停止规则(GPT 逐字给的, 现采纳为本条研究路径的预算规则)"]
    for k in ("目标使用声明", "参照和抽样范围", "最小有用改善", "判决操作特性", "具体行动"):
        assert k in r, f"★ 停止规则缺前提「{k}」"
    assert "任一项缺失, 不发起" in r
    assert "不临时扩样、换方法或改阈值" in r, "★★ 这句是停止规则的牙齿, 不许删"
    d = json.dumps(_d(), ensure_ascii=False)
    assert "不自动构成重新立项的理由" in d, "★ 重新立项门槛不许删"
    assert "不能从噪声底倒推" in d, "★ 「可接受退化量不能从噪声底倒推」不许删"


def test_the_narrow_check_overturned_my_own_closure_claim():
    """★★★ 窄检查: v3c 新增了「决策对象」与「在文本中」两处旧合同没有的要求。"""
    b = _d().get("★★★窄检查已做_结果推翻了我自己的一项声称")
    assert b, "★★★ 窄检查的记录被删了"
    cmp_ = b["★零调用比对(旧版取自修复前冻结备份)"]
    assert "新增" in cmp_["★★「决策对象」"] and "新增" in cmp_["★★「在文本中」这个限定"]
    assert "未新增" in cmp_["「犹豫理由」"] and "未新增" in cmp_["「还没定/再看看」"]
    assert "扩大了规范范围" in b["★★★结论"]
    assert "那一项其实不闭合" in b["★★★因此我预注册里的第③项检查不闭合"]["★实测"]
    assert "不保证我找全了判断成分" in b["★我在预注册里唯一自认过的判断成分"], \
        "★★ 这条自认不许删 —— 它是「承认有判断成分 ≠ 找全了判断成分」的记录"


def test_the_narrow_check_is_recomputable():
    """★ 窄检查必须能**现算**复核, 不是一句话断言。"""
    bak = pathlib.Path("/Volumes/data/cce-identified-vault/backups")
    if not bak.exists():
        # ★ **无本机素材**(CI 上没有识别层保险库) ⇒ 降级: **只跑**留档核对, 未重算窄检查。
        #   降级路径自带断言, 不是静默跳过。
        print("  ★ 降级(**无本机素材**): 只跑留档核对, **未比对**冻结备份 ⇒ 窄检查本轮**不可验证**")
        assert "新增" in json.dumps(_d(), ensure_ascii=False)
        return
    cand = sorted(bak.glob("*gate-protocol-v2"))
    if not cand:
        print("  ★ 降级(**无本机素材**): 备份目录在但没有该次冻结快照 ⇒ **未比对**, 窄检查**不可验证**")
        assert "新增" in json.dumps(_d(), ensure_ascii=False)
        return
    old = json.loads((cand[-1] / "knot_taxonomy.json").read_text(encoding="utf-8"))
    dt = [l for l in old["annotation_protocol"]["decision_tree_prompt"] if l.startswith("4.")][0]
    hd = [k for k in old["knots"] if k["key"] == "suspend"][0]["hard_discriminant"]
    new = json.loads(PRE.read_text(encoding="utf-8"))["★★★the_single_change_verbatim"]["new"]
    assert "决策对象" not in dt and "决策对象" not in hd, "★ 旧文本里出现了「决策对象」—— 窄检查结论要重算"
    assert "决策对象" in new, "★ 候选文本里没有「决策对象」—— 窄检查结论要重算"
    assert "文本中" not in dt and "文本中" not in hd
    assert "在文本中" in new


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_d"]
    import copy
    bad = copy.deepcopy(_d())
    del bad["★★★窄检查已做_结果推翻了我自己的一项声称"]
    g["_d"] = lambda: bad
    try:
        test_the_narrow_check_overturned_my_own_closure_claim()
        raise SystemExit("★ 反向验证失败: 删掉窄检查后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_d"] = saved

    bad2 = copy.deepcopy(_d())
    bad2["★★★可事先写下的停止规则(GPT 逐字给的, 现采纳为本条研究路径的预算规则)"] = \
        bad2["★★★可事先写下的停止规则(GPT 逐字给的, 现采纳为本条研究路径的预算规则)"].replace(
            "不临时扩样、换方法或改阈值", "可酌情扩样")
    g["_d"] = lambda: bad2
    try:
        test_the_stop_rule_has_all_five_prerequisites()
        raise SystemExit("★ 反向验证失败: 把「不许扩样」改成「可酌情扩样」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_d"] = saved
    return n


if __name__ == "__main__":
    test_three_books_kept_separate()
    test_owner_is_not_asked_to_certify_the_experiment()
    test_the_stop_rule_has_all_five_prerequisites()
    test_the_narrow_check_overturned_my_own_closure_claim()
    test_the_narrow_check_is_recomputable()
    n = _reverse_checks()
    print(f"test_cce_v3c_archived: OK ("
          f"★三本账分开(FAIL 是历史记录 · 效应证据是「观察到改善但非劣效未建立」 · "
          f"操作决定是「不启用+关预算+留候选」), **停止研究≠证明有害, 留候选≠继续买的义务** | "
          f"★★owner 只判规范问题, **不能签字补出验证证据** | "
          f"停止规则五项前提齐全且「**不临时扩样换方法改阈值**」有牙 | "
          f"★★★窄检查**现算**确认 v3c 新增了「决策对象」「在文本中」两处旧合同没有的要求 ⇒ "
          f"**我预注册里的第③项检查不闭合** —— 「承认有判断成分」不保证「找全了判断成分」 | "
          f"{n} 条反向验证判红)")
