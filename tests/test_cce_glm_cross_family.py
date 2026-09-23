"""GLM 作为**跨家族真值源**的阳性对照 —— 以及它的证据强度有多弱。零 API。

## 为什么需要它
库内铁律: **禁止拿测量模型(MiniMax)定锚例真值, 那是循环**。
⇒ 锚例扩充必须有第二个家族。2026-09-07 实测: 智谱 `api.z.ai` 的 flash 免费档可用。

## 阳性对照(今天刚立的闸: 用模型代替判断前, 先在既有真值上验)
在**人定的 5 个既有锚例**上, 串行 + max_tokens=6000:
· `glm-4.5-flash` **5/5**, 零重试
· `glm-4.7-flash` **4/4**(第 5 条 finish=length tok=6000 打满, **不是判错**)

## ★★★ 本闸真正防的是把 9/9 读成「可靠」
· 9/9 的 **Wilson 95% 下界只有 0.70** —— **排除不了真实准确率低到 70%**
· 那 5 条是**人挑出来当锚例的**(大概率是清晰样本) ⇒ **边界样本上的表现完全未知**,
  而边界样本恰恰是资格考最需要区分的地方
· 两个标注者**同属 GLM 家族**(4.5 与 4.7) ⇒ **共享先验查不出来**
  (与库内 2026-08-19 记的限度同型: 「验证者恰是另一个生成器…该盲验查不出来」)

★ 所以产物必须标 `cross_family_model_consensus`, **不得**标 human-adjudicated。

## ★ 顺带钉住两个踩过的坑
① flash 档是**推理模型**, `reasoning_content` 独占预算 —— max_tokens=1500 时 content 为空
   (第一次跑只有 2/5 与 1/5, **全是预算打满不是判错**)。**必须 >= 6000。**
② 并发 3 会大面积 429 —— **必须串行**。
③ 端点是 **api.z.ai**, 不是 open.bigmodel.cn。我第一次探活探错端点+档位, 误报「智谱不可用」;
   而**库里 2026-07-21 就记着 CCE 用的是 api.z.ai**。
"""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PC = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/glm_positive_control.json")
HAVE_PC = os.path.exists(PC)      # ★ 在保险库侧(含语料文本), 公开仓 CI 上可能不在
PRE = ROOT / "tests/data/anchor_expansion_prereg.json"
PROBE = ROOT / "probes/anchor_expansion_cross_family.py"
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def _wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (max(0.0, c - h), min(1.0, c + h))


def test_the_evidence_strength_is_stated_not_just_the_hit_rate():
    """★★★ 核心: 5/5 旁边必须有区间, 否则它会被读成「可靠」。"""
    d = _j(PRE)["★positive_control_first"]
    assert "5/5" in json.dumps(d["result"], ensure_ascii=False)
    lo, _ = _wilson(9, 9)
    assert abs(d["wilson95"]["两模型合计 9/9"][0] - round(lo, 4)) < 1e-4, "★ 落盘的区间与现算不符"
    assert lo < 0.75, f"★ 9/9 的下界现算 {lo:.4f} —— 若它变高了说明样本量增加了, 请更新说法"
    t = d["★★the_limits_of_this_evidence"]
    assert "排除不了真实准确率低到 70%" in t, "★ 下界那句不见了"
    assert "边界样本" in t and "未知" in t, "★ 「边界样本未验」这条不见了"


def test_the_positive_control_really_passed():
    """★ 阳性对照的原始记录必须在, 且失败项必须是**预算打满**而非判错。"""
    if not HAVE_PC:
        assert "5/5" in json.dumps(_j(PRE), ensure_ascii=False), \
            "★ 无本机素材时, 预注册里至少要留下对照结果"
        return                      # ★ 无本机素材, 未比对原始对照记录
    rows = _j(PC)
    for m in ("glm-4.5-flash", "glm-4.7-flash"):
        rs = [r for r in rows if r["model"] == m]
        assert rs, f"★ {m} 的对照记录不见了"
        ok = [r for r in rs if r["finish"] == "stop"]
        assert ok, f"★ {m} 没有一条成功返回"
        assert all(r["hit"] for r in ok), (
            f"★★ {m} 在成功返回的样本上**判错了**: "
            f"{[(r['id'], r['truth'], r['glm']) for r in ok if not r['hit']]} —— "
            "那 GLM 作为真值源的资格要重估")
        for r in rs:
            if not r["hit"] and r["finish"] != "stop":
                assert "length" in str(r["finish"]) or "err" in str(r["finish"]), \
                    f"★ {r['id']} 失败原因不是预算/网络: {r['finish']}"


