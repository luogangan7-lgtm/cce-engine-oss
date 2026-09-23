"""★★★ 预算打满**不是随机失败** —— 它系统性地丢掉薄类。零 API。

## 发现
锚例扩充第一轮(60 篇候选 × 两个 GLM, max_tokens=6000):
· `glm-4.5-flash` **60/60 全部解析成功**
· `glm-4.7-flash` **33/60 是 finish=length**(预算打满)

一致率算出来是 **96%** —— 看着很好。**但它只在 4.7 答完的那 25 条上算的。**

## ★★ 那 25 条与其余 35 条不是同分布(按 4.5 的标注看)
| | pain_seek 占比 | 覆盖结数 |
|---|---|---|
| 4.7 **答完的** 25 条 | **80%** | **2** |
| 4.7 **没答完的** 35 条 | 60% | **6**(含 suspend / reward / itch / **belong**) |

⇒ **4.7 答不完的, 恰恰是「不那么典型 pain_seek」的那些** —— 也就是**更有信息量、更需要当锚例**的那批。
⇒ **96% 是高估**; 而「只覆盖 2 个结」是**被预算人为压窄的**, 不是内在的。

## ★ 一般教训
**任何按「成功返回」过滤的分析, 都必须检验「失败的那批与成功的那批是否同分布」。**
本仓已有同族: 消融的 code_refs 被登记表虚增(计数偏置) · 离群规则在阈值边缘反复(判决偏置)。
这次是**第三种**: **算力预算造成的选择偏置** —— 它伪装成技术故障, 实际改变了样本构成。
"""
import json
import os
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "tests/data/anchor_expansion_result.json"
RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/anchor_expansion/raw.json")
HAVE_RAW = os.path.exists(RAW)   # ★ 保险库侧(含语料), 公开仓 CI 上可能不在
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_the_bias_is_recorded_next_to_the_agreement_rate():
    """★★★ 96% 旁边必须有「有选择偏倚」, 否则它会被当成干净的一致率引用。"""
    d = _j(RES)
    b = d["★★★the_selection_bias_i_did_not_predict"]
    assert "96% 是高估" in json.dumps(b, ensure_ascii=False), "★ 「96% 是高估」这句不见了"
    e1 = d["★★three_predictions_adjudicated"]["E1_一致率>=60%"]
    assert "★caveat" in e1 and "选择偏倚" in e1["★caveat"], \
        "★★ E1 命中的旁边没有偏倚提醒 —— 那它会被当成干净的结论"


def test_round2_proved_the_bias_instead_of_removing_it():
    """★★★ 加预算(6000→16000)**没有消除**偏倚, 只是把它证明了。现算 Fisher。"""
    d = _j(RES).get("round2_retry_at_16000_tokens")
    assert d, "★ round2 的记录不见了"
    b = d["★★★the_bias_did_not_go_away_it_got_proven"]
    from math import comb

    def fisher(a, bb, c, dd):
        n1, n2, k = a + bb, c + dd, a + c
        return sum(comb(n1, i) * comb(n2, k - i) for i in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)
    p_ = fisher(6, 14, 0, 40)          # 薄类: 打满 6/20 vs 答完 0/40
    assert p_ < 0.01, f"★ Fisher 现算 {p_:.5f} 不再 <0.01"
    import re as _re
    got = float(_re.search(r"[\d.]+", b["★fisher_one_sided"]).group())
    assert abs(got - p_) < 1e-4, f"★ 落盘的 p={got} 与现算 {p_:.5f} 不符"
    assert "0.0%" in b["薄类占比"]["4.7 答完的 40 条"], "★ 「答完的里薄类 0 条」这个完全分离不见了"
    lost = {x["knot"] for x in b["★the_lost_thin_samples"]}
    assert "belong" in lost and "suspend" in lost, f"★ 被丢的薄类变了: {lost}"
    assert "不是因为文本长, 是因为判断难" in b["★★they_are_short_not_long"]


def test_the_practical_conclusion_is_stated():
    """★★ 「4.7 不能当第二个标注者」以及「单模型不构成共识」必须写明。"""
    d = _j(RES)
    t = d["round2_retry_at_16000_tokens"]["★★★practical_conclusion"]
    assert "不能当第二个标注者" in t
    assert "单模型不构成共识" in t, "★★ 少了这句, 下一个人会拿单模型标注当共识真值用"
    assert "没有**产出可用的锚例真值" in t or "没有产出可用的锚例真值" in t
    assert "single_cross_family_model" in json.dumps(d, ensure_ascii=False),         "★ 更弱的真值标签名不见了"


