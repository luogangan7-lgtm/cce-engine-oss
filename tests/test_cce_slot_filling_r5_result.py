# -*- coding: utf-8 -*-
"""r5 读数的闸。**68 次已花, 这些数不许被改、不许被误读。**"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
R = ROOT / "results/slot_filling_r5.json"
P = ROOT / "tests/data/slot_filling_prereg_r5.json"


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def test_读数与预注册冻结的门一致():
    r = _r()
    if not r:
        return
    FZ = json.loads(P.read_text(encoding="utf-8"))["★★★主判据(测量前冻结_confirmatory)"]
    m = r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    assert "≥%d/%d" % (FZ["★冻结的门"], FZ["★冻结的 n"]) in m["★冻结的门(预注册, 非现算)"], (
        "★★★ 产物里的门与预注册不符 —— 测量后换门就是调结果")
    assert m["零假设 p0(= 最佳浅层规则的命中率)"] == FZ["★冻结的 p0"]


def test_主判据未达成这件事不许被改写():
    r = _r()
    if not r:
        return
    m = r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    assert m["★结论"].startswith("**未达成**"), "★★★ 读数是未达成, 不许改写"
    assert m["★三个前置条件"]["① 鉴别格 ≥ 冻结的门"] is False
    k, n = (int(x) for x in m["B 臂鉴别格"].split("/"))
    bk, _ = (int(x) for x in m["最佳浅层规则鉴别格"].split("/"))
    assert k < bk, "★ 读数变了: B 臂 %d vs 最佳浅层规则 %d" % (k, bk)


def test_D6必须响_且写明零增益():
    r = _r()
    if not r:
        return
    dg = r["★★★判读降级"]
    assert dg != "无", "★★★ B 臂鉴别格 ≤ 最佳浅层规则, D6 必须响"
    assert any("D6" in x and "零增益" in x for x in dg), "★ D6 没写明零增益"


def test_四个必须一起读的边界都在():
    r = _r()
    if not r:
        return
    k = [x for x in r if "这一轮买到了什么" in x][0]
    v = r[k]
    assert "未经检验的假说" in v["★★★它推翻了什么"] and "告诉了它判据, 他还是判不出" not in v["★★★它推翻了什么"]
    assert "136/136" in v["★★★为什么这不是「模型摆烂」"], (
        "★★★ 必须给出「其他槽位几乎满分」的数 —— 否则 4/24 会被读成模型没能力")
    assert "0.167" in v["★★★为什么这不是 power 不够"], (
        "★★★ 必须写明模型实际命中率远低于 power 拐点 —— 否则阴性会被推给功效不足")
    assert "两条路都不通" in v["★★★但规则也不行"] and "24/24" in v["★★★但规则也不行"], (
        "★★★ 必须写明**金标 24/24 说明这个区分可判**, 只是自动化方法都接近随机")
    ns = json.dumps(v["★★★不得据此说"], ensure_ascii=False)
    for must in ("没有语义能力", "不如规则", "自然语料", "n=1"):
        assert must in ns, "★ 「不得据此说」漏了 %r" % must


def test_五臂的数由同一批同一套打分():
    r = _r()
    if not r:
        return
    k = [x for x in r if "五臂对照" in x][0]
    arms = r[k]
    assert len(arms) == 5, "★ 应有 5 条臂(四条零调用 + 一条模型臂), 实为 %d" % len(arms)
    g = [v for a, v in arms.items() if a.startswith("①")][0]
    z = [v for a, v in arms.items() if a.startswith("②")][0]
    gp = g["逐槽位"]["predicate"]["★★★鉴别格(金标 ≠ 零基线常数)"]
    zp = z["逐槽位"]["predicate"]["★★★鉴别格(金标 ≠ 零基线常数)"]
    assert gp.split("/")[0] == gp.split("/")[1], "★★★ 金标臂鉴别格不是满分 ⇒ 打分链路有问题: %s" % gp
    assert zp.startswith("0/"), "★★★ 零基线在鉴别格上必须是 0(结构上答不对): %s" % zp


def test_两档必须分开报():
    r = _r()
    if not r:
        return
    k = [x for x in r if "五臂对照" in x][0]
    for arm, t in r[k].items():
        e = t["端到端(两档分开报_不许合并)"]
        assert "只用合同明文" in e and "明文+解释" in e, "★ 臂 %s 没两档分报" % arm


def test_执行记录完整():
    r = _r()
    if not r:
        return
    assert r["★实际执行数"] == r["★硬上限"] == 68
    assert r["调用或格式失败"] == 0
    assert len(r["rows"]) == 68, "★ rows 不全: %d" % len(r["rows"])
    assert r["★★★两臂提示词哈希(现算)"], "★ 提示词哈希没落盘"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r5 读数闸 %d 项全过" % n)
