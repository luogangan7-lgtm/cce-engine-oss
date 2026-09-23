# -*- coding: utf-8 -*-
"""对照集体检器的闸。

★★★ 它守的是一条**方法论**: 手构对照集在每条已知特征轴上的 pos/neg 分布差,
  **不应明显大于真实语料**在同一条轴上的差。
  2026-09-15 一天之内手构集连续三轮冒出新共线(句法 → 量词/时段 → 词数),
  每次都是**事后搜出来才发现**。这个体检器把它变成造对照时的机械约束。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/corpus_balance_audit.py"
R = ROOT / "results/corpus_balance_audit.json"


def _m():
    s = importlib.util.spec_from_file_location("cba", P)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def test_产物由探针现算_不许手写():
    r = _r()
    if not r:
        return
    live = _m().build_result()
    assert set(r) == set(live), "★★★ 键集不符"
    diff = [k for k in live if r[k] != live[k]]
    assert not diff, "★★★ 与现算不符(档案手写, 或探针改了没重跑): %r" % diff


def test_没有任何已知轴超出真实语料():
    """★★★ 这是投料的**硬前置**。2026-09-15 评审实测: 量词/时段轴超出时,
    一条族外零语义正则拿 19/24 并穿过全部三个前置条件。"""
    r = _r()
    if not r:
        return
    over = r["★★★超出真实语料的轴"]
    assert over == "无", (
        "★★★ 这些轴超出真实语料: %r —— 手构集在它们上面与目标信号共线, "
        "族外浅层规则会从那里穿过去" % over)


def test_判准不是差为0_且写明了为什么():
    r = _r()
    if not r:
        return
    assert "语义差异**必然**伴随某种表层差异" in r["★★★判准不是差为 0"], (
        "★ 必须写明追求差为 0 是不可能的 —— 否则下一个人会无限迭代")
    assert "不应明显大于真实语料" in r["★★★判准不是差为 0"]


def test_参照的分母极小这件事必须写明():
    r = _r()
    if not r:
        return
    v = r["★★★参照的分母极小"]
    assert "不当阈值" in v and "只用来判" in v, (
        "★★★ 真实侧 RESTATES 只有 2 条 —— 不写明就会被当成精确阈值")


def test_必须写明永远盖不全():
    r = _r()
    if not r:
        return
    v = r["★★★永远盖不全"]
    assert "留出集" in v and "外部锚点" in v, (
        "★★★ 已知轴之外的共线只能靠留出集与外部锚点管 —— "
        "把体检器写成「全覆盖」就是第 N 次假保证")


def test_量词时段那三条轴必须在轴表里():
    """★ 它们是 2026-09-15 评审抓到的那条 BLOCKING 的直接来源, 不许被删。"""
    ax = set(_m().axes())
    for must in ("含量词或数字", "含时段单位", "含量词或时段"):
        assert must in ax, "★★★ 轴 %r 被删了 —— 那正是族外规则穿过去的那条" % must


def test_probe零调用():
    src = P.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 体检器里出现模型调用入口 %r" % bad

# ───────── 第二个参照: 真实 Reddit 语料 ─────────

def test_第二个参照必须在_且说清它回答的是另一个问题():
    """★★★ 真实证书(9 条, 有标注)比**类别间的差**; 真实语料(493 句, 无标注)比**句子本身像不像真人写的**。
    两者**互补不是替代** —— 类别差合格但句子根本不像真人写的, 仍然是个问题。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "第二个参照" in x][0]
    c = r[k]
    assert "互补不是替代" in c["★它回答的是另一个问题"], "★ 必须写明两个参照回答不同问题"
    assert "类别间的差" in c["★它回答的是另一个问题"] and "像不像真人写的" in c["★它回答的是另一个问题"]


def test_偏离量必须报出来_不许只报布尔():
    """★★★ 布尔阈值(40 点)只抓极端偏离。真正该报的是**偏离量本身** ——
    实测有四条轴偏离 19–30 个百分点, 布尔全是 False。"""
    r = _r()
    if not r:
        return
    c = r[[x for x in r if "第二个参照" in x][0]]
    w = c["★★★偏离最大的四条轴(百分点)"]
    assert len(w) >= 3 and all(isinstance(v, int) for v in w.values()), "★ 偏离量要报具体数"
    m = c["★★★这几条偏离意味着什么"]
    assert "内部效度不受影响" in m, "★ 必须说清同向偏离不影响类别区分"
    assert "不得外推到自然语料" in m, (
        "★★★ 必须写明这几条偏离**影响外推** —— 这条以前只是口头边界, 现在有数了")
    assert "为什么不把阈值调到 20 点" in json.dumps(c, ensure_ascii=False), (
        "★★★ 必须写明**不在看过数字之后调阈值** —— 那会变成拟合当前对照集")
    # ★★★ 上一行只守「有没有写这句话」。变异实测(Q4b)证明: 把阈值真的改掉,
    #   那句话还在 ⇒ 闸不响。⇒ **直接断言阈值本身**。「断言太弱」同型又一次。
    assert _m().FAR_THRESHOLD == 0.4, (
        "★★★ 阈值被改成 %s —— 它是**在看过偏离量之前**定的 0.4, 改它就是拟合当前对照集。"
        "要看细粒度请读**偏离量本身**(已现算并报出)。" % _m().FAR_THRESHOLD)


def test_语料原文不许进产物():
    """★★★ 语料是**外部真人内容**(已去标识)。产物里只放统计量。"""
    r = _r()
    if not r:
        return
    body = json.dumps(r, ensure_ascii=False)
    m = _m()
    sents = m._corpus_sents()
    assert sents, "★ 语料读不到"
    leaked = [x for x in sents if len(x) > 30 and x[:30] in body]
    assert not leaked, "★★★ 产物里出现了语料原文(%d 条) —— 只许放统计量" % len(leaked)
    c = r[[x for x in r if "第二个参照" in x][0]]
    assert "一个字的原文都不写进去" in c["★★★边界_这是外部真人内容"]


def test_语料规模必须够大_否则参照没意义():
    m = _m()
    sents = m._corpus_sents()
    assert len(sents) >= 300, (
        "★★★ 真实语料只有 %d 句 —— 太少就和真实证书那 9 条一样是弱参照" % len(sents))
    brand = [x for x in sents if m.BRANDS.search(x)]
    assert len(brand) >= 30, (
        "★ 含具体品牌/型号的只有 %d 句 —— 手构集全都含品牌, 可比的是这一子集" % len(brand))


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("对照集体检闸 %d 项全过" % n)
