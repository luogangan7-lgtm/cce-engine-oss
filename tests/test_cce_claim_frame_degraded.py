# -*- coding: utf-8 -*-
"""「判据层要不要接入生产」这个判断的闸。

★★★ 答案是**不接入**, 而且理由必须**三条都在**:
  (a) 塞进 prompt —— gen9 实测已排除
  (b) 让模型自动填槽位 —— r5 实测没有证据支持
  (c) 填不出的留空 —— 本轮实测对照全误拦
★★ 同时必须守住一个区分: **判据层本身是有效的**, 问题**不在判据, 在没有可靠的方法把槽位填对**。
   把这两件事混为一谈, 下一个人会去改判据(改不动)而不是去解决填槽位(真问题)。
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/claim_frame_degraded_capacity.py"
R = ROOT / "results/claim_frame_degraded_capacity.json"


def _m():
    s = importlib.util.spec_from_file_location("cfd", P)
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
    assert not diff, "★★★ 与现算不符: %r" % diff


def test_降级方案的失败必须由数字给出():
    """★ 「留空 ⇒ 全拦」在逻辑上显然, 但**算出来才是证据**。"""
    r = _r()
    if not r:
        return
    blk = r["手构最小对照(34 对 × 2 版)"]
    deg = [v for k, v in blk.items() if k.startswith("②")][0]
    full = [v for k, v in blk.items() if k.startswith("①")][0]
    a, b = (int(x) for x in deg["明文+解释"]["对照通过"].split("/"))
    assert a == 0, "★★★ 降级后对照居然没被全拦(%d/%d) —— 那结论要重写" % (a, b)
    fa, fb = (int(x) for x in full["明文+解释"]["对照通过"].split("/"))
    assert fa == fb, "★★★ **全槽位**时对照必须全通过, 否则判据层本身就有问题: %d/%d" % (fa, fb)


def test_三条路的证据必须都在_且各带数字():
    r = _r()
    if not r:
        return
    v = r["★★★两条被挡住的路"]
    a = [x for x in v if x.startswith("(a)")][0]
    assert "1/80" in v[a] and "40/80" in v[a] and "倒挂" in v[a], (
        "★★★ (a) 必须带 gen9 的实测数(生产臂 1/80 → 候选臂 40/80 且倒挂)")
    b = [x for x in v if x.startswith("(b)")][0]
    assert "12%" in v[b] and "−6" in v[b], "★★★ (b) 必须带 r5 的实测数"
    ans = r["★★★所以现在的答案是"]
    assert ans.startswith("**不接入。**"), "★ 答案必须先写结论"
    for must in ("(a)", "(b)", "(c)"):
        assert must in ans, "★ 答案里缺 %s 这条路" % must


def test_必须守住判据本身有效与填不出槽位的区分():
    """★★★ 混为一谈 ⇒ 下一个人会去改判据(改不动), 而不是去解决填槽位(真问题)。"""
    r = _r()
    if not r:
        return
    ans = r["★★★所以现在的答案是"]
    assert "判据层**本身是有效的**" in ans, "★★★ 必须写明判据本身没问题"
    assert "不在判据, 在没有可靠的方法把槽位填对" in ans, (
        "★★★ 必须点名真问题是**填槽位**而不是判据")


def test_我写错的那份replay实现必须留档():
    """★★★ 2026-09-15: 我先写了一份自己的回放实现, 读出「对照 0/12」,
    而仓里已验证的那份读出 **12/12** ⇒ 我那份是错的。
    ★ 处理是**撤掉**不是「修好」—— 已有验证过的实现, 两份并存会让下一个人不知道信哪个。
    ★★ 但**撤掉这件事本身必须留档**, 否则下一个人会再写一遍。"""
    src = P.read_text(encoding="utf-8")
    assert "不自己重新实现回放" in src, "★ 源码里那条纪律没了"
    assert "对照通过 0/12" in src and "12/12" in src, (
        "★★★ 必须写明**两份实现读出的数不一样**, 以及哪一份是对的")
    assert "撤掉我那份" in src and "不是「修好它」" in src, "★ 必须写明处理方式"
    # ★★★ 2026-09-16: 欠账已补 —— 给**已验证的** claim_frame_replay.py 加 drop 参数,
    #   而**不是**再写一份自己的实现。这条断言随之从「必须写明没算」改成「必须用那份算」。
    assert "**不是**再写一份自己的实现" in src, (
        "★★★ 补欠账的做法必须是**给已验证探针加参数**, 不是重写")
    assert "m.build_rows(drop=drop)" in src, "★ 必须真的调用已验证探针的 build_rows"


def test_已验证探针的历史读数不许因为加了drop而改变():
    """★★★ 给 claim_frame_replay.py 加 drop 参数时, **默认必须是 ()**,
    否则它自己的历史读数(results/claim_frame_replay.json, 7 道闸在守)会被悄悄改掉。"""
    src = (ROOT / "probes/claim_frame_replay.py").read_text(encoding="utf-8")
    assert "def build_rows(drop=()):" in src, "★★★ drop 必须默认为空元组"
    assert "默认 drop=() ⇒ 现有读数逐字不变" in src, "★ 源码里要写明这条"
    hist = json.loads((ROOT / "results/claim_frame_replay.json").read_text(encoding="utf-8"))
    assert hist["★★★对照_会不会误拦"]["明文+解释"]["正常放行"] == "12/12", (
        "★★★ 已验证探针的历史读数变了 —— 加 drop 参数不该动它")


def test_真实证书上的降级也必须算出来_且与手构一致():
    """★★★ 2026-09-16 补上的欠账。两批数据结论一致, 才说明「留空 ⇒ 全误拦」
    **不是手构对照的特性**。"""
    r = _r()
    if not r:
        return
    rb = r["真实证书回放(r1/r2/r3 已付费的 48 次)"]
    full = [v for k, v in rb.items() if k.startswith("①")][0]["明文+解释"]
    deg = [v for k, v in rb.items() if k.startswith("②")][0]["明文+解释"]
    fa, fb = (int(x) for x in full["对照通过"].split("/"))
    assert fa == fb and fb > 0, (
        "★★★ **全槽位**时真实证书的对照必须全通过(现 %s) —— "
        "这也是我上一轮那份错实现被识破的地方(它给 0/12)" % full["对照通过"])
    da, _ = (int(x) for x in deg["对照通过"].split("/"))
    assert da == 0, "★★★ 降级后真实证书的对照居然没被全拦(%s) ⇒ 结论要重写" % deg["对照通过"]
    v = r["★★★真实证书上也一样吗"]
    assert "不是手构对照的特性" in v, "★ 必须点明两批数据一致意味着什么"
    assert "分母小" in v and "只判方向" in v, (
        "★★★ 真实证书对照只有 12 张, 必须写明分母小")


def test_关键数字不许在docstring里复述():
    """★★★ 2026-09-15 变异实测踩到的: 同一个数写在 docstring 与产物两处,
    改了 docstring 那处**没有任何闸会红**(它不进产物), 文档就此与读数不一致。
    ⇒ 通则: **一个数只写在一个地方 —— 现算的那个**。"""
    src = P.read_text(encoding="utf-8")
    doc = src[src.index('"""'):src.index('"""', src.index('"""') + 3)]
    for num in ("1/80", "40/80", "12%", "−6", "56%", "41%"):
        assert num not in doc, (
            "★★★ docstring 里复述了具体读数 %r —— 它不进产物, 改错了没有闸会红。"
            "把它挪进 build_result(现算), docstring 只指过去。" % num)
    assert "一个数只写在一个地方" in src, "★ 那条通则要留在源码里"


def test_probe零调用():
    src = P.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 出现模型调用入口 %r" % bad


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("判据层接入判断闸 %d 项全过" % n)
