# -*- coding: utf-8 -*-
"""第二轮(重测)预注册的闸。零调用, 每个数现算。"""
import hashlib, importlib.util, json, pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "tests/data/real_corpus_pilot_r2_prereg.json"
GEN = ROOT / "probes/real_corpus_pilot_r2_prereg.py"
RUN = ROOT / "probes/real_corpus_pilot_r2_run.py"
R1_PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
R1_RES = ROOT / "results/real_corpus_pilot.json"


def _pre():
    return json.loads(P.read_text(encoding="utf-8")) if P.exists() else None


def _gen():
    s = importlib.util.spec_from_file_location("_g2", GEN)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def test_重测的理由必须落在本仓已登记的教训上():
    """★★★ 不是「再跑一次看看」—— 是本仓自己的硬规矩要求的。"""
    pre = _pre()
    if not pre:
        return
    v = _k(pre, "为什么要跑第二轮")
    assert "单次运行读数不可信" in _k(v, "但它是单次读数")
    assert "翻了 6 条" in _k(v, "但它是单次读数"), "★ 必须给出 r3 那个实测锚"
    assert "temp=0 并不确定" in _k(v, "但它是单次读数"), "★ 必须带上 seed 探针那条"
    assert "已写进 manifest" in _k(v, "我已经拿它下了判决"), (
        "★★★ 必须写明我已经拿单次读数下了判决 —— 那才是这轮存在的理由")


def test_与第一轮相同的部分必须逐项钉sha且执行前重验():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._g1()._r2()
    same = _k(pre, "与第一轮**完全相同**的部分")
    assert same["第一轮预注册 sha256"] == hashlib.sha256(R1_PRE.read_bytes()).hexdigest()
    assert same["第一轮产物 sha256"] == hashlib.sha256(R1_RES.read_bytes()).hexdigest()
    assert same["PROMPT sha256"] == hashlib.sha256(m.PROMPT.encode()).hexdigest()
    assert same["判别式 sha256"] == hashlib.sha256(m.DISC.encode()).hexdigest()
    assert same["temperature"] == 0.0 and same["max_retries"] == 1
    p1 = json.loads(R1_PRE.read_text(encoding="utf-8"))
    assert same["items"] == [p1[x] for x in p1 if "冻结输入集" in x][0]["items"], (
        "★★★ 输入集与第一轮不同 ⇒ 不是重测")
    assert "只让时间变" in _k(same, "为什么必须逐字相同")
    src = RUN.read_text(encoding="utf-8")
    assert "def preflight2" in src and src.index("preflight2(pre, p1, m)") < src.index("for it, line in pairs")


def test_拒绝域必须继承第一轮的表_且逐键相同():
    """★★★ 新立一张表就是换判据。"""
    pre = _pre()
    if not pre:
        return
    J = _k(pre, "主判据(投料前定死)")
    table = _k(J, "第一轮拒绝域表(继承, 不重算)")
    p1 = json.loads(R1_PRE.read_text(encoding="utf-8"))
    J1 = [p1[x] for x in p1 if "主判据" in x][0]
    assert table == [J1[x] for x in J1 if "拒绝域按实际 n_ok 查表" in x][0], (
        "★★★ 与第一轮的表不同 ⇒ 判据被换过")
    assert _k(J, "第一轮最低可判 n_ok") == [J1[x] for x in J1 if "最低可判 n_ok" in x][0]
    assert "不新立判据, 不重新推导" in _k(J, "★判法")


def test_主判据功效必须现算一致_且承认它测不出小波动():
    pre = _pre()
    if not pre:
        return
    J = _k(pre, "主判据(投料前定死)")
    table = _k(J, "第一轮拒绝域表(继承, 不重算)")
    same = _k(pre, "与第一轮**完全相同**的部分")
    N = len(same["items"])
    hi = table[str(N)]["k ≥"]
    pw = _k(J, "★事前功效")
    for key, want in pw.items():
        q = float(key.split("=")[1])
        got = round(sum(comb(N, k) * q ** k * (1 - q) ** (N - k) for k in range(hi, N + 1)), 3)
        assert abs(got - want) < 1e-9, "★ 功效 %s 档案 %r vs 现算 %r" % (key, want, got)
    assert pw["q=0.83"] >= 0.95, "★ 在第一轮那个率上都复现不了 ⇒ 判据有问题"
    honest = _k(J, "功效的老实话")
    assert "测不出小波动" in honest and "kappa" in honest, (
        "★★★ 必须写明它只测大跌, 小波动交给 kappa")


