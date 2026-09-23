"""★★★ 2026-09-07 那次 PASS 的**资格前提已撤销** —— 而数字**没改**。零 API, 现算。

## 为什么改
旧 `overall_pass: True` 由三个必要条件构成:
`{G_K1: True, G_K2: True, annotator_qualification: 'OK'}`。
★ 那个 `'OK'` 是 **v1 规则**产出的, 而 v1(5 锚例 · top1>=4/5)已实测为**抽签**:
同卷四次跑出 **3/5、5/5、4/5、4/5**; n=5 在任何 cutoff 下都做不到 α、β 同时 <5%。
★★ 按 v2 三态判据, **五名标注者全部 UNRESOLVED —— 从未有任何一个被有效认证过。**

## ★★★ 本闸真正防的是两个方向的过度
① **不许把数字说成假的**: top2=0.9042 / JS=0.2321 仍是**原数据原流程下的历史结果**,
   它们不会因为前提被撤销而在算术上变假。
② **不许继续说「资格考生效下通过」**: 生效的是一条**无分辨力**的规则; 且那次的 4 人面板
   是**一次抽签**剔除 M2.7 的结果, 而实测**保留 M2.7 的 5 人面板更稳**
   (自助失败率 **7.0% vs 23.1%**)。

⇒ 正确表述被钉死为: 「**在一个未经有效资格认证的 4 人面板上, G-K1 的两项指标达标**」。

★ 依据: 2026-09-08 网页 GPT(Pro, 10m10s, 联网)裁决 ——
「若旧 PASS 依赖『面板已通过有效资格认证』这一前提, 而该前提现在不能成立,
 就应**修订资格声明**, 而不只是保留原分数。」
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
PROD = json.loads((ROOT / "accuracy/out/gates_result.json").read_text(encoding="utf-8"))
KEY = "★qualification_premise_of_the_2026-09-07_PASS_is_revised"


def test_the_revision_exists_and_names_the_three_components():
    assert KEY in TAXO, "★ 资格前提的撤销记录不见了"
    t = TAXO[KEY]
    assert "annotator_qualification" in t and "'OK'" in t, "★ 没写明旧 PASS 依赖哪个组件"
    assert "3/5、5/5、4/5、4/5" in t, "★ 四次考试的序列不见了 —— 它是「抽签」的依据"
    assert "全部 UNRESOLVED" in t


def test_the_numbers_are_explicitly_not_called_fake():
    """★★ 方向一: 不许把历史数字说成假的。"""
    t = TAXO[KEY]
    assert "不是假的" in t, "★★ 「数字不是假的」这句不见了 —— 少了它, 撤销会被读成「结论作废」"
    assert "0.9042" in t and "0.2321" in t, "★ 具体数字不见了"
    # ★ 现算: 产物里的数字确实**没被改过**
    g = PROD["G_K1v2_分布一致性"]
    assert g["mean_top2_hit"] == 0.9042 and g["mean_JS"] == 0.2321, (
        f"★★★ 产物里的数字被改了({g['mean_top2_hit']} / {g['mean_JS']}) —— "
        "撤销前提**不许动数字**, 那是两回事")
    assert PROD["overall_pass"] is True, "★ 历史产物的 overall_pass 被改了 —— 它是历史记录, 不该改"


def test_the_claim_is_no_longer_qualification_effective():
    """★★ 方向二: 不许继续说「资格考生效下通过」。"""
    s = TAXO["status"]
    assert "资格考真正生效的条件下" not in s, "★★ 「资格考生效」这个说法回来了"
    assert "从未被有效认证" in s or "全部 UNRESOLVED" in s, "★ status 没写明面板未被认证"
    import cce_knot_classify as K
    assert "面板从未被有效认证" in K.CANDIDATE_CAVEAT, "★ caveat 没跟着改"
    assert "资格考生效" not in K.CANDIDATE_CAVEAT


def test_the_exclusion_was_a_coin_flip_and_hurt_the_metric():
    """★★★ 那次 4 人面板是抽签的结果, 而 5 人面板更稳 —— 两个方向都要在。"""
    t = TAXO[KEY]
    assert "抽签" in t and "M2.7" in t
    assert "7.0%" in t and "23.1%" in t, "★ 「保留 M2.7 更稳」的两个数不见了"
    # ★ 与重复性产物交叉核对
    bs = json.loads((ROOT / "tests/data/gk1_bootstrap.json").read_text(encoding="utf-8"))
    j5 = bs["run2_5panel_as_run"]["point"]["JS"]
    j4 = bs["run2_restricted_to_run1_4panel"]["point"]["JS"]
    assert j4 > j5, f"★ 剔除后 JS 不再更差({j4} vs {j5}) —— 那这条论证要重做"


def test_the_correct_wording_is_pinned():
    """★ 唯一被允许的表述, 逐字钉住。"""
    t = TAXO[KEY]
    assert "在一个未经有效资格认证的 4 人面板上, G-K1 的两项指标达标" in t, \
        "★★ 那句「正确表述」被改了 —— 它是本次撤销的落点"


def test_v2_really_says_all_unresolved():
    """★ 现算: v2 判据在四次考试的众数上确实给全员 UNRESOLVED。"""
    import run_gates as RG
    scores = {"MiniMax-M3": 5, "MiniMax-M2.5": 5, "MiniMax-M2.7": 4, "MiniMax-M2": 5, "MiniMax-Text-01": 5}
    states = {m: RG.qualification_state(k, 5)[0] for m, k in scores.items()}
    assert set(states.values()) == {"UNRESOLVED"}, f"★ v2 不再给全员 UNRESOLVED 了: {states}"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved_t, saved_p = g["TAXO"], g["PROD"]
    bad = copy.deepcopy(saved_t)
    bad[KEY] = bad[KEY].replace("不是假的", "已作废")
    g["TAXO"] = bad
    try:
        test_the_numbers_are_explicitly_not_called_fake()
        raise SystemExit("★ 反向验证失败: 把「不是假的」改成「已作废」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["TAXO"] = saved_t
    badp = copy.deepcopy(saved_p)
    badp["G_K1v2_分布一致性"]["mean_JS"] = 0.19
    g["PROD"] = badp
    try:
        test_the_numbers_are_explicitly_not_called_fake()
        raise SystemExit("★ 反向验证失败: 篡改产物数字后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["PROD"] = saved_p
    bad2 = copy.deepcopy(saved_t)
    bad2["status"] = bad2["status"].replace("从未被有效认证", "资格考真正生效的条件下")
    g["TAXO"] = bad2
    try:
        test_the_claim_is_no_longer_qualification_effective()
        raise SystemExit("★ 反向验证失败: 把「生效」说法放回去后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["TAXO"] = saved_t
    return n


if __name__ == "__main__":
    test_the_revision_exists_and_names_the_three_components()
    test_the_numbers_are_explicitly_not_called_fake()
    test_the_claim_is_no_longer_qualification_effective()
    test_the_exclusion_was_a_coin_flip_and_hurt_the_metric()
    test_the_correct_wording_is_pinned()
    test_v2_really_says_all_unresolved()
    n = _reverse_checks()
    print(f"test_cce_qualification_premise_revised: OK ("
          f"★★★旧 PASS 的「面板已通过有效资格认证」前提**已撤销** | "
          f"★两个方向都钉住: **数字不是假的**(现算产物仍是 0.9042/0.2321 且未被改) "
          f"**且不许再说「资格考生效」** | "
          f"那次 4 人面板是**一次抽签**剔除 M2.7 的结果, 而 5 人面板自助失败率 7.0% vs 23.1% | "
          f"唯一允许的表述已逐字钉住 | v2 现算确认五人全 UNRESOLVED | {n} 条反向验证判红)")
