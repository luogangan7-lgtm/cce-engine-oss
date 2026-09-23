# -*- coding: utf-8 -*-
"""r4(模型自己填六槽位)的设计闸 + 执行器闸。★ 结果未出时只守设计与执行器。"""
import hashlib, importlib.util, json, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P = ROOT / "tests/data/slot_filling_prereg_r4.json"
RES = ROOT / "results/slot_filling_r4.json"
PROBE = ROOT / "probes/slot_filling_run_r4.py"
GOLD = ROOT / "tests/data/claim_frame_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"


def _mod():
    spec = importlib.util.spec_from_file_location("r4", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_提示词冻结且不泄露答案():
    m, d = _mod(), json.loads(P.read_text(encoding="utf-8"))
    f = d["★★★prompt(逐字冻结)"]
    assert m.PROMPT == f["text"], "★★★ 运行时提示词与冻结的不一致 —— 冻结就失效了"
    assert hashlib.sha256(m.PROMPT.encode()).hexdigest()[:8] == f["sha256_8"]
    for bad in f["★不许出现的话(泄露答案)"]:
        assert bad not in m.PROMPT, "★★★ 提示词泄露答案: %r" % bad
    assert "supports" not in m.PROMPT, (
        "★★★ 提示词又把 supports 标签放回去了 —— 那等于先把要判的结论说了")
    assert "UNSPECIFIED, 不要猜" in m.PROMPT, (
        "★ 必须明确允许 UNSPECIFIED 且不许猜 —— 否则模型被迫猜, fail-closed 就被破坏了")


def test_金标在r4之前已冻结_且不由r4读数决定():
    """★ 金标已用于上界测量。测量后改金标 = 调结果。"""
    g = json.loads(GOLD.read_text(encoding="utf-8"))
    assert len(g["annotations"]) == 10
    bad = {k: v for k, v in g["★默认槽位"].items() if v != "UNSPECIFIED"}
    assert not bad, "★★★ 金标默认槽位又变成 fail-open 了: %r" % bad
    d = json.loads(P.read_text(encoding="utf-8"))
    n = json.dumps(d["★★★不得据此说"], ensure_ascii=False)
    assert "不得**据此改金标" in n or "改金标" in n, "★ 必须明禁测量后改金标"


def test_只测填槽位_不测选片段():
    m = _mod()
    d = json.loads(P.read_text(encoding="utf-8"))
    assert "不让模型选" in d["★★★刻意隔离了什么"]
    src = PROBE.read_text(encoding="utf-8")
    assert "semantic_minimal_pairs.json" in src, "★ span 必须取自已冻结的最小对照"
    # 提示词里必须**给出** span, 而不是让模型找
    # 提示词必须**给出**片段, 而不是让模型自己去文本里找
    assert "片段一:" in m.PROMPT and "片段二:" in m.PROMPT, (
        "★ 提示词没有把片段直接给出 —— 那就变成「选片段 + 填槽位」混在一起了")
    assert "%s" in m.PROMPT


def test_预算与准入结果都在预注册里():
    d = json.loads(P.read_text(encoding="utf-8"))
    assert d["执行"]["★请求硬上限"] == 20 and d["执行"]["★自动重试"] == 0
    assert "均已用尽且不可挪用" in d["执行"]["★★★与 r1/r2/r3 的预算关系"]
    k = [x for x in d if "判据准入结果" in x]
    assert k, "★★★ 声明调用预算的预注册**必须带准入结果**(库内硬规则)"
    v = d[k[0]]
    assert "★★★我对被拦那两条的回应(不是无视)" in v, (
        "★★★ 准入拦下了判据却没回应 —— 无视准入等于没做准入")
    r = v["★★★我对被拦那两条的回应(不是无视)"]
    assert "退化检测" in r and "宽松" in r and "误拒率" in r, (
        "★ 回应必须说清: 这是退化检测方向 · 零容差落在宽松侧 · 且实际估了误拒率")


def test_不设达标线_且写明为什么():
    d = json.loads(P.read_text(encoding="utf-8"))
    v = d["★★★主判据(测量前冻结)"]["★★★本轮不设达标线"]
    assert "首次测量" in v and "拍脑袋" in v and "事后改线" in v


def test_桩自检五态都在预注册里():
    """★★★ 判据非空性: 既要能测出标注误差的代价, 也要能拦住「全填 UNSPECIFIED 制造完美」。"""
    d = json.loads(P.read_text(encoding="utf-8"))
    k = [x for x in d if "零调用桩自检" in x][0]
    v = d[k]
    assert "五态" in k, "★ 桩自检应为五态"
    assert "复现上界" in json.dumps(v, ensure_ascii=False)
    body = json.dumps(v, ensure_ascii=False)
    assert "2/10" in body, "★ 必须证明标注误差**会**让端到端漏 —— 否则这轮测不出代价"
    assert "D5" in body and "没有证据说明模型在读文本" in body, (
        "★★★ 必须证明「模型=零基线」会被 D5 拦住")
    assert "D4" in body and "伪造" in body, (
        "★★★ 必须证明「枚举外取值伪造复现上界」这条路被堵死")


def _stub_run(mode):
    """用桩真跑 main(), **零调用**。mode: gold / baseline / illegal / flip"""
    import io, contextlib
    m = _mod()
    m.PREREG = dict(m.PREREG)
    m.PREREG["★★★status"] = "**READY** (闸内桩跑, 零调用)"
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    pairs = {x["id"]: x for x in json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]}
    import exp_crossmodel_desire as X

    def fake(model, prompt, temperature=0.0, max_retries=1, **kw):
        for pid, pp in pairs.items():
            for side in ("pos", "neg"):
                if pp[side]["text"] in prompt:
                    g = gold["annotations"][pid]["frames"][side]

                    def mk(key):
                        if mode == "baseline":
                            return dict(m.BASELINE)
                        d = {s_: g[key].get(s_, "UNSPECIFIED") for s_ in m.SLOTS}
                        if mode == "illegal" and side == "neg":
                            d["polarity"] = "NO"
                        if mode == "flip" and side == "neg" and key == "A":
                            d["predicate"] = "OF_DECLARED_KIND"
                        return d
                    return json.dumps({"片段一": mk("A"), "片段二": mk("B")}), {"error": None}
        return "", {"error": "no match"}

    real, realk = X.call_model, m._load_key
    with tempfile.TemporaryDirectory() as td:
        m.OUT = pathlib.Path(td) / "o.json"
        m._load_key = lambda: None
        X.call_model = fake
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                m.main()
        finally:
            X.call_model, m._load_key = real, realk
        return json.loads(m.OUT.read_text(encoding="utf-8"))