def test_kappa的独立基线与可达性必须现算():
    """★★★ 交卷率高 ⇒ 纯随机一致率本来就高。这条是全轮最容易被误读的地方。"""
    pre = _pre()
    if not pre:
        return
    g = _gen()
    S = _k(pre, "稳定性读数(事前定死判法)")
    res1 = json.loads(R1_RES.read_text(encoding="utf-8"))
    k1, n1 = (int(x) for x in res1["★★★ 主读数: 真实语料交卷率"]["交卷/有效"].split("/"))
    q = k1 / n1
    base = q ** 2 + (1 - q) ** 2
    assert "%.3f" % base in _k(S, "为什么不能看裸的一致率"), (
        "★ 独立基线与现算不符, 应为 %.3f" % base)
    assert base > 0.5, "★ 若基线不再显著高于 0.5, 这条警告的理由要重写"
    # 可达性逐行现算
    same = _k(pre, "与第一轮**完全相同**的部分")
    N = len(same["items"])
    for label, row in _k(S, "★事前可达性").items():
        flip = int(label.split("翻转 ")[1].split(" 条")[0])
        b = c = flip // 2
        a = round(N * q) - b
        d = N - a - b - c
        want = g.kappa_ci(a, b, c, d)
        assert row["kappa"] == want.get("kappa"), "★ %s 的 kappa 与现算不符" % label
        assert row["95%CI"] == want.get("kappa 95%CI")
        assert row["判得出比随机稳吗"] == bool(want.get("kappa 95%CI") and want["kappa 95%CI"][0] > 0)
    lim = _k(S, "事前就知道的上限")
    mf = max(int(x.split("翻转 ")[1].split(" 条")[0])
             for x, v in _k(S, "★事前可达性").items() if v["判得出比随机稳吗"])
    assert "超过 %d 条" % mf in lim, "★ 上限与现算不符, 应为 %d" % mf
    assert "高到能与随机分开吗" in lim


def test_分不出不许被读成稳():
    pre = _pre()
    if not pre:
        return
    S = _k(pre, "稳定性读数(事前定死判法)")
    v = S["判 CANNOT_SHOW_BETTER_THAN_CHANCE"]
    assert "分不出它比随机稳" in v and "逐条层面是噪声" in v, (
        "★★★ 必须事前写明「分不出」本身是个结论, 不是「稳」")


def test_资格层只报机械部分_且不许冒充语义证据():
    pre = _pre()
    if not pre:
        return
    Q = _k(pre, "新增读数: 资格层的**机械**部分")
    assert set(Q["机械出口"]) == {"MALFORMED", "P2_FAIL", "PASS_MECHANICAL"}
    v = _k(Q, "这**不是**「验证器守得住」的证据")
    assert "需要**金标**" in v and "仍然零证据" in v
    assert "不拆" in _k(Q, "GRANULARITY 与 DISTINCT 分不开")
    assert "不重写、不加别名归并" in _k(Q, "规范化复用")


def test_不得做的事必须点名关键几条():
    pre = _pre()
    if not pre:
        return
    blob = " ".join(_k(pre, "不得做的事"))
    for w in ("看过结果再改", "第一轮的任何产物", "读成「稳」", "金标", "r3", "硬上限"):
        assert w in blob, "★ 缺 %r" % w


def test_预算必须接上一轮():
    pre = _pre()
    if not pre:
        return
    b = pre["预算"]
    r1 = json.loads(R1_PRE.read_text(encoding="utf-8"))["预算"]
    assert b["之前已用"] == r1["上限达成时合计"] == 200, "★ 预算链断了: %r" % b
    assert b["上限达成时合计"] == b["之前已用"] + b["本轮上限"]


def test_生成器零调用():
    import ast
    tree = ast.parse(GEN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm not in {"call_model", "urlopen", "_load_key", "post"}, "★ 真实调用 %r" % nm
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])
            for mod in mods:
                assert mod.split(".")[0] not in {"requests", "urllib", "http", "exp_crossmodel_desire"}, (
                    "★ 导入联网模块 %r" % mod)


def test_不许有一个字语料原文():
    pre = _pre()
    if not pre:
        return
    blob = json.dumps(pre, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25:
                assert l.strip()[:25] not in blob, "★★★ 出现语料原文"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("第二轮预注册闸 %d 项全过" % n)
