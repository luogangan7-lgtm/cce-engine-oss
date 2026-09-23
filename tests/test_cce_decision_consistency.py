"""资格考的 decision consistency —— 以及**不许把它读成「v2 更好」** 。零 API, 现算。

## 实测(同一份 5 锚例, temp=0.0, 四次独立运行)
| 标注者 | 四次得分 | v1 二值 | v2 三态 |
|---|---|---|---|
| M2.7 | **3, 5, 4, 4** | FAIL/PASS/PASS/PASS ★**翻转** | UNRESOLVED × 4 |
| 其余四人 | 全 4~5 | 全 PASS | UNRESOLVED × 4 |

· v1: 判决覆盖率 **100%**, 但 **1/5** 名标注者翻转过。
· v2: **0/5** 翻转 —— **但判决覆盖率 0%**, 它一次判决都没做。

## ★★★ 本闸真正防的是一句好听的假话
「v2 比 v1 稳」是**错的读法**。正确的是:
**v2 把一个不可靠的判决换成了一个诚实的空缺。**
空缺不是成果, 是对现状的准确描述 —— 5 个锚例本来就不足以判决, v1 只是在假装能判。

★ 所以本闸**同时**断言两件相反的事: v2 不翻转 **且** v2 覆盖率为 0。
  只钉前一件, 就会让下一个人把它读成「新规则更好」。
"""
import json
import pathlib
from collections import Counter
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DC = ROOT / "tests/data/qualification_decision_consistency.json"
QR = ROOT / "tests/data/qualification_exam_resolution.json"
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def _wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (max(0.0, c - h), min(1.0, c + h))


def _v2(k, n, pL=0.70, pH=0.90):
    lo, hi = _wilson(k, n)
    return "QUALIFIED" if lo >= pH else ("DISQUALIFIED" if hi <= pL else "UNRESOLVED")


def test_v1_flipped_and_v2_did_not():
    d = _j(DC)
    assert d["★summary"]["v1_flipped"] == ["MiniMax-M2.7"], \
        f"★ v1 翻转名单变了: {d['★summary']['v1_flipped']}"
    assert d["★summary"]["v2_flipped"] == [], "★ v2 也翻转了 —— 那是新情况"


def test_v2_coverage_is_zero_and_that_must_be_said_in_the_same_breath():
    """★★★ 核心: 「不翻转」与「零覆盖率」必须**同时**被钉住。"""
    d = _j(DC)
    assert d["★summary"]["★v2_mean_coverage"] == 0.0, (
        f"★ v2 覆盖率不再是 0 了({d['★summary']['★v2_mean_coverage']}) —— "
        "若锚例扩充了, 请重算并更新「空缺」那段说法")
    t = json.dumps(d, ensure_ascii=False)
    assert "不能说「v2 更稳」" in t, "★★★ 那句防误读的话不见了 —— 没有它, 结论会被读反"
    assert "诚实的空缺" in t and "空缺本身不是成果" in t


def test_the_numbers_are_recomputed_from_the_raw_scores():
    """★ 不信任落盘的一致率, 从四次原始得分现算。"""
    d = _j(DC)
    for m, r in d["per_model"].items():
        hs = r["scores"]
        assert len(hs) == 4, f"★ {m} 不再是四次"
        v1 = Counter("PASS" if h >= 4 else "FAIL" for h in hs)
        v2 = Counter(_v2(h, 5) for h in hs)
        assert dict(v1) == r["v1"], f"★ {m} 的 v1 分布与现算不符"
        assert dict(v2) == r["v2"], f"★ {m} 的 v2 分布与现算不符"
        cov = sum(1 for h in hs if _v2(h, 5) != "UNRESOLVED") / len(hs)
        assert abs(cov - r["v2_coverage"]) < 1e-9