def test_三臂对照存在_且零基线确实漏满():
    """★★★ 评审最要命的一条: 金标取值极度倾斜, 一个**完全不读文本**的常数填充器
    能拿 206/220=93.6% 而阴性 10/10 全漏。没有零基线, 那个准确率**毫无意义**。"""
    r = _stub_run("gold")
    T = r["★★★三臂对照(同一批 items · 同一套打分)"]
    for k in ("模型", "金标(上界)", "零基线(常数多数类填充)"):
        assert k in T, "★★★ 三臂缺 %s" % k
    assert "必须显著优于它" in r["★★★零基线是什么"]
    m = _mod()
    assert m.BASELINE and all(v != "UNSPECIFIED" for v in m.BASELINE.values()), (
        "★ 零基线必须是**多数类肯定值**")
    b = T["零基线(常数多数类填充)"]["端到端"]["明文+解释"]["阴性被放行"]
    assert b == "10/10", (
        "★★★ 零基线阴性放行 %s ≠ 10/10 —— 它没能暴露「不读文本也能拿高分」" % b)


def test_D5_模型不优于零基线时必须降级():
    d = _stub_run("baseline")["★★★判读降级(测量前冻结)"]
    assert any(x.startswith("D5") for x in d), (
        "★★★ 模型=零基线时 D5 没响 ⇒ 「不读文本」可以冒充「读了文本」")
    assert "没有证据说明模型在读文本" in " ".join(d)


def test_D4_非法取值不许伪造复现上界():
    """★★★ 实测: 若干个枚举外取值就能让端到端显示 0/10(看起来复现上界), 因为非法值被当成未填
    ⇒ fail-closed ⇒ 看起来像「拦住了」。修法是把含非法取值的条目**剔出端到端分母**。"""
    r = _stub_run("illegal")
    T = r["★★★三臂对照(同一批 items · 同一套打分)"]["模型"]
    assert T["★端到端可用"] == "10/20", "★ 可用样本数不对: %s" % T["★端到端可用"]
    assert "无可用样本" in T["端到端"]["明文+解释"]["阴性被放行"], (
        "★★★ 阴性分母里还留着含非法取值的条目 ⇒ 「复现上界」可被伪造")
    assert any(x.startswith("D4") for x in r["★★★判读降级(测量前冻结)"])
    assert T["非法取值"] == 20


def test_标注误差的代价必须测得出来():
    """★ 若 predicate 填反(正是 MIS-4 那种错)端到端不变, 这一轮就测不出任何代价。"""
    T = _stub_run("flip")["★★★三臂对照(同一批 items · 同一套打分)"]["模型"]
    assert T["端到端"]["明文+解释"]["阴性被放行"] == "2/10", (
        "★★★ predicate 填反后阴性放行 %s —— 应为 2/10"
        % T["端到端"]["明文+解释"]["阴性被放行"])


