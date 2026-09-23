# -*- coding: utf-8 -*-
"""形式质量读数的闸。现算整份产物逐键比对。

★★★ 它守的核心是一句话: **交卷 ≠ 合格**。
    主读数 83% 很容易被读成「83% 的段落真的满足判别式」——
    而手构那边 10 张交卷证书里 6 张是**在阴性上错误升格**。
"""
import importlib.util, json, pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/real_corpus_pilot_formal_quality.py"
R = ROOT / "results/real_corpus_pilot_formal_quality.json"
SRC = ROOT / "results/real_corpus_pilot.json"


def _mod():
    s = importlib.util.spec_from_file_location("_fq", P)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def test_整份必须与build现算逐键一致():
    """★ 灵敏度: 改了源产物或计算却不重跑 ⇒ 红。"""
    r = _r()
    if not r or not SRC.exists():
        return
    m = _mod()
    res = json.loads(SRC.read_text(encoding="utf-8"))
    s2 = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py")
    r2 = importlib.util.module_from_spec(s2); s2.loader.exec_module(r2)
    hand = {}
    for rel in m.HAND:
        rows = json.loads((ROOT / rel).read_text(encoding="utf-8"))["rows"]
        iss = [x for x in rows if x.get("调用成功") and x.get("outcome") in r2.ISSUED]
        hand[rel.split("/")[-1]] = dict(sorted(Counter(x["outcome"] for x in iss).items()))
    got = m.build(res, hand)
    for k in got:
        assert got[k] == r[k], "★★★ %s 与现算不符\n  档案 %r\n  现算 %r" % (k, r[k], got[k])


def test_交卷不等于合格这句必须站得住():
    """★★★ 这是本文件的全部价值。它必须由**手构那边的实际 outcome** 支撑, 不是口号。"""
    r = _r()
    if not r:
        return
    v = r["★★★ 交卷 ≠ 合格"]
    hand = v["★手构那边的交卷证书是什么下场"]
    up = sum(x.get("UPGRADED", 0) for x in hand.values())
    tot = sum(sum(x.values()) for x in hand.values())
    assert up >= 1, "★★★ 若手构那边一张 UPGRADED 都没有, 「交卷≠合格」这句就没有证据了"
    assert "%d 张交卷证书里 **%d 张是 UPGRADED**" % (tot, up) in v["★★★所以 83% 不能读成「83% 的段落真的满足判别式」"]
    assert "本轮分不开这两种" in v["★★★所以 83% 不能读成「83% 的段落真的满足判别式」"], (
        "★★★ 必须写明两种解释分不开 —— 否则会被读成「抽取器更松」或「真实语料更合规」之一")


def test_形式不过关的那几张必须点出来():
    r = _r()
    if not r or not SRC.exists():
        return
    res = json.loads(SRC.read_text(encoding="utf-8"))
    sub = [x for x in res["rows"] if x["调用成功"] and x["交卷"] is True]
    allv = sum(1 for x in sub if x["span_逐字"] and all(x["span_逐字"]))
    f = r["★ 形式质量(无金标, 只看结构)"]
    assert f["★★★整张证书 span 全逐字"] == "%d/%d" % (allv, len(sub)), "★ 与现算不符"
    k = [x for x in f if x.startswith("★那 ") and "张的含义" in x][0]
    assert "MALFORMED" in f[k] and "连形式都不过" in f[k], (
        "★ 必须说清那几张在资格层就会被拦")
    assert int(k.split("★那 ")[1].split(" 张")[0]) == len(sub) - allv, "★ 标题里的数与现算不符"


def test_必须承认资格层被我自己的隐私选择挡住了():
    """★★★ 这是设计代价, 不是遗漏 —— 必须写明, 否则下一轮会重蹈。"""
    r = _r()
    if not r:
        return
    v = r["★这条限制是我自己的设计造成的"]
    assert "没存 object" in v and "无法重算资格层" in v
    assert "sha" in v, "★ 必须给出下一轮的可行办法, 不能只说做不到"
    nq = [r[x] for x in r if "本文件不回答" in x][0]
    assert any("资格层" in x and "隐私" in x for x in nq)


def test_零调用():
    r = _r()
    if not r:
        return
    assert "不发起任何调用" in r["★零调用"]
    import ast
    tree = ast.parse(P.read_text(encoding="utf-8"))
    BAD = {"call_model", "urlopen", "_load_key", "post"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm not in BAD, "★ 出现真实调用 %r" % nm
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])
            for mod in mods:
                assert mod.split(".")[0] not in {"requests", "urllib", "http", "exp_crossmodel_desire"}, (
                    "★ 导入了联网模块 %r" % mod)


def test_不许有一个字语料原文():
    r = _r()
    if not r:
        return
    blob = json.dumps(r, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25:
                assert l.strip()[:25] not in blob, "★★★ 出现语料原文"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("形式质量闸 %d 项全过" % n)
