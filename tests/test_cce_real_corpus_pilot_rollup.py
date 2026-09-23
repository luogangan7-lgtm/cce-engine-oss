# -*- coding: utf-8 -*-
"""跨轮汇总的闸。现算整份逐键比对。

★★★ 它守两句最容易被说错的话:
  ① 83% 是**交卷率**, 不是「可用产出率」—— 过机械资格层的只有 12/42
  ② **不得**拿 PASS_MECHANICAL 去收紧鉴别格的代价下界(那会低估代价)
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/real_corpus_pilot_rollup.py"
R = ROOT / "results/real_corpus_pilot_rollup.json"
R1 = ROOT / "results/real_corpus_pilot.json"
R2 = ROOT / "results/real_corpus_pilot_r2.json"


def _mod():
    s = importlib.util.spec_from_file_location("_ru", P)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def test_整份必须与build现算逐键一致():
    r = _r()
    if not r:
        return
    got = _mod().build(json.loads(R1.read_text(encoding="utf-8")),
                       json.loads(R2.read_text(encoding="utf-8")))
    for k in got:
        assert got[k] == r[k], "★★★ %s 与现算不符\n  档案 %r\n  现算 %r" % (k, r[k], got[k])


def test_复现结论必须由第二轮的判决支撑():
    r = _r()
    if not r:
        return
    v = _k(r, "一、第一轮的判决复现了")
    d2 = json.loads(R2.read_text(encoding="utf-8"))
    assert v["判决"] == [d2[x] for x in d2 if "主判据" in x][0]["★★★判决"]
    if v["判决"] == "CONFIRMED":
        assert "可以引用" in v["★意味着"] and "不再是单次读数" in v["★意味着"]
    # ★ kappa 不是 1 这件事必须写明
    k = [x for x in v if x.startswith("★★★但 kappa 只有")][0]
    assert "随机撞上的" in v[k] and "仍有真实的不确定性" in v[k], (
        "★★★ kappa 0.59 被读成了「完全稳」")


def test_交卷不等于合格必须带两个数与倍数():
    r = _r()
    if not r:
        return
    v = _k(r, "真正的新发现")
    d2 = json.loads(R2.read_text(encoding="utf-8"))
    Q = [d2[x] for x in d2 if "资格层" in x][0]["出口分布"]
    assert v["机械出口分布"] == Q, "★ 出口分布与第二轮产物不符"
    n2 = int(v["交卷"].split("/")[1].split(" ")[0])
    npass = Q["PASS_MECHANICAL"]
    assert v["过机械资格层"].startswith("%d/%d" % (npass, n2))
    key = [x for x in r if "真正的新发现" in x][0]
    assert "%.1f 倍" % (int(v["交卷"].split("/")[0]) / npass) in key, "★ 标题里的倍数与现算不符"
    fix = _k(v, "这对第一轮那个 83% 的修正")
    assert "不是「可用产出率」" in fix, "★★★ 必须写明 83% 不是可用产出率"
    assert "没错" in fix, "★ 不许把第一轮说成错的 —— 它测的就是交卷率"


def test_不许拿合格数去收紧鉴别格的代价下界():
    """★★★ 这是最容易犯的一步: 「鉴别格 ≤ 合格证书」听起来对, 实际是错的。"""
    r = _r()
    if not r:
        return
    C = _k(r, "三、代价下界")
    v = _k(C, "不得用 PASS_MECHANICAL 去收紧")
    assert "那是错的" in v and "照样可以被人标注" in v, (
        "★★★ 必须说清为什么不能收紧 —— 否则下一个人会顺手写出那个低估的界")
    assert "低估" in v
    # ★ 能用的那条必须真的只用交卷率
    d2 = json.loads(R2.read_text(encoding="utf-8"))
    M = [d2[x] for x in d2 if "主判据" in x][0]
    k2, n2 = (int(x) for x in M["第二轮"].split(" = ")[0].split("/"))
    _, hi = _mod().cp(k2, n2)
    assert "%.0f 次" % (24 / hi) in _k(C, "能用(纯下界, 只用交卷率)")
    assert "仍不是界" in [x for x in C if "借手构因子二" in x][0]


def test_仍然没回答的必须逐条列且点名零证据():
    r = _r()
    if not r:
        return
    v = " ".join(_k(r, "四、仍然没有回答的"))
    for w in ("因子二", "金标", "零证据", "机制未识别", "上界"):
        assert w in v, "★ 缺 %r" % w
    assert "两轮之后仍然零证据" in v, (
        "★★★ 必须写明跑了两轮、花了 84 次之后, 「验证器守得住」那句话仍然零证据")


def test_预算必须与两份产物现算一致():
    r = _r()
    if not r:
        return
    b = r["★预算"]
    d1 = json.loads(R1.read_text(encoding="utf-8")); d2 = json.loads(R2.read_text(encoding="utf-8"))
    assert b["第一轮"] == d1["★实际执行数"] and b["第二轮"] == d2["★实际执行数"]
    assert b["两轮合计"] == b["第一轮"] + b["第二轮"]
    assert b["累计"] == b["之前已用"] + b["两轮合计"] == 242


def test_零调用且不改源产物():
    import ast, hashlib
    r = _r()
    if not r:
        return
    assert "不改它们" in r["★零调用"]
    tree = ast.parse(P.read_text(encoding="utf-8"))
    src = P.read_text(encoding="utf-8")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm not in {"call_model", "urlopen", "_load_key", "post"}, "★ 真实调用"
            if nm in ("write_text", "unlink", "write_bytes"):
                seg = ast.get_source_segment(src, node) or ""
                assert "OUT" in seg, "★★★ 在写源产物: %s" % seg[:60]
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])
            for mod in mods:
                assert mod.split(".")[0] not in {"requests", "urllib", "http", "exp_crossmodel_desire"}


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
    print("跨轮汇总闸 %d 项全过" % n)