def test_两档都报_不许只跑一档():
    r = _stub_run("gold")
    for arm in r["★★★三臂对照(同一批 items · 同一套打分)"].values():
        for tier in ("只用合同明文", "明文+解释"):
            assert tier in arm["端到端"], "★★★ 少报了「%s」那一档" % tier
    assert "不许合并" in r["★★★两档都报"]


def test_敏感格定义必须与判据实际用到的槽位一致():
    """★★★ 敏感格若手写成「全槽位」, 装饰格就会把真实能力稀释掉, 而闸看不见。
    ⇒ 从 _p/_q 的**源码现算**它们实际用到哪些槽位, 与 SENSITIVE 逐字比对。"""
    import inspect
    import cce_claim_frame as CF
    m = _mod()
    for side, fn in (("A", CF._p), ("B", CF._q)):
        src = inspect.getsource(fn)
        used = {s_ for s_ in m.SLOTS if ("f." + s_) in src}
        assert set(m.SENSITIVE[side]) == used, (
            "★★★ SENSITIVE[%r] = %r, 但 %s 实际用到的是 %r —— "
            "敏感格必须由**判据结构**决定, 不许手写"
            % (side, sorted(m.SENSITIVE[side]), fn.__name__, sorted(used)))


def test_金标哈希必须与冻结的一致():
    """★★★ 金标在 r4 之前已用于上界测量。测量后改金标 = 调结果。
    变异实测: 改金标一格, 原来 14 道闸**一道都没响**(桩用的就是金标, 改了桩跟着改)。"""
    import hashlib
    d = json.loads(P.read_text(encoding="utf-8"))
    k = [x for x in d if "金标哈希" in x]
    assert k, "★★★ 预注册里没有金标哈希 ⇒ 金标可以被事后改而无人知道"
    want = d[k[0]]["sha256_8"]
    got = hashlib.sha256(GOLD.read_bytes()).hexdigest()[:8]
    assert got == want, (
        "★★★ 金标已被改动! 冻结 %s vs 现算 %s —— "
        "金标在 r4 之前已用于上界测量, **测量后改金标就是调结果**" % (want, got))


def test_敏感格与装饰格分开报():
    r = _stub_run("gold")
    acc = r["★★★三臂对照(同一批 items · 同一套打分)"]["模型"]["逐槽位"]
    assert acc and any("敏感" in v for v in acc.values()), "★ 敏感格没单独报"
    v = r["★★★敏感格与装饰格"]
    assert "由判据结构决定" in v and "都不进端到端" in v


def test_用桩真跑一次main_覆盖整条产物路径():
    """★ r3 的 blocking 教训通则化: 会花掉不可补抽预算的执行器, 必须有闸用桩真跑 main()。"""
    got = _stub_run("gold")
    assert got["★实际执行数"] == 20 and len(got["rows"]) == 20
    T = got["★★★三臂对照(同一批 items · 同一套打分)"]["模型"]
    e = T["端到端"]["明文+解释"]
    assert e["阴性被放行"] == "0/10", "★ 金标喂回去没复现上界: %s" % e["阴性被放行"]
    assert e["对照通过"] == "10/10", "★ 对照没全过: %s" % e["对照通过"]
    assert got["★★★判读降级(测量前冻结)"] == "无"
    for k in ("★★★不得据此说", "★★★已知局限(测量前写下)", "★★★本轮不设达标线",
              "★★★零基线是什么", "★★★敏感格与装饰格", "★★★非法取值单列"):
        assert k in got, "★ 产物缺 %s —— 未来读者读不到" % k


def test_结果出来后由冻结判据现算():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    rows = [r for r in res["rows"] if r["调用成功"]]
    neg = [r for r in rows if r["side"] == "neg"]
    pos = [r for r in rows if r["side"] == "pos"]
    assert res["★硬上限"] == 20 and res["★实际执行数"] <= 20
    assert len(res["rows"]) == res["★实际执行数"], "★ 有调用没被记账"
    T = res["★★★三臂对照(同一批 items · 同一套打分)"]
    for k in ("模型", "金标(上界)", "零基线(常数多数类填充)"):
        assert k in T, "★★★ 产物里三臂缺 %s" % k
    # 金标臂必须复现上界 —— 它是这一轮的**内部一致性检查**
    g = T["金标(上界)"]["端到端"]["明文+解释"]
    assert g["阴性被放行"] in ("0/10", "0/0 —— **无可用样本**"), (
        "★★★ 金标臂没复现上界(%s) ⇒ 打分链路有问题, 模型那一臂的数也不可信" % g["阴性被放行"])


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r4 闸 %d 项全过" % n)
