"""★★★ 「五员共识」这个说法是错的 —— 它是**软聚合主类**。零 API, 现算。

## 错在哪
· **软聚合(soft voting)**: 先汇总九维权重, 再取 argmax
· **多数票(hard voting)**: 先各自取 argmax, 再投票
二者是**不同的运算**, 不必相同。我从头到尾说「五员共识 argmax」, 那是**前者**。
⇒ GPT 原话: 「可以叫「**软聚合主类为 suspend**」, **不能叫「五员共识为 suspend」**。」

## 实测规模(81 条)
· 软聚合 ≠ 多数票: **3/81 = 3.7%**
· **软聚合主类得票 <= 半数: 8/81 = 9.9%** ← 更相关的数
· 逐类冲突率: display 0/32 · reward 0/12 · itch 0/8 · audit 0/5 · pain_seek 2/19 · **suspend 1/5 = 20%**

★★ 冲突面小 ⇒ 「共识」这个说法**误导但没有大幅扭曲结论**。
★★★ 但它**恰好发生在 suspend 那 5 条里的一条**(p1au1ez: 软聚合判 suspend 得 **2/5** 票,
   而 pain_seek 得 **3/5**) —— 也就是我用来论证「suspend 崩了」的证据里,
   **有一条的「共识」本身就可疑**。

## 从今往后的报告规则(作用于**全部**类别, 不只 suspend)
每条主类断言必须同时报 `pooled_top1` · `majority_top1` · `top1_votes` · `aggregation_conflict`;
**二者冲突时主类断言记 UNRESOLVED, 不在两者之间临时挑一个。**
★ 临时为了解决 suspend 的分歧而改用多数票, 就是**用结果选规则**。
"""
import collections
import json
import pathlib
import os

ROOT = pathlib.Path(__file__).resolve().parent.parent
A = ROOT / "tests/data/aggregation_semantics_correction.json"
RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/run_a_repeat/raw_annotations.json")
HAVE_RAW = os.path.exists(RAW)   # ★ 保险库侧, 公开仓 CI 上可能不在
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_the_wording_error_is_recorded():
    d = _j(A)["★★★the_wording_error_i_kept_making"]
    t = d["★★what_it_actually_is"]
    assert "软聚合主类" in t and "不是" in t and "多数票" in t
    assert "不同的运算" in t, "★ 「soft/hard 是不同运算」这条不见了"
    assert "不能叫「五员共识" in t, "★★ GPT 那句原话不见了"


def test_the_scale_is_measured_not_asserted():
    """★★ 现算冲突规模 —— 不信任落盘。"""
    if not HAVE_RAW:
        d = _j(A)["★★★the_wording_error_i_kept_making"]["★measured_scale_of_the_problem"]
        assert "3/81" in d["软聚合≠多数票"], "★ 无本机素材时, 落盘的数至少要在"
        return                      # ★ 无本机素材, 未从原始标注重算
    raw = _j(RAW)
    d, ms = raw["dists"], raw["annotators"]
    ids = sorted({i for m in ms for i in d[m] if d[m][i]})
    conf = minority = 0
    for i in ids:
        per = {m: d[m][i] for m in ms if d[m].get(i)}
        agg = {k: sum(v.get(k, 0) for v in per.values()) / len(per) for k in set().union(*per.values())}
        soft = max(agg, key=agg.get)
        votes = collections.Counter(max(v, key=v.get) for v in per.values())
        hard = votes.most_common(1)[0][0]
        conf += soft != hard
        minority += votes.get(soft, 0) * 2 <= len(per)
    rec = _j(A)["★★★the_wording_error_i_kept_making"]["★measured_scale_of_the_problem"]
    assert f"{conf}/{len(ids)}" in rec["软聚合≠多数票"], \
        f"★ 现算冲突 {conf}/{len(ids)} 与落盘不符"
    assert f"{minority}/{len(ids)}" in rec["★软聚合主类得票<=半数"], \
        f"★ 现算「得票不过半」{minority}/{len(ids)} 与落盘不符"