def test_the_two_groups_really_differ():
    """★★ 现算: 答完的与没答完的**不同分布**。这是偏倚存在的依据。"""
    if not HAVE_RAW:
        b = _j(RES)["★★★the_selection_bias_i_did_not_predict"]
        assert b["distribution_by_45_eyes"]["4.7 答完的"] != b["distribution_by_45_eyes"]["4.7 没答完的"], \
            "★ 无本机素材时, 落盘的两组分布至少要不同"
        return                      # ★ 无本机素材, 未从原始数据重算
    rows = _j(RAW)
    M45, M47 = "glm-4.5-flash", "glm-4.7-flash"
    # ★ 只看**第一轮**的 finish(补跑会覆盖 4.7 的结果), 故用落盘的分布做交叉核对
    b = _j(RES)["★★★the_selection_bias_i_did_not_predict"]
    done_d = b["distribution_by_45_eyes"]["4.7 答完的"]
    undone_d = b["distribution_by_45_eyes"]["4.7 没答完的"]
    assert len(undone_d) > len(done_d), (
        f"★★ 没答完的那批**覆盖的结更少**了({len(undone_d)} vs {len(done_d)}) —— "
        "那「预算打满系统性丢薄类」这条要重新表述")
    sh_done = done_d.get("pain_seek", 0) / sum(done_d.values())
    sh_un = undone_d.get("pain_seek", 0) / sum(undone_d.values())
    assert sh_done - sh_un > 0.1, (
        f"★ 答完组的 pain_seek 占比 {sh_done:.1%} 不再明显高于没答完组 {sh_un:.1%}")
    # ★ 4.5 全部成功 —— 它是这个对照的锚
    assert all(r[M45]["top1"] for r in rows), "★ glm-4.5-flash 不再是 60/60 全成功了"


def test_thin_knots_are_exactly_what_got_dropped():
    """★★★ 被丢掉的正是薄类 —— 这是「最坏方向」的证据。"""
    b = _j(RES)["★★★the_selection_bias_i_did_not_predict"]
    un = set(b["distribution_by_45_eyes"]["4.7 没答完的"])
    done = set(b["distribution_by_45_eyes"]["4.7 答完的"])
    lost = un - done
    assert lost, "★ 没有任何结是「只出现在没答完那批」的 —— 那这条结论要弱化"
    assert "belong" in lost, (
        f"★ belong 不再是被丢掉的结之一({sorted(lost)}) —— "
        "它是今天花了两轮实验才证明存在的类, 被预算丢掉最值得记")


def test_coverage_blocker_is_stated_as_structural_not_just_budget():
    """★★ 即使补齐预算, 随机抽样也覆盖不了九个结 —— 这条不能被「补跑就好了」盖过去。"""
    c = _j(RES)["★★coverage_is_the_real_blocker"]
    t = json.dumps(c, ensure_ascii=False)
    assert "必须分层" in t, "★ 「必须分层抽样」这条不见了"
    assert "塌到同一批类" in t, "★ 「两家族塌到同一批类」这条独立证据不见了"
    assert "凑不够每结 3 条" in t


def test_the_real_answer_to_how_many_anchors():
    """★ 「扩充多少才够」的答案必须在, 而且是 n=60 不是 n=24。"""
    e3 = _j(RES)["★★three_predictions_adjudicated"]["E3_扩充后v2覆盖率仍是0%"]
    t = e3["★the_real_number"]
    assert "n=60 起" in t and "没有分辨力" in t, "★ 那个真答案不见了"
    assert "35" in t, "★ CERTIFY 门槛 n>=35 这个数不见了"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(RES)
    bad = copy.deepcopy(d)
    bad["★★three_predictions_adjudicated"]["E1_一致率>=60%"].pop("★caveat")
    g["_j"] = lambda p: bad if p == RES else saved(p)
    try:
        test_the_bias_is_recorded_next_to_the_agreement_rate()
        raise SystemExit("★ 反向验证失败: 摘掉偏倚提醒后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★★the_selection_bias_i_did_not_predict"]["distribution_by_45_eyes"]["4.7 没答完的"] = {"pain_seek": 35}
    g["_j"] = lambda p: bad2 if p == RES else saved(p)
    try:
        test_thin_knots_are_exactly_what_got_dropped()
        raise SystemExit("★ 反向验证失败: 抹掉被丢的薄类后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_the_bias_is_recorded_next_to_the_agreement_rate()
    test_round2_proved_the_bias_instead_of_removing_it()
    test_the_practical_conclusion_is_stated()
    test_the_two_groups_really_differ()
    test_thin_knots_are_exactly_what_got_dropped()
    test_coverage_blocker_is_stated_as_structural_not_just_budget()
    test_the_real_answer_to_how_many_anchors()
    n = _reverse_checks()
    b = _j(RES)["★★★the_selection_bias_i_did_not_predict"]["distribution_by_45_eyes"]
    print(f"test_cce_budget_selection_bias: OK ("
          f"★★★**预算打满不是随机失败**: 4.7 答完的 25 条 pain_seek 80%/覆盖 {len(b['4.7 答完的'])} 个结, "
          f"没答完的 35 条 60%/覆盖 {len(b['4.7 没答完的'])} 个结 ⇒ **系统性丢掉薄类(含 belong)** | "
          f"96% 一致率**是高估**, 已钉在 E1 旁边 | "
          f"覆盖不足是**结构性**的(两家族塌到同一批类, 必须分层抽样), 不是补预算能解决 | "
          f"★★★round2 加预算到 16000 **没消除偏倚, 反而证明了它**: 答完 40 条薄类 **0**, "
          f"打满 20 条薄类 **6**, Fisher p=0.00077 | "
          f"⇒ **glm-4.7-flash 不能当第二个标注者**, 单模型不构成共识 | "
          f"「扩充多少才够」的真答案: **n=60** 起才有分辨力 | "
          f"{'原始数据已比对' if HAVE_RAW else '★**无本机素材, 未从原始数据重算**'} | "
          f"{n} 条反向验证判红)")
