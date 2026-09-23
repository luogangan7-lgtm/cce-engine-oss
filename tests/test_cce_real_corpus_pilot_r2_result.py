# -*- coding: utf-8 -*-
"""第二轮(重测)结果的闸。现算整份逐键比对。

★★★ 它守的核心是三句话:
  ① 主判据的拒绝域是**继承第一轮的冻结表**, 不是现场推导的
  ② kappa 的「分不出」**不许**被读成「稳」
  ③ 资格层的**机械**出口**不许**被读成「验证器守得住」
"""
import hashlib, importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/real_corpus_pilot_r2.json"
PRE = ROOT / "tests/data/real_corpus_pilot_r2_prereg.json"
R1_PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
R1_RES = ROOT / "results/real_corpus_pilot.json"
RUN = ROOT / "probes/real_corpus_pilot_r2_run.py"


def _res():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _mod():
    s = importlib.util.spec_from_file_location("_r2run", RUN)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def test_整份必须与build_result现算逐键一致():
    res = _res()
    if not res:
        return
    m = _mod()
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    env = [res[x] for x in res if "运行时环境" in x][0]
    got = m.build_result(pre, res["rows"], res["★实际执行数"], res["耗时秒"], res["model"], env)
    for k in got:
        if k == "耗时秒":
            continue
        assert got[k] == res[k], (
            "★★★ %s 与现算不符 —— 改了执行器却没重跑?\n  档案 %r\n  现算 %r" % (k, res[k], got[k]))


def test_拒绝域必须继承第一轮的冻结表_不许现场推导():
    res = _res()
    if not res:
        return
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    J = _k(pre, "主判据(投料前定死)")
    table = _k(J, "第一轮拒绝域表(继承, 不重算)")
    # ★ 它必须与第一轮预注册里那张表**逐键相同**
    p1 = json.loads(R1_PRE.read_text(encoding="utf-8"))
    J1 = [p1[x] for x in p1 if "主判据" in x][0]
    t1 = [J1[x] for x in J1 if "拒绝域按实际 n_ok 查表" in x][0]
    assert table == t1, "★★★ 第二轮的拒绝域表与第一轮不同 ⇒ 判据被换过"
    M = res["★★★ 主判据: 第一轮的判决复现吗"]
    k2, n_ok = (int(x) for x in M["第二轮"].split(" = ")[0].split("/"))
    reg = table.get(str(n_ok))
    assert M["★继承的拒绝域(第一轮冻结表, 未重算)"] == reg, "★★★ 用的不是该 n_ok 那一行"
    min_n = _k(J, "第一轮最低可判 n_ok")
    if n_ok < min_n or reg is None:
        want = "INSUFFICIENT_DATA"
    elif reg["k ≥"] is not None and k2 >= reg["k ≥"]:
        want = "CONFIRMED"
    else:
        want = "NOT_CONFIRMED"
    assert M["★★★判决"] == want, "★ 判决与查表不符: k2=%d n_ok=%d 应判 %s" % (k2, n_ok, want)


def test_第一轮的产物必须逐字节没被动过():
    """★★★ 重测的意义是**只让时间变**。第一轮被改过, 这轮就白跑。"""
    res = _res()
    if not res:
        return
    pin = [res[x] for x in res if "第一轮产物 sha256" in x][0]
    assert pin == hashlib.sha256(R1_RES.read_bytes()).hexdigest(), (
        "★★★ 第一轮产物被改过 —— 重测失去意义")
    src = RUN.read_text(encoding="utf-8")
    assert "def preflight2" in src and "未发起任何调用" in src, "★ 执行器没有调用前重验"
    assert src.index("preflight2(pre, p1, m)") < src.index("for it, line in pairs"), (
        "★★★ 重验必须在循环之前")