def test_the_flip_rate_matches_the_binomial_theory():
    """★ 两条独立线索同向: 实测翻转率 1/4 vs p=0.80 的理论误判率 26.3%。"""
    P = lambda p: sum(comb(5, k) * p ** k * (1 - p) ** (5 - k) for k in (4, 5))
    hs = _j(DC)["per_model"]["MiniMax-M2.7"]["scores"]
    p_hat = sum(hs) / (5 * len(hs))
    assert abs(p_hat - 0.80) < 0.01, f"★ M2.7 的矩估计变了: {p_hat}"
    theory = 1 - P(p_hat)
    observed = sum(1 for h in hs if h < 4) / len(hs)
    assert abs(theory - observed) < 0.10, (
        f"★ 理论误判率 {theory:.3f} 与实测翻转率 {observed:.3f} 不再相符 —— 需重新解释")
    lo, hi = _wilson(1, 4)
    assert hi - lo > 0.5, "★ n=4 的区间应当很宽 —— 若变窄了说明样本量增加了, 请更新"


def test_consistency_is_not_accuracy():
    """★★ 必须写明: 已证「v1 会翻转」, **未证**「v1 判错了谁」。"""
    t = json.dumps(_j(DC), ensure_ascii=False)
    assert "decision accuracy" in t and "未证" in t
    assert "同一个瓶颈" in t, "★ 「accuracy 与锚例扩充是同一个瓶颈」这条不见了"


def test_the_fourth_run_is_recorded():
    q = _j(QR)
    assert "run4_2026-09-07_confirmatory" in q["observed"], "★ 第四次运行没记"
    assert q["★★three_runs_three_answers"]["MiniMax-M2.7"] == \
        ["3/5 不合格", "5/5 合格", "4/5 合格", "4/5 合格"], "★ M2.7 的四次序列变了"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(DC)
    bad = copy.deepcopy(d)
    bad["★summary"]["★v2_mean_coverage"] = 1.0
    g["_j"] = lambda p: bad if p == DC else saved(p)
    try:
        test_v2_coverage_is_zero_and_that_must_be_said_in_the_same_breath()
        raise SystemExit("★ 反向验证失败: 把覆盖率改成 1.0 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★the_tradeoff_is_the_whole_finding"] = "v2 比 v1 稳。"
    g["_j"] = lambda p: bad2 if p == DC else saved(p)
    try:
        test_v2_coverage_is_zero_and_that_must_be_said_in_the_same_breath()
        raise SystemExit("★ 反向验证失败: 把结论改成「v2 更稳」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad3 = copy.deepcopy(d)
    bad3["per_model"]["MiniMax-M2.7"]["scores"] = [5, 5, 5, 5]
    g["_j"] = lambda p: bad3 if p == DC else saved(p)
    try:
        test_the_numbers_are_recomputed_from_the_raw_scores()
        raise SystemExit("★ 反向验证失败: 篡改原始得分后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_v1_flipped_and_v2_did_not()
    test_v2_coverage_is_zero_and_that_must_be_said_in_the_same_breath()
    test_the_numbers_are_recomputed_from_the_raw_scores()
    test_the_flip_rate_matches_the_binomial_theory()
    test_consistency_is_not_accuracy()
    test_the_fourth_run_is_recorded()
    n = _reverse_checks()
    d = _j(DC)
    print(f"test_cce_decision_consistency: OK ("
          f"四次同卷 · v1 翻转 {len(d['★summary']['v1_flipped'])}/5(M2.7: 3,5,4,4) 覆盖率 100% | "
          f"v2 翻转 0/5 **但覆盖率 {d['★summary']['★v2_mean_coverage']:.0%}** | "
          f"★★★「不翻转」与「零覆盖」**同时**钉住 —— 防的是「v2 更稳」这句好听的假话 | "
          f"分布从四次原始得分**现算** | 翻转率 1/4 与 p=0.80 的理论 26.3% 相符 | "
          f"★consistency ≠ accuracy, 后者与锚例扩充**同一个瓶颈** | {n} 条反向验证判红)")
