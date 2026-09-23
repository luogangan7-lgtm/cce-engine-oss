# -*- coding: utf-8 -*-
"""r2 结果的**读法纪律闸**。

★★★ 这一轮最容易被读错的方向:
  「阴性 0 错误升格 + 对照 2/4 通过 ⇒ 这条路安全了」——**完全错**。
  真相是: 抽取器**自己**拒答了全部 12 条, **资格层一次都没被 exercise**,
  所以「验证器守得住」这句话仍然零证据。买到的是「抽取器不太上钩」, 不是「验证器守得住」。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/extractor_counterexample_r2.json"
P = ROOT / "tests/data/extractor_counterexample_prereg_r2.json"


def _r():
    return json.loads(R.read_text(encoding="utf-8"))


def test_判读与降级都由冻结逻辑现算():
    """不许把判决与降级手写进档案 —— 用执行器自己的 summarize() 现跑一遍比对。"""
    import importlib.util, sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "r2run", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    r = _r()
    S = m.summarize(r["rows"])
    assert S["verdict"] == r["★★★verdict(原始_不得单独引用)"], (
        "★ 档案判决 %r 与按冻结逻辑现算 %r 不符" % (r["★★★verdict(原始_不得单独引用)"], S["verdict"]))
    assert S["最终判读"] == r["★★★最终判读"], "★ 最终判读与现算不符"
    assert S["降级"] == (r["★★★判读降级(测量前冻结的条件)"] if S["降级"] else []), "★ 降级列表与现算不符"


def test_预算与失败计数守住了():
    r = _r()
    cap = json.loads(P.read_text(encoding="utf-8"))["执行"]["★请求硬上限"]
    assert r["★硬上限"] == cap and r["★实际执行数"] <= cap
    assert len(r["rows"]) == r["★实际执行数"], "★ 有调用没被记账"
    assert r["★重试"] == 0
    # 失败的那次**必须**计入执行数、**不得**进任何分母
    bad = [x for x in r["rows"] if not x["调用成功"]]
    assert r["调用或格式失败"] == len(bad)
    for x in bad:
        assert "不进任何分母" in x["why"]


def test_不许把这轮读成验证器守得住():
    """★★★ 本轮的核心限度。阴性 0 错误升格**不是**验证器的功劳 —— 它一次都没被调用。"""
    r = _r()
    adj = r["阴性合计"]["★被资格层裁决过"]
    k = "★★★怎么读这一轮(逐条带证据)"
    assert k in r, "★ 结果文件必须自带逐条读法"
    v = json.dumps(r[k], ensure_ascii=False)
    if adj.startswith("0/"):
        assert "一次都没被 exercise" in v and "零证据" in v, (
            "★★★ 资格层零裁决, 却没写「验证器守得住仍然零证据」—— "
            "下一个只读 p_challenge 的人会把这轮读成安全")
    assert "★★★这一轮**不**支持什么" in r, "★ 缺「不支持什么」清单"
    n = json.dumps(r["★★★这一轮**不**支持什么"], ensure_ascii=False)
    for must in ("验证器守得住", "抽取器安全", "单独引用"):
        assert must in n, "★ 「不支持什么」里缺: %s" % must


def test_r1的悬案必须被明确了结或明确未了结():
    """r1 判 DEGENERATE_ON_CONTROLS, 预注册把「第二次退化」绑成路线终局结论。
    r2 的对照结果必须显式回答这桩悬案, 不许悬着。"""
    r = _r()
    up = r["正证据对照"]["结局"].get("UPGRADED", 0)
    v = json.dumps(r["★★★怎么读这一轮(逐条带证据)"], ensure_ascii=False)
    if up:
        assert "仪器伪影" in v and "走得通" in v, (
            "★ 对照通过了 %d/4, 必须明写 r1 的 DEGENERATE 是仪器伪影、这条路走得通" % up)
    else:
        assert "D5" in json.dumps(r["★★★判读降级(测量前冻结的条件)"], ensure_ascii=False) \
            or "第二次退化" in v, "★ 对照全败时必须交代终局条款是否触发"


def test_事后观察与预注册指标分得开():
    """★ 人工复核 why_not 得出的 4/4 **不得**顶替机械读法的 1/4。
    两个数必须同时在, 且事后观察要自带「不得当结论用」。"""
    r = _r()
    k = [x for x in r if x.startswith("★★★事后观察")]
    assert k, "★ 缺事后观察段"
    assert "不是**预注册指标" in k[0] and "不得当结论用" in k[0], (
        "★ 事后观察段的标题必须自带隔离声明")
    v = json.dumps(r[k[0]], ensure_ascii=False)
    assert "不改锚词表重算" in v, (
        "★★★ 必须明写**不改锚词表重算** —— 测量后改判据就是调参")
    # 机械读数照留
    assert "命名对了 1" in r["★★★逐臂"]["对象错配阴性"]["拒答"], (
        "★ 机械读法的 1/4 被人工复核的 4/4 顶替了 —— 两个数必须同时在")


def test_测量后不许改判据_prompt与模板哈希未变():
    """跑完之后, 提示词与模板必须与测量前冻结的完全一致。"""
    import hashlib, importlib.util, sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "r2run2", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    d = json.loads(P.read_text(encoding="utf-8"))
    assert hashlib.sha256(m.PROMPT.encode()).hexdigest()[:8] == d["★★★prompt(逐字冻结)"]["sha256_8"], (
        "★★★ 测量之后提示词被改过 —— 那份读数就不再对应任何冻结设计")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r2 读法纪律 %d 项全过" % n)
