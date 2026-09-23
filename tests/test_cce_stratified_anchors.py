"""分层候选锚例 —— 交付物的完整性与**诚实性**。零 API。

## 交付什么
7/9 个结各 3 条候选(共 21 条), 真值 = **glm-4.5-flash 单模型**跨家族标注, **待人复核**。

## ★★★ 本闸真正防的三件事
① **选择规则不许改成「按模型置信度取」** —— 那会挑「模型最有把握的」= 最容易的样本,
   而资格考最需要的恰恰是**边界样本**。现在用 `sha256(id+'strat')` 排序, 与置信度无关。
② **真值标签不许升级** —— 它是 `single_cross_family_model`, 不是 consensus(round2 证明
   glm-4.7-flash 对薄类结构性失败, 双模型共识**执行不下去**), 更不是 human-adjudicated。
③ **reward/inertia 的缺口不许被说成「再抽点就有了」** —— 它是**结构性的**:
   两者按单元亲和性都在**评论侧**(reward 15.7×), 而评论语料只有 86 条且**全部用完**
   (81 进验收集 + 5 已是锚例) ⇒ 从中取锚例会**把考题放进测试集**。

## 两种失败的区分(本轮的干净负结果)
· glm-4.7-flash `finish=length`: 加预算 6000→16000 **仍失败**, Fisher **p=0.00077** ⇒ 系统性丢薄类
· glm-4.5-flash `finish=err`: 加 timeout 420→900s **40/40 全通**, Fisher **p=0.71247** ⇒ **未见偏倚**
★ 「按成功过滤必须检验偏倚」这条闸, 这次给出的是**「没有」** —— 那正是它该给的两种答案之一。
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SA = ROOT / "tests/data/stratified_anchor_candidates.json"
UA = ROOT / "tests/data/unit_affinity_table.json"
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_selection_is_hash_based_not_confidence_based():
    """★★★ 按置信度取 = 挑最容易的 = 资格考最不该要的。"""
    d = _j(SA)
    r = d["★selection_rule"]
    assert "sha256" in r and "strat" in r, "★ 选择规则不再是哈希排序了"
    assert "不按模型置信度取" in r, "★★ 那条**为什么不按置信度**的理由不见了"
    assert "边界样本" in r
    # ★ 现算: 落盘的 ids 必须真是哈希排序的前 3
    for k, items in d["candidates"].items():
        ids = [x["id"] for x in items]
        assert ids == sorted(ids, key=lambda i: hashlib.sha256((i + "strat").encode()).hexdigest()), \
            f"★ {k} 的候选不是按 sha256(id+'strat') 排序的 —— 可能被换成了别的选法"


def test_truth_label_is_not_upgraded():
    """★★ 真值只能是单模型, 不许写成 consensus 或 human。"""
    d = _j(SA)
    assert "single_cross_family_model" in d["★truth_source"]
    t = json.dumps(d, ensure_ascii=False)
    assert "不是** human-adjudicated" in t or "不是 human-adjudicated" in t
    assert "待人复核" in t
    assert "consensus" not in d["★truth_source"], (
        "★★ 真值被写成 consensus 了 —— 而 round2 已证明 glm-4.7-flash 对薄类结构性失败, "
        "双模型共识执行不下去")
    assert d["★i_will_not"].count("不") >= 1 and "anchors.json" in d["★i_will_not"]


def test_the_gap_is_structural_not_a_sampling_shortfall():
    """★★★ reward/inertia 取不到是**结构性**的, 不是「再抽点就有」。"""
    d = _j(SA)["★★the_gap_and_why_it_cannot_be_closed_here"]
    assert set(d["缺口"]) == {"reward", "inertia"}, f"★ 缺口变了: {d['缺口']}"
    why = d["★★★why"]
    assert "评论侧" in why and "结构上取不到" in why
    assert "86" in why and "81" in why, "★ 「评论语料 86 条, 81 条已进验收集」这个具体数不见了"
    assert "把考题放进测试集" in why, "★★ 那条**为什么不能从评论取**的核心理由不见了"
    # ★ 与单元亲和性表交叉核对
    ua = _j(UA)["table"]
    for k in d["缺口"]:
        assert ua[k]["亲和"] == "评论", f"★ {k} 的亲和性变了({ua[k]['亲和']}) —— 那这条推理要重做"
    assert len(d["★options_for_owner"]) >= 3, "★ 给 owner 的选项少于 3 个"
    assert any("未复测" in o for o in d["★options_for_owner"]), \
        "★ 「ScraperAPI 的可用性是旧记录、未复测」这个诚实标注不见了"


def test_seven_of_nine_are_actually_complete():
    d = _j(SA)["candidates"]
    full = [k for k, v in d.items() if len(v) >= 3]
    assert len(full) == 7, f"★ 满 3 条的结数变了: {len(full)} ({sorted(full)})"
    assert all(len(v) <= 3 for v in d.values()), "★ 有结取了超过 3 条"
    ids = [x["id"] for v in d.values() for x in v]
    assert len(ids) == len(set(ids)), "★ 候选 id 有重复"


def test_the_two_failure_modes_are_distinguished():
    """★★ 本轮的干净负结果: 不是所有「按成功过滤」都有偏倚。"""
    doc = (ROOT / "tests/test_cce_stratified_anchors.py").read_text(encoding="utf-8")
    assert "0.00077" in doc and "0.71247" in doc, "★ 两个 Fisher p 值不见了"
    assert "未见偏倚" in doc and "那正是它该给的两种答案之一" in doc, \
        "★★ 「闸给出『没有』也是正确输出」这条不见了 —— 少了它, 下次会以为闸没抓到就是闸没用"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(SA)
    bad = copy.deepcopy(d)
    bad["★truth_source"] = "cross_family_model_consensus"
    g["_j"] = lambda p: bad if p == SA else saved(p)
    try:
        test_truth_label_is_not_upgraded()
        raise SystemExit("★ 反向验证失败: 真值升级成 consensus 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["candidates"]["display"] = list(reversed(bad2["candidates"]["display"]))
    g["_j"] = lambda p: bad2 if p == SA else saved(p)
    try:
        test_selection_is_hash_based_not_confidence_based()
        raise SystemExit("★ 反向验证失败: 打乱哈希序后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad3 = copy.deepcopy(d)
    bad3["★★the_gap_and_why_it_cannot_be_closed_here"]["★★★why"] = "再多抽一些就有了。"
    g["_j"] = lambda p: bad3 if p == SA else saved(p)
    try:
        test_the_gap_is_structural_not_a_sampling_shortfall()
        raise SystemExit("★ 反向验证失败: 把结构性缺口说成抽样不足后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_selection_is_hash_based_not_confidence_based()
    test_truth_label_is_not_upgraded()
    test_the_gap_is_structural_not_a_sampling_shortfall()
    test_seven_of_nine_are_actually_complete()
    test_the_two_failure_modes_are_distinguished()
    n = _reverse_checks()
    d = _j(SA)
    print(f"test_cce_stratified_anchors: OK ("
          f"**7/9 个结**各 3 条候选(21 条), 真值 single_cross_family_model **待人复核** | "
          f"★★★选择用 sha256 排序**不按置信度**(那会挑最容易的样本), 现算校验 | "
          f"真值标签不许升级成 consensus/human | "
          f"★★reward/inertia 的缺口是**结构性**的(都在评论侧, 而评论语料 86 条全用完 "
          f"⇒ 取了就是把考题放进测试集), 已给 owner 三个选项 | "
          f"★两种失败已区分: length(p=0.00077 有偏) vs err(p=0.71247 **无偏**) | "
          f"{n} 条反向验证判红)")