def test_kappa的分不出不许被读成稳():
    res = _res()
    if not res:
        return
    K = _k(res, "稳定性: 逐条稳不稳")
    if K["★★★判读"] == "CANNOT_SHOW_BETTER_THAN_CHANCE":
        v = _k(K, "★★★怎么读")
        assert "分不出它比随机稳" in v, "★★★ 分不出被读成了「稳」"
        assert "逐条层面仍可能是噪声" in v, "★ 必须写明边际复现 ≠ 逐条稳"
    # ★ kappa 与配对表必须自洽
    c = K["配对 2x2"]
    g = importlib.util.spec_from_file_location(
        "_g2", ROOT / "probes/real_corpus_pilot_r2_prereg.py")
    g2 = importlib.util.module_from_spec(g); g.loader.exec_module(g2)
    want = g2.kappa_ci(c["两轮都交卷"], c["一交二不交"], c["一不交二交"], c["两轮都不交"])
    for kk, vv in (want or {}).items():
        assert K.get(kk) == vv, "★ kappa 的 %s 与现算不符: %r vs %r" % (kk, K.get(kk), vv)
    assert sum(c.values()) == K["可配对条数"], "★ 配对表加总与可配对条数不符"


def test_独立基线必须报出来_不许只报裸一致率():
    """★★★ 交卷率高 ⇒ 纯随机下一致率本来就高。只报裸一致率会把噪声读成稳。"""
    res = _res()
    if not res:
        return
    K = _k(res, "稳定性: 逐条稳不稳")
    if K.get("kappa") is None:
        return
    assert "pe(独立基线)" in K, "★★★ 没报独立基线"
    assert K["pe(独立基线)"] > 0.3, "★ 独立基线异常低, 读法要重想"
    assert "扣掉它之后剩下的" in _k(K, "为什么不看裸的一致率")


def test_资格层机械出口不许被读成验证器守得住():
    res = _res()
    if not res:
        return
    Q = _k(res, "新增: 资格层的**机械**部分")
    v = _k(Q, "这不是「验证器守得住」的证据")
    assert "需要**金标**" in v and "仍然零证据" in v, (
        "★★★ 机械出口被读成了语义证据 —— 那句话自 r2 起就是零证据")
    assert "不拆" in _k(Q, "P2_FAIL 没有再拆")
    # ★ 出口分布必须与 rows 现算一致
    m = _mod()
    from collections import Counter
    want = dict(sorted(Counter(q for q in (m.qualify_mechanical(r) for r in res["rows"]) if q).items()))
    assert Q["出口分布"] == want, "★ 出口分布与现算不符: %r vs %r" % (Q["出口分布"], want)


def test_不许有一个字语料原文或模型文本():
    res = _res()
    if not res:
        return
    blob = json.dumps(res, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25:
                assert l.strip()[:25] not in blob, "★★★ 出现语料原文"
    for r in res["rows"]:
        for o in r.get("objects") or []:
            assert set(o) == {"有 object", "object 逐字", "sha16"}, (
                "★★★ objects 的形状变了, 可能把 object 文本带回来了: %r" % o)
            assert o["sha16"] is None or len(o["sha16"]) == 16
        for kk, vv in r.items():
            assert not (isinstance(vv, str) and len(vv) > 70 and kk != "sha256"), (
                "★ 行里有超长字符串: %s" % kk)
        assert "err" not in r, "★ err 正文可能夹带上游响应体"
    assert "只存规范化后的 sha16" in res["★隐私"]


def test_行必须对得上分片文件():
    res = _res()
    if not res:
        return
    if res["model"] in ("SMOKE", "DRY_RUN"):
        return
    P = ROOT / "results/real_corpus_pilot_r2_partial.jsonl"
    assert P.exists(), "★★★ 真跑却没有分片文件 —— 逐次落盘没生效"
    part = {}
    for ln in P.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            part[r["ptr"]] = r
    for r in res["rows"]:
        assert part.get(r["ptr"]) == r, "★★★ 产物的行与分片不符 —— rows 被改过: %s" % r["ptr"]
    assert len(res["rows"]) == len(part)


def test_本轮不回答什么必须逐条列出():
    res = _res()
    if not res:
        return
    v = " ".join(res["★★★ 本轮不回答什么"])
    for w in ("金标", "因子二", "机制未识别", "r3", "60%"):
        assert w in v, "★ 缺 %r" % w


def test_重试必须是1不是0():
    res = _res()
    if not res:
        return
    assert "max_retries=1" in res["★重试"] and "不是 0" in res["★重试"]
    import ast
    tree = ast.parse(RUN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "max_retries":
            v = getattr(node.value, "value", None)
            assert v != 0, "★★★ 源码里有 max_retries=0 —— 那等于一次 HTTP 都不发"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("第二轮结果闸 %d 项全过(产物未生成时空过)" % n)
