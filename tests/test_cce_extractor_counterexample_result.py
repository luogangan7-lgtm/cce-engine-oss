# -*- coding: utf-8 -*-
"""抽取器构造反例一轮的**读法纪律闸**。

这一轮的判决是 DEGENERATE_ON_CONTROLS —— 最容易被后来的人读错成
「跑过了, 阴性 0/12, 抽取器干净」。这个闸把不许那样读钉住。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/extractor_counterexample.json"
P = ROOT / "tests/data/extractor_counterexample_prereg.json"


def test_判决是由冻结规则现算的_不是写死的():
    r = json.loads(R.read_text(encoding="utf-8"))
    rows = r["rows"]
    neg = [x for x in rows if x["arm"] != "正证据对照"]
    pos = [x for x in rows if x["arm"] == "正证据对照"]
    negz = [x for x in neg if x["Z"]]
    posz = [x for x in pos if x["Z"]]
    want = ("COUNTEREXAMPLE_FOUND" if negz
            else "DEGENERATE_ON_CONTROLS" if not posz
            else "NO_COUNTEREXAMPLE_IN_THIS_SUITE")
    assert r["★★★verdict"] == want, (
        "★档案判决 %r 与按冻结规则现算 %r 不符" % (r["★★★verdict"], want))
    assert r["p_challenge"] == "%d/%d" % (len(negz), len(neg))
    assert r["正证据成功"] == "%d/%d" % (len(posz), len(pos))


def test_预算与失败计数守住了():
    r = json.loads(R.read_text(encoding="utf-8"))
    cap = json.loads(P.read_text(encoding="utf-8"))["执行"]["★请求硬上限"]
    assert r["★硬上限"] == cap
    assert r["★实际执行数"] <= cap, "★超了硬上限"
    assert len(r["rows"]) == r["★实际执行数"], "★行数与执行数不符 —— 有调用没被记账"
    assert r["★重试"] == 0, "★预注册写的是零重试"


def test_这一轮不许被读成抽取器干净():
    r = json.loads(R.read_text(encoding="utf-8"))
    if r["★★★verdict"] != "DEGENERATE_ON_CONTROLS":
        return                      # 判决变了, 这条读法纪律随之作废
    k = "★★★怎么读这个判决"
    assert k in r and "不是" in r[k] and "安全" in r[k], (
        "★ DEGENERATE 的结果必须自带「阴性 0/N 不是安全证据」这句 —— "
        "少了它, 下一个只读 p_challenge 的人会把这轮读成通过")
    assert "★★★退化的单一原因" in r, "★ 退化了却没写原因 = 下一轮会原样再退化一次"


def test_被误伤挡下的候选反例没有被静默丢掉():
    """NEGP-1 曾被模型判 supported, 却因**无关原因**被 P2 拦下。
    它不计入 p_challenge(对), 但**必须留痕**(否则下一轮以为这格从没亮过)。"""
    r = json.loads(R.read_text(encoding="utf-8"))
    if r["★★★verdict"] != "DEGENERATE_ON_CONTROLS":
        return
    post = [v for k, v in r.items() if k.startswith("★事后观察")]
    assert post, "★ 事后观察整段没了"
    body = json.dumps(post[0], ensure_ascii=False)
    assert "不是**预注册指标" in json.dumps(list(r), ensure_ascii=False) or "事后观察" in str(list(r))
    assert "不计入 p_challenge" in body, (
        "★ 必须明写它**不计入**主指标 —— 否则事后观察会被当成测量结果")
    # 现算: 确实存在这样一行(模型说 supported 却 Z=0 且原因是对象不同)
    hit = [x for x in r["rows"]
           if isinstance(x["模型原样"], dict) and x["模型原样"].get("supported")
           and not x["Z"] and x["arm"] != "正证据对照"]
    assert hit, "★ 档案里说有这样一行, 现算找不到"


def test_修法不许是放松P2():
    r = json.loads(R.read_text(encoding="utf-8"))
    if "★★★退化的单一原因" not in r:
        return
    why = json.dumps(r["★★★退化的单一原因"], ensure_ascii=False)
    assert "不许" in why and "放松" in why, (
        "★ 必须明写「不许放松 P2」—— 放松它会把对象错配那一格重新放进来, "
        "而那正是 P2 存在的理由。这是退化结果最容易招来的错误修法。")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("读法纪律 %d 项全过 · 判决 DEGENERATE_ON_CONTROLS" % n)
