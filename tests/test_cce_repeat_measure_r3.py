# -*- coding: utf-8 -*-
"""r3 = **r2 的重复测量**。本文件守两件事:

  ① 重复测量的**定义**真的成立 —— 同一份执行器代码 · 同一提示词 · 同一模板 · 同一种子。
     ★ 2026-09-14 教训: 把执行器**分叉成新文件**时**旧闸只守旧文件** ——
       配对变异实测: 同一变异打 r2 文件被抓, 打分叉文件 **96 道全绿**。
       ⇒ 重复测量必须走**同一个文件**, 这条由下面的闸钉住。
  ② 梯度设计(已否决且从未投料)**不许被重做或被误当成 READY**。
"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P3 = ROOT / "tests/data/repeat_measure_prereg_r3.json"
P2 = ROOT / "tests/data/extractor_counterexample_prereg_r2.json"
RES2 = ROOT / "results/extractor_counterexample_r2.json"
RES3 = ROOT / "results/repeat_measure_r3.json"
GRAD = ROOT / "tests/data/refusal_gradient_prereg_r3.json"
RUNNER = ROOT / "probes/extractor_counterexample_run_r2.py"


def _mod():
    spec = importlib.util.spec_from_file_location("r2run", RUNNER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_重复测量走的是同一份执行器_不是分叉出来的():
    d = json.loads(P3.read_text(encoding="utf-8"))
    v = d["★★★重复测量的定义(这是本轮的全部严谨性所在)"]["同一份执行器代码"]
    assert "extractor_counterexample_run_r2.py" in v and "一个字未动" in v
    src = RUNNER.read_text(encoding="utf-8")
    assert "CCE_EXTRACTOR_OUT" in src, "★ 同一执行器必须支持换输出路径, 否则重复测量会覆盖 r2 的读数"
    # ★★★ 反向: 仓里**不得**再出现第二份能被运行的抽取器执行器
    forks = [p for p in (ROOT / "probes").glob("*extractor*run*.py")
             if p.name != RUNNER.name]
    forks += [p for p in (ROOT / "probes").glob("*refusal_gradient*run*.py")]
    for f in forks:
        body = f.read_text(encoding="utf-8")
        assert "raise SystemExit" in body and "已被否决" in body, (
            "★★★ %s 是一份**可运行的分叉执行器**, 而闸只守 %s —— "
            "配对变异实测已证分叉文件上同一变异 96 道全绿。要么合并, 要么封掉入口。"
            % (f.name, RUNNER.name))


def test_提示词与模板与种子逐字未变():
    m = _mod()
    d2 = json.loads(P2.read_text(encoding="utf-8"))
    d3 = json.loads(P3.read_text(encoding="utf-8"))
    assert hashlib.sha256(m.PROMPT.encode()).hexdigest()[:8] == d2["★★★prompt(逐字冻结)"]["sha256_8"], (
        "★★★ 提示词变了 ⇒ 这就不是**重复测量**, 是另一次测量")
    assert d2["★★★prompt(逐字冻结)"]["sha256_8"] in d3["★★★status"]
    src = RUNNER.read_text(encoding="utf-8")
    assert "random.Random(20260914)" in src, "★ 种子变了 ⇒ 引入了一个无关变量"
    assert "extractor_counterexample_templates_r2.json" in src


def test_r2基线在测量前就被冻结进预注册():
    """★ 比对基线必须**测量前**写死, 否则跑完再挑基线就是自我实现。"""
    d = json.loads(P3.read_text(encoding="utf-8"))
    base = d["★r2 的逐条基线(测量前冻结, 用于比对)"]
    live = {r["id"]: r["outcome"] for r in json.loads(RES2.read_text(encoding="utf-8"))["rows"]}
    assert base == live, "★★★ 冻结基线与 r2 结果文件现算不符: %r" % (
        {k: (base.get(k), live.get(k)) for k in set(base) | set(live) if base.get(k) != live.get(k)})
    assert len(base) == 16


def test_不许用r3去改r2的读数():
    d = json.loads(P3.read_text(encoding="utf-8"))
    n = json.dumps(d["★★★不得据此说"], ensure_ascii=False)
    assert "只能**加注**" in n and "回溯重算" in n, (
        "★★★ 必须明禁「用 r3 改 r2」与「拿 r3 的容错去回溯重算 r2 那条失败行」")
    # r2 的结果文件必须**逐字节**没被动过(重复测量不得修改被比对的基线)
    if RES3.exists():
        r2 = json.loads(RES2.read_text(encoding="utf-8"))
        base = json.loads(P3.read_text(encoding="utf-8"))["★r2 的逐条基线(测量前冻结, 用于比对)"]
        assert {r["id"]: r["outcome"] for r in r2["rows"]} == base, (
            "★★★ r2 的读数在 r3 之后被改过了")


def test_梯度设计留档为REJECTED且入口已封():
    """★ 库里铁律: 被否决的方案**必须留档**, 否则下一个 agent 会重做它。"""
    d = json.loads(GRAD.read_text(encoding="utf-8"))
    assert d["★★★status"].startswith("**REJECTED"), "★ 梯度设计没被标成 REJECTED"
    assert "未发起任何调用" in d["★★★status"]
    rr = [k for k in d if k.startswith("★★★REJECTED_reason")]
    assert rr, "★ 没写 reject_reason ⇒ 下一个 agent 会重做它"
    body = json.dumps(d[rr[0]], ensure_ascii=False)
    for must in ("断点判据", "轴不成立", "假声称", "换了维度", "共线", "第四次「假保证」"):
        assert must in body, "★ reject_reason 里缺: %s" % must
    assert "superseded_by" in d[rr[0]], "★ 否决必须带 superseded_by"


def test_用桩真跑一次main_覆盖整条产物路径():
    """★★★ 2026-09-14 的 blocking 教训通则化: 分叉出来的那份执行器在 `res` 字典里引用了
    预注册中**不存在**的两个键 ⇒ **16 次调用跑完之后**才 KeyError, 结果文件一个字都写不出;
    而 12 道闸**没有一道碰过 main()**, 12/12 全绿。

    ⇒ 凡是会**花掉不可补抽预算**的执行器, 必须有一道闸**用桩真跑一遍 main()**,
      断言产物落盘且可解析。零外部调用。
    """
    import os, tempfile
    m = _mod()
    calls = {"n": 0}

    def fake_call_model(model, prompt, temperature=0.0, max_retries=1, **kw):
        calls["n"] += 1
        return ('{"supported": false, "evidence": [], "why_not": '
                '"不满足条件 A: 没有具体型号、数据、使用细节、纠错或结构化经验"}'), {"error": None}

    import exp_crossmodel_desire as X
    import cce_knot_classify as CK
    real = X.call_model
    real_load = m._load_key
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "stub.json"
        m.OUT = out
        m._load_key = lambda: None            # 桩: 不碰凭据文件
        X.call_model = fake_call_model
        try:
            m.main()
        finally:
            X.call_model = real
            m._load_key = real_load
        assert out.exists(), "★★★ main() 跑完了却没落盘 —— 那正是被否决那份执行器的形态"
        got = json.loads(out.read_text(encoding="utf-8"))   # 必须可解析
        assert len(got["rows"]) == 16 and got["★实际执行数"] == 16
        assert calls["n"] == 16, "★ 调用次数与硬上限不符: %d" % calls["n"]
        for k in ("★★★最终判读", "★★★不得据此说", "★★★已知局限(两轮评审确认_测量前写下)"):
            assert k in got, "★ 产物缺 %s —— 未来读者读不到" % k
        # 桩全部拒答 ⇒ 对照也拒答 ⇒ 必然 DEGENERATE, 且 D5 不响(拒答不是格式/粒度层)
        assert got["★★★verdict(原始_不得单独引用)"] == "DEGENERATE_ON_CONTROLS"


def test_结果出来后逐条比对由冻结基线现算():
    if not RES3.exists():
        return
    d = json.loads(P3.read_text(encoding="utf-8"))
    base = d["★r2 的逐条基线(测量前冻结, 用于比对)"]
    r3 = json.loads(RES3.read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in r3["rows"]}
    # ★ 预注册: 分母**只算两轮都调用成功的**。r2 里调用失败的那条 outcome 为 None,
    #   必须排除 —— 否则「r3 这次成功了」会被算成一次翻转, 把噪声算进不稳定度。
    both = [i for i in base if base[i] and rows.get(i) and rows[i]["调用成功"]]
    flips = [i for i in both if rows[i]["outcome"] != base[i]]
    k = len(flips)
    assert r3["★★★逐条比对"]["翻转数 k"] == k, "★ 翻转数与现算不符"
    assert r3["★★★逐条比对"]["比对点"] == "%d/16" % len(both)
    want = "STABLE" if k == 0 else "UNSTABLE_%d" % k
    assert r3["★★★verdict(重测)"] == want, (
        "★ 判决 %r 与按冻结规则现算 %r 不符" % (r3["★★★verdict(重测)"], want))
    if k:
        assert "单次运行读数" in json.dumps(r3, ensure_ascii=False), (
            "★★★ 有翻转却没写「r2 的每一格都变成单次运行读数」")
    if len(both) < 12:
        assert any("D9" in x for x in (r3.get("★★★判读降级(测量前冻结的条件)") or [])), (
            "★ 比对点不足 12 却没挂 D9")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r3 重复测量闸 %d 项全过" % n)