def test_the_conflict_hit_the_suspend_evidence():
    """★★★ 最要紧的一条: 冲突恰好发生在 suspend 的证据里。"""
    d = _j(A)["★★★the_wording_error_i_kept_making"]
    assert "p1au1ez" in json.dumps(d, ensure_ascii=False), "★ 那条冲突样本的 id 不见了"
    t = d["★★so_the_error_is_precision_not_distortion"]
    assert "有一条的「共识」本身就是可疑的" in t, \
        "★★★ 「我的 suspend 证据里有一条可疑」这句不见了 —— 少了它，这个更正就只是措辞问题"
    conflicts = {c["id"] for c in d["★the_conflicts"]}
    assert "p1au1ez" in conflicts


def test_the_new_reporting_rule_applies_to_all_classes():
    """★★ 不许只对 suspend 改规则 —— 那是用结果选规则。"""
    r = _j(A)["★★the_required_reporting_from_now_on"]
    for f in ("pooled_top1", "majority_top1", "top1_votes", "aggregation_conflict"):
        assert f in r["★rule"], f"★ 必报字段 {f} 不见了"
    assert "记 UNRESOLVED" in r["★rule"] and "不在两者之间临时挑一个" in r["★rule"]
    assert "不只 suspend" in r["★★applies_to_all_classes"], \
        "★★★ 「作用于全部类别」这条不见了 —— 少了它就成了为 suspend 定制规则"


def test_the_calibration_caveat_is_stated():
    """★★ 九类权重不是概率 —— 权重和为 1 不能证明校准。"""
    t = _j(A)["★★the_required_reporting_from_now_on"]["★★a_deeper_question_it_raises"]
    assert "合成读数" in t and "不是" in t and "概率" in t
    assert "权重和为 1 不能证明校准" in t


def test_my_suspend_conclusion_was_corrected_on_three_counts():
    """★★★ GPT 纠正我三处, 都要在。"""
    c = _j(A)["★★★what_gpt_corrected_about_my_suspend_conclusion"]
    assert "intra-annotator" in c["①_inter_vs_intra"] and "我根本没测" in c["①_inter_vs_intra"], \
        "★★★ 「inter ≠ intra, 而我没测 intra」这条不见了"
    assert "召回率" in c["②_not_a_recall"] and "不能判定哪一方正确" in c["②_not_a_recall"]
    t3 = c["③_the_downstream_case_proves_less_than_i_said"]
    assert "同时改了三件事" in t3 and "同一仪器" in t3, "★ 那个混淆不见了"
    assert "Kane" in t3, "★ 「解释成立 ≠ 用它作决策成立」的出处不见了"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(A)
    bad = copy.deepcopy(d)
    bad["★★the_required_reporting_from_now_on"]["★★applies_to_all_classes"] = "只对 suspend 生效。"
    g["_j"] = lambda p: bad if p == A else saved(p)
    try:
        test_the_new_reporting_rule_applies_to_all_classes()
        raise SystemExit("★ 反向验证失败: 改成只对 suspend 生效后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★★the_wording_error_i_kept_making"]["★★so_the_error_is_precision_not_distortion"] = "只是措辞问题。"
    g["_j"] = lambda p: bad2 if p == A else saved(p)
    try:
        test_the_conflict_hit_the_suspend_evidence()
        raise SystemExit("★ 反向验证失败: 抹掉「证据里有一条可疑」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_the_wording_error_is_recorded()
    test_the_scale_is_measured_not_asserted()
    test_the_conflict_hit_the_suspend_evidence()
    test_the_new_reporting_rule_applies_to_all_classes()
    test_the_calibration_caveat_is_stated()
    test_my_suspend_conclusion_was_corrected_on_three_counts()
    n = _reverse_checks()
    s = _j(A)["★★★the_wording_error_i_kept_making"]["★measured_scale_of_the_problem"]
    print(f"test_cce_aggregation_semantics: OK ("
          f"★★★「五员共识」是错说法, 它是**软聚合主类**(soft≠hard voting) | "
          f"实测规模 软≠硬 {s['软聚合≠多数票']} · **得票不过半 {s['★软聚合主类得票<=半数']}** | "
          f"★★★冲突**恰好命中 suspend 的证据**(p1au1ez: soft 2/5 票 vs hard pain_seek 3/5) | "
          f"新报告规则**作用于全部类别**不只 suspend | "
          f"★权重不是概率(和为 1 不证明校准) | "
          f"★★GPT 纠正我三处: inter≠intra(**我没测 intra**) · 0/5 不是召回率 · 改稿同时改了三件事 | "
          f"{'原始标注已重算' if HAVE_RAW else '★**无本机素材, 未重算**'} | {n} 条反向验证判红)")