def test_the_two_operational_traps_are_pinned():
    """★ 推理模型预算 + 必须串行 —— 两个坑都要在代码里。"""
    src = PROBE.read_text(encoding="utf-8")
    assert "MAX_TOK = 6000" in src, "★ max_tokens 被调小了 —— 1500 时 content 会是空的"
    assert "串行" in src and "reasoning_content" in src
    assert "api.z.ai" in src, "★ 端点变了 —— open.bigmodel.cn 的免费档会 429 限流"


def test_the_truth_source_is_labelled_honestly():
    """★★ 产物必须标跨家族模型共识, **不得**标人工裁定。"""
    pre = _j(PRE)
    t = json.dumps(pre, ensure_ascii=False)
    assert "cross_family_model_consensus" in t
    assert "不得" in t and "human-adjudicated" in t
    assert "不得**在未经 owner 确认前替换" in t or "不得在未经 owner 确认前替换" in t, \
        "★ 「未经确认不得替换 anchors.json」这条不见了"
    src = PROBE.read_text(encoding="utf-8")
    assert "不是** human-adjudicated" in src or "不是 human-adjudicated" in src


def test_the_shared_prior_limit_is_recorded():
    """★ 两个标注者同属 GLM 家族 —— 这个限度不能省。"""
    t = json.dumps(_j(PRE), ensure_ascii=False)
    assert "同属" in t and "GLM 家族" in t
    assert "共享" in t and "先验" in t, "★ 「共享先验查不出来」这条不见了"


def test_i_recorded_that_my_earlier_impossibility_claim_was_wrong():
    """★★★ 我说过「结构上做不成」, 那是基于一个错的前提 —— 必须留档。"""
    t = _j(PRE)["★★what_changed_since_i_said_it_was_impossible"]
    assert "结构上做不成" in t and "那个前提是错的" in t
    assert "open.bigmodel.cn" in t and "api.z.ai" in t, "★ 探错端点这件事不见了"
    assert "2026-07-21" in t, "★ 「库里早就记着」这条不见了 —— 它是这次失误的根因"


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    pre = saved(PRE)
    bad = copy.deepcopy(pre)
    bad["★positive_control_first"]["★★the_limits_of_this_evidence"] = "GLM 可靠。"
    g["_j"] = lambda p: bad if p == PRE else saved(p)
    try:
        test_the_evidence_strength_is_stated_not_just_the_hit_rate()
        raise SystemExit("★ 反向验证失败: 抹掉限度后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(pre)
    bad2["★★what_changed_since_i_said_it_was_impossible"] = "锚例扩充现已可行。"
    g["_j"] = lambda p: bad2 if p == PRE else saved(p)
    try:
        test_i_recorded_that_my_earlier_impossibility_claim_was_wrong()
        raise SystemExit("★ 反向验证失败: 抹掉「我判断错了」后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_the_evidence_strength_is_stated_not_just_the_hit_rate()
    test_the_positive_control_really_passed()
    test_the_two_operational_traps_are_pinned()
    test_the_truth_source_is_labelled_honestly()
    test_the_shared_prior_limit_is_recorded()
    test_i_recorded_that_my_earlier_impossibility_claim_was_wrong()
    n = _reverse_checks()
    lo, hi = _wilson(9, 9)
    print(f"test_cce_glm_cross_family: OK ("
          f"阳性对照 glm-4.5-flash **5/5** · glm-4.7-flash **4/4**(失败项全是预算打满) | "
          f"★★★但 9/9 的 Wilson 下界只有 **{lo:.4f}** —— 排除不了真实准确率低到 70% | "
          f"边界样本未验 · 两标注者**同属 GLM 家族**(共享先验查不出来) | "
          f"产物标 cross_family_model_consensus, **不得**标人工裁定, 未经确认不得替换 anchors.json | "
          f"两个坑已钉(推理模型需 max_tokens>=6000 · 必须串行 · 端点 api.z.ai) | "
          f"★我「结构上做不成」的判断错了, 已留档 | "
          f"{'原始对照已比对' if HAVE_PC else '★**无本机素材, 未比对原始对照记录**'} | "
          f"{n} 条反向验证判红)")
