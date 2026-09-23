"""任何**用规则代替判断**的方案, 必须先在既有真值上做**阳性对照** —— 零 API。

## ★★★ 这条闸的来历: 我今天在同一个坑里踩了两次

**第一次(Study 2)**: 用 belong 自己定义里的标志词挑候选, 再问一个被告知
「belong = only me?」的仪器认不认 —— **循环**。当时是脚本自带的循环性自检抓到的,
处理办法是**拆两臂**(ARM_CLEAN / ARM_LEAKED), 把缺陷变成一个被测量。

**第二次(锚例扩充)**: 我说 reward/audit 的 `hard_discriminant` 是「二值前置」⇒
「表面特征, 规则可核验」⇒ 能机械产出负例锚。实测:
· audit 的 6 条正则在 **1208 篇帖 + 86 条评论上一条都没命中过**
· ★★★ 而**既有 audit 锚例 p25z258(真值就是 audit)按我的规则会被判「一定不是 audit」**

看原文就知道错在哪: 它写的是「…which device would **you** fit that patient with?」——
**确实是**「直接指向你的质询句」, 只是不是我编的那几个短语。
★ 我把 hard_discriminant 里的三个括号例子当成了**穷举**, 而它们是**例示**。
  「直接指向你的质询句」是一个**语用范畴, 不是词表**。

★★ 而我在同一份文件的 B 节里**自己写过**这条警告(「不给软判断结编词表, 因为判别式写的是『落点意图』」),
   然后在 A 节里换个说法又踩了一次 —— 这次猜的是「表面特征」而不是「意图」。

## 本闸钉什么
① 撤销记录必须在, 且写明证伪过程(否则下一个人会照着 A 节再做一遍)
② **阳性对照的一般规则**: 仓里任何「规则 → 真值」的方案, 若存在既有真值样本,
   必须能重现它们。本闸对现有的两处规则化方案各跑一次现算对照。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAND = ROOT / "tests/data/anchor_candidates_for_adjudication.json"
ANCH = json.loads((ROOT / "accuracy/data/anchors.json").read_text(encoding="utf-8"))["anchors"]
CORPUS = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def test_the_retraction_is_recorded_with_its_falsification():
    d = _j(CAND)
    k = "★★★A_RETRACTED_the_rule_verifiable_route_was_falsified"
    assert k in d, "★ 撤销记录不见了 —— 下一个人会照着原方案再做一遍"
    assert "★A_mechanically_verifiable_NEGATIVE_anchors" not in d, "★ 被撤销的方案又回来了"
    t = json.dumps(d[k], ensure_ascii=False)
    assert "p25f" in t or "p25z258" in t, "★ 证伪用的那条锚例 id 不见了"
    assert "例示" in t and "穷举" in t, "★ 「把例示当穷举」这个根因不见了"
    assert "27" in json.dumps(d, ensure_ascii=False), "★ 九结全部待裁定(>=27 条)这条不见了"


def test_the_retracted_audit_regexes_really_fail_the_positive_control():
    """★★ 现算: 用被撤销的正则去判既有 audit 锚例, 必须**判错** —— 这是撤销的依据。"""
    d = _j(CAND)["★★★A_RETRACTED_the_rule_verifiable_route_was_falsified"]
    pats = d["retracted_regexes"]["audit"]
    truth = [a for a in ANCH if a["knot"] == "audit"]
    assert truth, "★ 既有锚例里没有 audit 了 —— 那这条证伪的依据要重找"
    for a in truth:
        assert not any(re.search(x, a["text"].lower()) for x in pats), (
            f"★ 被撤销的 audit 正则现在能命中真值锚例 {a['id']} 了 —— "
            "若确实修好了规则, 请撤销本次撤销并重新验证")
    # ★ 且它们在整个语料上命中率为 0 —— 「零命中」使负例判定**平凡为真**
    n = sum(1 for c in CORPUS if any(re.search(x, c["b"].lower()) for x in pats))
    assert n == 0, f"★ 被撤销的 audit 正则在语料上命中 {n} 条了 —— 情况变了, 需重估"


def test_reward_rule_was_never_validated_and_that_is_said_so():
    """★ audit 能被证伪纯属侥幸(恰好有 audit 锚例); reward 规则**未经检验**, 必须写明。"""
    d = _j(CAND)["★★★A_RETRACTED_the_rule_verifiable_route_was_falsified"]
    assert "reward 规则是未经检验的" in json.dumps(d, ensure_ascii=False), \
        "★ 「reward 那半未经检验」这句不见了 —— 那会让人以为只有 audit 有问题"
    assert not [a for a in ANCH if a["knot"] == "reward"], (
        "★ 现在有 reward 锚例了 ⇒ **可以对 reward 规则做阳性对照了**, 请去做, 然后更新本断言")


def test_the_general_rule_is_stated():
    """★★★ 一般教训必须在: 用规则代替判断前, 先在既有真值上做阳性对照。"""
    t = json.dumps(_j(CAND), ensure_ascii=False)
    assert "必须先在既有真值上做阳性对照" in t, "★ 一般教训不见了"
    assert "做完才想起来验" in t, "★ 「我是做完才验的」这句自陈不见了 —— 它是这条教训的力度所在"


def test_study2_circularity_split_is_the_sibling_case():
    """★ 同一个坑的第一次(Study 2 拆两臂)必须还在, 两者互为参照。"""
    s2 = _j(ROOT / "tests/data/study2_belong_discriminant.json")
    assert "★circularity_handled_by_splitting_not_deleting" in s2
    assert "不是关键词匹配" in json.dumps(s2, ensure_ascii=False)


def _reverse_checks():
    n = 0
    g = globals()
    import copy
    saved = g["_j"]
    d = saved(CAND)
    bad = copy.deepcopy(d)
    bad.pop("★★★A_RETRACTED_the_rule_verifiable_route_was_falsified")
    g["_j"] = lambda p: bad if p == CAND else saved(p)
    try:
        test_the_retraction_is_recorded_with_its_falsification()
        raise SystemExit("★ 反向验证失败: 删掉撤销记录后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    saved_a = g["ANCH"]
    g["ANCH"] = saved_a + [{"id": "fake", "knot": "reward", "text": "thanks"}]
    try:
        test_reward_rule_was_never_validated_and_that_is_said_so()
        raise SystemExit("★ 反向验证失败: 加入 reward 锚例后仍绿(应提醒去做阳性对照)")
    except AssertionError:
        n += 1
    finally:
        g["ANCH"] = saved_a
    return n


if __name__ == "__main__":
    test_the_retraction_is_recorded_with_its_falsification()
    test_the_retracted_audit_regexes_really_fail_the_positive_control()
    test_reward_rule_was_never_validated_and_that_is_said_so()
    test_the_general_rule_is_stated()
    test_study2_circularity_split_is_the_sibling_case()
    n = _reverse_checks()
    print(f"test_cce_rule_positive_control: OK ("
          f"★★★「规则可核验的负例锚」已**撤销**且证伪过程留档 | "
          f"现算确认: 被撤销的 audit 正则**判错既有真值锚例 p25z258**, 且全语料命中 0 条 | "
          f"★reward 那半**未经检验**已写明(没有 reward 锚例可对照) | "
          f"一般教训在: **用规则代替判断前先在既有真值上做阳性对照** | "
          f"与 Study 2 的循环性拆两臂互为参照 | {n} 条反向验证判红)")
