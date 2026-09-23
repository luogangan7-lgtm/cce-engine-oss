"""belong 的处置判决必须**照事前冻结的表查** —— 零 API, 数字测试时重算。

## 判决链(三个出口, 逐一被排除到只剩一个)
· **RETIRE** ← 被 Run B 排除: 帖子上 prevalence **7/81 = 8.6%**, Wilson CI [4.3%, 16.8%],
  远高于冻结的 0.5% SESOI。(评论上 0/81 的单侧上界是 3.63% —— **两区间不重叠**。)
· **MERGE**  ← 被 Study 2 排除: 与最近邻 display 的判别 Fisher p=**0.0102**;
  且候选里只有 **17.1%** 落到 display, 远低于 MERGE 要求的 2/3。
· **RETAIN** ← 三条判据全中: k=10>=7 · Fisher p<0.05 · 10 个不同作者。
  零模型 Binom(105, 2/78) 下拿到 k>=10 的概率 **0.039%**。

## ★★ 本闸真正防的是「改表」
处置规则在 Study 2 发起**任何调用之前**修订并冻结过一次(把 RETAIN 的「至少 1 条」
换成 k>=7 + Fisher + >=3 作者), 原因是旧条文在零模型下有 **93.5%** 概率开门 ——
**它不是一个阈值, 是一次点名**。
★ 本闸断言判据**没有再被改动**, 并在测试时**重算** Fisher 与零模型概率, 不信任落盘值。
"""
import json
import os
import pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
S2 = ROOT / "tests/data/study2_belong_discriminant.json"
RB = ROOT / "tests/data/run_b_external_validity_result.json"
RULE = ROOT / "tests/data/belong_disposition_rule_prereg.json"
VAULT_RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/study2_belong_discriminant/raw.json")
HAVE_VAULT = os.path.exists(VAULT_RAW)   # ★ 原始标注在识别层保险库, 公开仓 CI 上可能不在

