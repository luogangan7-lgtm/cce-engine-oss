# -*- coding: utf-8 -*-
"""r2 设计的**机械自检**。覆盖 r1 那两个协议层错误各自的反面。

★★★ 覆盖什么: 档案自身是否守它要求模型守的逐字协议 · 对照臂是否**可达** ·
     阴性臂是否与 r1 **逐字节相同** · 被改易的是否**只有**对照臂 ·
     缺P阴性是否**存在**共享对象名(否则它通不过就不能归因于语义)。
★★★ **不**覆盖: 16 条推导对不对。逐字核对验不了语义关系(2026-09-13 零调用反例已证)。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R1 = ROOT / "tests/data/extractor_counterexample_templates.json"
R2 = ROOT / "tests/data/extractor_counterexample_templates_r2.json"
P2 = ROOT / "tests/data/extractor_counterexample_prereg_r2.json"
ARMS = {"正证据对照": 4, "缺P阴性": 4, "否定Q阴性": 4, "对象错配阴性": 4}
ABOUT_KEYS = ("about", "about_P", "about_Q", "★可共享的逐字对象名")


def _t(p):
    return json.loads(p.read_text(encoding="utf-8"))["templates"]


def test_档案自身也守逐字协议():
    """r2 要求模型的 about 逐字, 档案自己的 about 标注**不许例外**。
    (r1 档案写过「Mine (a much older pair)」这种带说明的形式 —— 自己违反自己的协议。)"""
    bad = [(t["id"], k, t[k]) for t in _t(R2) for k in ABOUT_KEYS
           if t.get(k) and t[k] not in t["text"]]
    assert not bad, "★★★ 这些 about 标注不是原文逐字片段: %r" % bad


def test_对照臂可达_共享对象名同时落在两支片段内():
    """r1 的死因: 对照因偶然原因全败 ⇒ 整轮读不出东西。
    对照的职责是证明这条路走得通, 所以它必须**结构上可达**。"""
    for t in _t(R2):
        if t["arm"] != "正证据对照":
            continue
        n = t["★可共享的逐字对象名"]
        assert n in t["span_P"], "★ %s 共享名 %r 不在 P 半片段内 ⇒ 对照可能再次因偶然原因失败" % (t["id"], n)
        assert n in t["span_Q"], "★ %s 共享名 %r 不在 Q 半片段内" % (t["id"], n)


def test_缺P阴性存在共享对象名():
    """★★★ 这一臂是本轮**真正承重**的阴性臂: 共享对象名**确实存在**,
    所以它通不过**只能**靠 P 的五类判断, 不能靠对象绑定顺手拦下。
    若这里也没有共享名, 那这一臂的 Z=0 就和 r1 一样没有语义含量。"""
    for t in _t(R2):
        if t["arm"] != "缺P阴性":
            continue
        n = t["about"]
        assert n in t["text"] and n in t["span_Q"], (
            "★ %s 的 about %r 不在 Q 片段里 ⇒ 这一臂会退化成对象绑定检查" % (t["id"], n))


def test_对象错配臂两个对象不重合():
    for t in _t(R2):
        if t["arm"] != "对象错配阴性":
            continue
        a, b = t["about_P"], t["about_Q"]
        assert a != b, "★ %s 两个对象声明成同一个了" % t["id"]
        assert a not in t["span_Q"] and b not in t["span_P"], (
            "★ %s 两个对象名交叉落入了对方片段 ⇒ 该格不干净" % t["id"])


def test_阴性臂与r1逐字节相同_对照臂才是被改易的():
    """★★★ r1↔r2 可比性的依据就在这里, 但它**已被主动削弱过一次**且记了账:
    对照 4 条从零重写, 阴性 **9/12 逐字不变**, 另 3 条被改且理由各自具名:
      NEGP-3 / MIS-4 —— 消除过度决定(设问句在「无质询句」宽读法下抢先决定了阴性性质)
      MIS-1          —— 打破共线(「型号名出现两次」原本与臂身份完全共线)
    ★ 放弃「阴性全不变」的理由: r1 阴性**只有 1/12 交卷**, 资格层在 11 条上一次都没被调用
      ⇒ 根本没有可比之物; 留一个有缺陷的模板去换一个空的可比性, 不划算。"""
    a = {t["id"]: (t["arm"], t["text"]) for t in _t(R1)}
    b = {t["id"]: (t["arm"], t["text"]) for t in _t(R2)}
    assert set(a) == set(b), "★ r1/r2 的用例集合不同, 可比性无从谈起"
    changed = sorted(k for k in a if a[k][1] != b[k][1])
    unchanged = sorted(k for k in a if a[k][1] == b[k][1])
    assert all(b[k][0] == "正证据对照" for k in changed
               if k not in ("MIS-1", "MIS-4", "NEGP-3")), (
        "★★★ 除登记在册的那三条以外, 被改的不该有阴性: %r"
        % [k for k in changed if b[k][0] != "正证据对照"
           and k not in ("MIS-1", "MIS-4", "NEGP-3")])
    assert all(b[k][0] != "正证据对照" for k in unchanged), (
        "★ 有对照臂没被改易: %r —— 那一条仍带着 r1 的可达性风险"
        % [k for k in unchanged if b[k][0] == "正证据对照"])
    # ★★★ 2026-09-14 设计评审后放弃了「阴性全部逐字不变」: NEGP-3 与 MIS-4 带设问句,
    #   在「无质询句」的**宽读法**下该格已被过度决定 ⇒ 测不到它声称要测的机制。
    #   代价与理由已写进档案; 其余 10 条阴性仍逐字不变。
    neg_changed = sorted(k for k in changed if b[k][0] != "正证据对照")
    assert neg_changed == ["MIS-1", "MIS-4", "NEGP-3"], (
        "★★★ 被改的阴性集合变了: %r —— 每多改一条, 「与 r1 可比」就更弱一分, "
        "理由由 test_改了的阴性必须具名一条冻结枚举里的理由 逐条核" % neg_changed)
    assert len(changed) == 7 and len(unchanged) == 9


# ★★★ 改阴性**允许的理由**是一张冻结枚举表。每条被改的阴性必须具名其中之一,
#   且那个理由必须是**与本轮读数无关**的设计缺陷 —— 否则改阴性就是调结果。
NEG_CHANGE_REASONS = {
    "过度决定": "该格的阴性性质**被另一个条件抢先决定**, 测不到它声称要测的机制"
              "(NEGP-3 / MIS-4 的设问句: 「无质询句」宽读法下它们已因问句出局)",
    "打破共线": "某个**纯句法**特征与臂身份完全共线 ⇒ 一个不做语义判断的启发式能拿满分"
              "(「型号名出现两次」原本 4/4 对照 vs 0/12 阴性)",
}


def test_改了的阴性必须具名一条冻结枚举里的理由():
    changed = []
    for t in _t(R2):
        if t["arm"] == "正证据对照":
            continue
        why = t.get("★r2 改动", "")
        if why.startswith("**无"):
            continue
        hit = [k for k in NEG_CHANGE_REASONS if k in why]
        assert hit, (
            "★★★ %s 被改了, 但理由不在冻结枚举 %r 里 —— "
            "改阴性要付可比性代价, 理由必须是**与本轮读数无关**的设计缺陷, "
            "否则就是调结果" % (t["id"], sorted(NEG_CHANGE_REASONS)))
        changed.append((t["id"], hit[0]))
    assert sorted(changed) == [("MIS-1", "打破共线"), ("MIS-4", "过度决定"),
                               ("NEGP-3", "过度决定")], (
        "★★★ 被改的阴性集合变了: %r —— 每多改一条, 「与 r1 可比」就更弱一分, "
        "必须在这里显式登记" % sorted(changed))


def test_对照臂不许基于r1模型的作答改写():
    """★★★ 评审抓到的最狠一条: r2 初版对照 4/4 的编辑区间都落在 r1 模型
    **实际选中的 span** 内 —— 那是拿受试者上一轮的作答改考题。"""
    for t in _t(R2):
        if t["arm"] != "正证据对照":
            continue
        why = t.get("★r2 改动", "")
        assert "从零重写" in why and "不参照 r1 文本" in why, (
            "★ %s 的对照改动没声明它是从零重写的" % t["id"])


def test_对照臂两半限定词同形():
    """r1 实测 5/5 证书的 about 都带修饰 ⇒ 光有裸型号名不够, 两处语境要同形。"""
    for t in _t(R2):
        if t["arm"] != "正证据对照":
            continue
        n = t["★可共享的逐字对象名"]
        tx = t["text"]
        dets = []
        i = tx.find(n)
        while i >= 0:
            dets.append(tx[max(0, i - 4):i].lower())
            i = tx.find(n, i + 1)
        assert len(set(dets)) == 1, (
            "★★★ %s 型号名两处左语境不同 %r ⇒ 模型自然切出的 about 字节不等, "
            "P2 会以无关原因拦下(r1 的死法)" % (t["id"], dets))


def test_四格条数与结构互异():
    T = _t(R2)
    got = {}
    for t in T:
        got[t["arm"]] = got.get(t["arm"], 0) + 1
    assert got == ARMS, "★四格条数不符: %r" % got
    for arm in ARMS:
        ss = [t["结构"] for t in T if t["arm"] == arm]
        assert len(set(ss)) == len(ss), "★%s 内有重复的表述结构 %r" % (arm, ss)


def test_每条声明的片段都逐字在文本里():
    for t in _t(R2):
        for k in ("span_P", "span_Q", "span_negQ"):
            s = t.get(k)
            if s is not None:
                assert s in t["text"], "★%s.%s 非逐字: %r" % (t["id"], k, s)


def test_预注册把已知局限写在测量之前():
    """★ 逐字要求可能**暗示**模型去找共享名字 ⇒ 对象错配臂的干净通过不算强证据。
    这条局限必须在测量前写下, 否则事后补写就是为结果找说法。"""
    d = json.loads(P2.read_text(encoding="utf-8"))
    lim = json.dumps(d["★★★协议变更(唯一的实质变更)"], ensure_ascii=False)
    assert "暗示" in lim and "对象错配" in lim, "★ 已知局限没写在协议变更里"
    assert "缺P阴性" in lim, "★ 没指明哪一臂是真正承重的阴性臂"
    nots = json.dumps(d["★★★不得据此说"], ensure_ascii=False)
    assert "观测通道" in nots, "★ 没钉住「r1↔r2 差异是观测通道变化, 不是模型行为变化」"


def test_r2不许重用r1的预算():
    d = json.loads(P2.read_text(encoding="utf-8"))
    assert d["执行"]["★请求硬上限"] == 16 and d["执行"]["★自动重试"] == 0
    assert "已用尽且不可挪用" in d["执行"]["★★★与 r1 的预算关系"]


def test_第二次退化不许再改协议重跑():
    d = json.loads(P2.read_text(encoding="utf-8"))
    k = [x for x in d["★★★决策规则(测量前冻结)"] if "第二次 DEGENERATE" in x]
    assert k, "★ 没写「若 r2 再次退化怎么办」—— 那会变成无限调参"
    v = d["★★★决策规则(测量前冻结)"][k[0]]
    assert "不得" in v and "结论" in v


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r2 设计自检 %d 项全过 —— ★但它没验过任何一条推导" % n)
