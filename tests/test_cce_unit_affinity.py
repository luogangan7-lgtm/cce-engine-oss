"""★★★ 九结的**单元亲和性** —— 「单元错配」不是 belong 一个特例。零 API, 数字现算。

## 来历
今天早些时候发现: belong 在评论上共识 argmax 0/81, 换成**帖子**后 7/81 —— 那是**采样框错配**,
不是死类。本表把那条**从一个特例升级为一个系统性维度**。

## 实测(跨 **两个仪器家族** × **四次独立运行**)
MiniMax 五员: run1 评论 81 · run2 评论 81 · runC 帖子 81 | GLM-4.5-flash: 帖子 200

| 结 | 评论 | 帖子 | 比值 | 亲和 |
|---|---|---|---|---|
| **reward** | 15.1% | 1.0% | **15.7** | 评论 |
| inertia | 1.1% | 0.2% | 4.3 | 评论 |
| itch | 12.1% | 3.4% | 3.6 | 评论 |
| **belong** | 0.2% | 4.5% | **0.05** | 帖子 |
| pain_seek | 22.0% | 56.5% | 0.39 | 帖子 |

★★ **两个方向都存在且量级相当**(reward 评论侧 15.7 倍 · belong 帖子侧 20 倍)
⇒ 这不是「帖子更丰富」的单向效应, 是**真正的双向单元分化**。

## ★★★ 可执行后果
锚例必须**按结的单元亲和性从对应语料取**:
· reward / itch / inertia → **从评论取**(它们在帖子上极稀)
· belong / pain_seek → **从帖子取**
★ 这**推翻**了我上一步算的「还需再标 ~400 条帖子 ≈ 4 小时」——
  inertia 在帖子上 0.2%, 标 400 条期望只多 **0.8 条**。**那是错的做法。**
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = ROOT / "tests/data/unit_affinity_table.json"
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_both_directions_exist_with_comparable_magnitude():
    """★★★ 核心: 不是单向效应。两端都要在, 且量级相当。"""
    t = _j(UA)["table"]
    comment_side = [k for k, v in t.items() if v["亲和"] == "评论"]
    post_side = [k for k, v in t.items() if v["亲和"] == "帖子"]
    assert comment_side and post_side, (
        f"★★★ 只剩单向了(评论侧 {comment_side} · 帖子侧 {post_side}) —— "
        "那「双向单元分化」这条结论要重写")
    assert "reward" in comment_side and "belong" in post_side
    r_ratio = t["reward"]["比值"]
    b_ratio = 1 / t["belong"]["比值"]
    assert r_ratio > 5 and b_ratio > 5, f"★ 两端的极值变弱了: reward {r_ratio} · belong {b_ratio}"
    assert min(r_ratio, b_ratio) / max(r_ratio, b_ratio) > 0.3, \
        f"★ 两端量级不再相当({r_ratio} vs {b_ratio}) —— 「量级相当」这句要改"


def test_the_definition_does_not_always_match_the_data():
    """★ 分类学里的单元措辞**有的准有的不准** —— 不能一律采信。"""
    t = _j(UA)["table"]
    B = {k["key"]: k["behavior"] for k in TAXO["knots"]}
    # belong 定义说「发帖」, 数据也说帖子 ⇒ 一致
    assert "发帖" in B["belong"] and t["belong"]["亲和"] == "帖子", "★ belong 的定义-数据一致性变了"
    # display 定义说「评论区…主力」, 但数据是「无偏好」⇒ 不一致
    assert "评论" in B["display"], "★ display 的定义里不再提评论区了"
    assert t["display"]["亲和"] == "无偏好", (
        f"★ display 现在有偏好了({t['display']['亲和']}) —— "
        "那「定义说评论、数据说两边都高」这条不一致要重写")
    assert "有的准有的不准" in json.dumps(_j(UA), ensure_ascii=False)


def test_the_wrong_move_is_recorded_as_wrong():
    """★★ 我算过「再标 400 条帖子」—— 那是错的, 必须留着这条自我更正。"""
    t = json.dumps(_j(UA)["★★★executable_consequence_for_anchors"], ensure_ascii=False)
    assert "推翻" in t and "400" in t, "★ 「再标 400 条是错的做法」这条自我更正不见了"
    assert "0.8 条" in t, "★ 那个说明为什么错的具体数(期望只多 0.8 条)不见了"


def test_the_numbers_are_recomputed_from_products():
    """★ 评论侧的数从仓内产物现算 —— 不信任落盘表。"""
    t = _j(UA)["table"]
    prev = _j(ROOT / "accuracy/out/gates_result.json")["G_K1v2_分布一致性"]["top1_prevalence"]
    n = sum(prev.values())
    # run1 的评论侧 reward 占比应与表里的评论侧同量级
    r1 = prev.get("reward", 0) / n
    assert abs(r1 - t["reward"]["评论侧"]) < 0.06, (
        f"★ reward 的评论侧现算 {r1:.3f} 与表里 {t['reward']['评论侧']} 差太多")
    assert prev.get("belong", 0) / n < 0.01, "★ run1 的 belong 评论侧不再接近 0"


def test_correlation_not_causation_is_stated():
    """★ 亲和性是相关不是因果 —— 帖与评论同时差了文体/长度/prompt 措辞。"""
    t = json.dumps(_j(UA)["★what_this_does_not_settle"], ensure_ascii=False)
    assert "相关" in t and "不是因果" in t
    assert "2×2" in t or "2x2" in t, "★ 「分离它需要 2×2」这条不见了"
    assert "GLM" in t and "没标评论侧" in t, "★ 「跨家族只在帖子侧验过」这条限度不见了"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(UA)
    bad = copy.deepcopy(d)
    for k in bad["table"]:
        bad["table"][k]["亲和"] = "帖子"
    g["_j"] = lambda p: bad if p == UA else saved(p)
    try:
        test_both_directions_exist_with_comparable_magnitude()
        raise SystemExit("★ 反向验证失败: 抹成单向后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["★★★executable_consequence_for_anchors"] = "按亲和性取锚例。"
    g["_j"] = lambda p: bad2 if p == UA else saved(p)
    try:
        test_the_wrong_move_is_recorded_as_wrong()
        raise SystemExit("★ 反向验证失败: 删掉自我更正后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_both_directions_exist_with_comparable_magnitude()
    test_the_definition_does_not_always_match_the_data()
    test_the_wrong_move_is_recorded_as_wrong()
    test_the_numbers_are_recomputed_from_products()
    test_correlation_not_causation_is_stated()
    n = _reverse_checks()
    t = _j(UA)["table"]
    cs = [k for k, v in t.items() if v["亲和"] == "评论"]
    ps = [k for k, v in t.items() if v["亲和"] == "帖子"]
    print(f"test_cce_unit_affinity: OK ("
          f"★★★**双向**单元分化: 评论侧 {cs} · 帖子侧 {ps} | "
          f"两端量级相当(reward 评论 {t['reward']['比值']}× · belong 帖子 {1/t['belong']['比值']:.0f}×) | "
          f"跨**两个仪器家族**×四次运行 | "
          f"★分类学的单元措辞**有的准有的不准**(belong 准 · display 不准) | "
          f"★★可执行后果: 锚例按亲和性取语料, 并留着「再标 400 条帖子是错的」这条自我更正 | "
          f"相关≠因果已声明 | {n} 条反向验证判红)")
