# -*- coding: utf-8 -*-
"""三项同尺汇总的闸。

★★★ 这份汇总的**唯一价值**是那把尺 —— 三个不同的问题换算成同一个数。
    尺被换掉 / 三项之一被偷偷改成非零 / 「不做裁定」被删 ⇒ 必须见红。
★★★ 闸**现算**三个数, 不读档案里的那三个 —— 否则源产物变了闸还是绿的
    (2026-09-17 刚因为这个毛病修过一次)。
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/three_decisions_rollup.py"
R = ROOT / "results/three_decisions_rollup.json"


def _mod():
    s = importlib.util.spec_from_file_location("_rollup", P)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _live():
    """★ 从**源产物**现算三个数 —— 不碰 rollup 的档案。"""
    m = _mod()
    D = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in m.SRC.items() if p.exists()}
    if len(D) != 3:
        return None
    ex = m._k(D["①"], "这两条规则在真实证书上被 exercise 了吗")
    g1 = m._k(ex, "citation == REPORTED 出现次数") + m._k(ex, "predicate == NOT_OF_DECLARED_KIND 出现次数")
    uniq = D["③"]["逐组不同输出数"]
    dgrp = [k for k in uniq if k.startswith("D")][0]
    return {"g1": g1, "uniq_D": uniq[dgrp], "n_D": D["③"]["逐组样本数"][dgrp]}


def test_三个数必须与源产物现算一致():
    """★★★ 灵敏度: 改了源产物却没重跑 rollup ⇒ 见红。"""
    r, live = _r(), _live()
    if not r or not live:
        return
    got = r["★★★★★ 三项同尺后的读数"]["逐项新增鉴别格"]
    assert got["①升合同"] == live["g1"], (
        "★ ①的新增鉴别格与源产物现算不符: 档案 %r vs 现算 %r —— 源产物变了, 重跑 rollup"
        % (got["①升合同"], live["g1"]))
    assert got["②换真实语料"] == 0 and got["③要确定性"] == 0
    assert r["★★★★★ 三项同尺后的读数"]["合计"] == sum(got.values()), "★ 合计与逐项不符"


def test_第三项的实测句必须与seed产物现算一致():
    r, live = _r(), _live()
    if not r or not live:
        return
    s = r["③"]["★实测"]
    assert "%d 次 → **%d 种不同输出**" % (live["n_D"], live["uniq_D"]) in s, (
        "★★★ ③的实测句与 seed 产物脱钩了: %r (现算 %d 次/%d 种)" % (s, live["n_D"], live["uniq_D"]))


def test_尺必须是净增益_不许换尺():
    """★★★ 换一把尺(比如「有没有道理」「值不值得」)就能让三个 0 变成三个不同的答案。
    尺被换掉 = 这份汇总失去全部价值。"""
    r = _r()
    if not r:
        return
    assert "净增益 = 鉴别格对数 − 多数类格错数" in r["★尺"], "★ 尺被换了: %r" % r["★尺"]
    assert "在真实证书上能新增几个鉴别格" in r["★尺"], "★ 必须写明三项换算成什么"


def test_结论必须是同一堵墙_而不是三个独立结论():
    """★★★ 这份东西的全部价值就在这一句: 三个不同的问题, 同一把尺上都是 0。"""
    r = _r()
    if not r:
        return
    c = r["★★★★★ 三项同尺后的读数"]["★★★这才是结论"]
    assert "三件不同的事" in c and "同一堵墙" in c, "★ 结论被削弱成三个独立结论了"
    assert "没有鉴别格" in c, "★ 必须点名那堵墙是什么"
    assert "50 次" in c and "小批试" in c, (
        "★★★ 必须写明下一件该做的事**不在这三项里** —— 否则读者会以为三项做完就没事了")


def test_每一项都要写明卡在效度还是可复现():
    """★★★ ③ 与 ①② 卡的**不是同一类问题**。混掉会让人以为「拿到 seed 就好了」。"""
    r = _r()
    if not r:
        return
    for k in ("①", "②"):
        assert "效度" in r[k]["★卡在哪"], "★ %s 必须写明卡在效度: %r" % (k, r[k]["★卡在哪"])
    w = r["③"]["★为什么是 0"]
    assert "可复现" in w and "效度" in w, "★ ③必须把两类问题分开"
    assert "即便 seed 明天就生效" in w, (
        "★★★ 必须写明**即便确定性解决了也不会多出一个格子** —— 这是最容易被误读的一条")


def test_第三项排除服务端变更必须留档且标明不得外推():
    r = _r()
    if not r:
        return
    k = [x for x in r if "但它换掉了一个此前的解释" in x][0]
    v = r[k]
    assert "不能单独归因于模型随机性" in v["r3 当时说什么"], "★ 必须写清 r3 原来的保留"
    assert "同一时刻并发" in v["本轮换掉了什么"] and "服务端变更这个解释被排除" in v["本轮换掉了什么"]
    assert "不可消除的下界" in v["★这对项目的含义"], "★ 必须写出它对项目的实际含义"
    assert "不得外推" in k or "不得外推" in json.dumps(v, ensure_ascii=False), "★ 必须标明不得外推"


def test_不做裁定这条纪律必须写明():
    """★ 附件 A 那次定死的纪律: 裁定依据是 owner 的决定, 不是读数。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "不做裁定" in x][0]
    assert "owner 的决定" in r[k], "★ 纪律被删了"


def test_零调用且不产生新数字():
    r = _r()
    if not r:
        return
    assert "不发起任何模型调用" in r["★零调用"] and "不产生任何新数字" in r["★零调用"]
    src = P.read_text(encoding="utf-8")
    for bad in ("call_model", "requests.post", "urlopen", "http"):
        assert bad not in src, "★ 探针里出现 %r —— 这应当是零调用的" % bad
    assert len(r["★来源"]) == 3, "★ 三个来源都要留档"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("三项同尺闸 %d 项全过" % n)