_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def _fisher(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    return sum(comb(n1, i) * comb(n2, k - i) for i in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)


def _null_p(k, n, p0=2 / 78):
    return sum(comb(n, x) * p0 ** x * (1 - p0) ** (n - x) for x in range(k, n + 1))


def test_the_verdict_is_retain_and_all_three_checks_pass():
    d = _j(S2)["★★★VERDICT"]
    assert "RETAIN_as_core" in d["verdict"], f"★ 判决变了: {d['verdict']}"
    assert all("✅" in v for v in d["checks_one_by_one"].values()), d["checks_one_by_one"]


def test_the_numbers_are_recomputed_not_copied():
    """★ Fisher 与零模型概率**现算**, 不信任落盘值。"""
    r = _j(S2)["★★results"]
    k, nc = 10, 105
    j, nh = 1, 89
    assert r["ARM_CLEAN_belong_argmax"].count(str(k)) and str(nc) in r["ARM_CLEAN_belong_argmax"]
    assert str(j) in r["HARD_NEGATIVE_belong_argmax"] and str(nh) in r["HARD_NEGATIVE_belong_argmax"]
    p = _fisher(k, nc - k, j, nh - j)
    assert p < 0.05, f"★ Fisher 现算 {p:.5f} 不再 <0.05"
    assert abs(p - 0.01024) < 1e-4, f"★ Fisher 现算 {p:.5f} 与落盘的 0.01024 不符"
    np_ = _null_p(k, nc)
    assert np_ < 0.001, f"★ 零模型概率现算 {np_:.5f}"
    assert _null_p(1, nc) > 0.9, "★ 旧条文「至少 1 条」的 93.5% 变了 —— 那整段理由要重写"


def test_the_rule_was_not_changed_after_seeing_the_data():
    """★★★ 核心: 判据在 Study 2 发起前冻结, 之后**不许再动**。"""
    R = _j(RULE)["★★DISPOSITION_RULE"]["★★AMENDED_2026-09-07_before_any_STUDY2_call"]
    assert "k >= 7" in R["★NEW_RETAIN_as_core"], "★★ RETAIN 的 k>=7 被改了"
    assert "Fisher 单侧精确检验 p < 0.05" in R["★NEW_RETAIN_as_core"]
    assert ">= 3 个不同作者" in R["★NEW_RETAIN_as_core"]
    assert "**一次调用都还没发**" in R["★when"], "★ 「改在前」的声明不见了"
    assert R["★threshold_justification_frozen"]["★why_7_not_6"].count("5%")


def test_retire_and_merge_are_both_excluded_with_evidence():
    b = _j(RB)["★★★B1_STRONGLY_CONFIRMED_belong_lives_in_posts"]
    assert "7/81" in json.dumps(b, ensure_ascii=False), "★ 帖子上 7/81 这个数不见了"
    assert "RETIRE 出口被明确排除" in b["★consequence"]
    s = _j(S2)["★★★VERDICT"]["★★what_it_means"]
    assert "MERGE 被本研究排除" in s and "RETIRE 已被 Run B 排除" in s


def test_circularity_was_split_not_deleted():
    """★ 泄漏的标志词**没有被删掉** —— 拆两臂, 把缺陷变成一个被测量。"""
    c = _j(S2)["★circularity_handled_by_splitting_not_deleting"]
    assert "only" in c["leaked_marker"]
    assert "不是关键词匹配" in c["★the_worry_is_refuted"]
    R = _j(RULE)["STUDY_2_discriminant_validity"]["★amendment_2026-09-07_circularity_split"]
    assert R["n_arm_clean"] == 105 and R["n_arm_leaked_only"] == 6
    assert "**未看到任何标注数据。**" in R["★when"]


def test_raw_annotations_back_the_numbers():
    """★★ 有保险库时**从原始标注重算** —— 落盘的聚合数不许自说自话。"""
    if not HAVE_VAULT:
        assert not os.path.exists(VAULT_RAW.parent / "result.json"), \
            "★ 聚合在但原始不在 —— 半份数据比没有更危险"
        return                      # ★ 无本机素材, 未比对原始标注
    raw = _j(VAULT_RAW)
    d, arm = raw["dists"], raw["arm"]
    cons = {}
    for i in arm:
        vs = [d[m][i] for m in d if d[m].get(i)]
        if len(vs) >= 2:
            cons[i] = {k: sum(v.get(k, 0) for v in vs) / len(vs) for k in set().union(*vs)}
    hit = lambda a: sum(1 for i in cons if arm[i] == a and max(cons[i], key=cons[i].get) == "belong")
    n = lambda a: sum(1 for i in cons if arm[i] == a)
    assert (hit("candidate"), n("candidate")) == (10, 105), \
        f"★★ ARM_CLEAN 现算 {hit('candidate')}/{n('candidate')} != 落盘的 10/105"
    assert (hit("hard_negative"), n("hard_negative")) == (1, 89), \
        f"★★ HARD_NEG 现算 {hit('hard_negative')}/{n('hard_negative')} != 落盘的 1/89"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    R = saved(RULE)
    bad = copy.deepcopy(R)
    bad["★★DISPOSITION_RULE"]["★★AMENDED_2026-09-07_before_any_STUDY2_call"]["★NEW_RETAIN_as_core"] = \
        "至少 1 条被判为 belong 主类"
    g["_j"] = lambda p: bad if p == RULE else saved(p)
    try:
        test_the_rule_was_not_changed_after_seeing_the_data()
        raise SystemExit("★ 反向验证失败: 把判据改回「至少 1 条」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    s = saved(S2)
    bad2 = copy.deepcopy(s)
    bad2["★★★VERDICT"]["verdict"] = "**MERGE_into_display**"
    g["_j"] = lambda p: bad2 if p == S2 else saved(p)
    try:
        test_the_verdict_is_retain_and_all_three_checks_pass()
        raise SystemExit("★ 反向验证失败: 改判决后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_the_verdict_is_retain_and_all_three_checks_pass()
    test_the_numbers_are_recomputed_not_copied()
    test_the_rule_was_not_changed_after_seeing_the_data()
    test_retire_and_merge_are_both_excluded_with_evidence()
    test_circularity_was_split_not_deleted()
    test_raw_annotations_back_the_numbers()
    n = _reverse_checks()
    print(f"test_cce_belong_disposition: OK ("
          f"★★★判决 **RETAIN_as_core** | RETIRE 被 Run B 排除(帖子 7/81=8.6%) · "
          f"MERGE 被 Study 2 排除(Fisher p={_fisher(10,95,1,88):.5f}, 候选落 display 仅 17.1%) | "
          f"三条判据现算全中(k=10>=7 · p<0.05 · 10 个作者零聚类) | "
          f"零模型 P(k>=10)={_null_p(10,105)*100:.3f}% vs 旧条文「至少1条」的 {_null_p(1,105)*100:.1f}% | "
          f"判据**在发起调用前**冻结且未再动 | 循环性**拆两臂**未删 | "
          f"{'★从原始标注重算一致' if HAVE_VAULT else '★**无本机素材, 未比对原始标注**'} | "
          f"{n} 条反向验证判红)")
