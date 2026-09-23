# -*- coding: utf-8 -*-
"""seed 探针读数的闸。**22 次已花, 这些数不许被改、不许被误读。**

★★★ 这份读数回答了三项决策的第 ③ 项, 而且它的头条**不是 seed**:
  **temperature=0.0 · 同一 prompt · 6 次调用 → 5 种不同输出**(零失败)。
  那正是 CCE 实际使用的调用形态。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/seed_probe.json"
P = ROOT / "probes/seed_probe.py"


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def test_判据是2026_08_18写的_今天一字未动():
    """★★★ 探针写于 2026-08-18、今天第一次跑。**判据不许在看过数据后改** —— 那是调参。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "判据(写于 2026-08-18" in x][0]
    v = r[k]
    assert "组内 uniq==1" in v and "B==C 或组内不确定" in v, "★ 判据被改写了"
    src = P.read_text(encoding="utf-8")
    assert "只改了**两处非判据的东西**" in src and "判据逻辑一字未动" in src, (
        "★★★ 源码里必须写明改了什么、没改什么")


def test_四组都跑了_且预算记清楚():
    r = _r()
    if not r:
        return
    n = r["逐组样本数"]
    assert set(n) == {"D temp=0.0 无seed", "A temp=0.6 无seed",
                      "B temp=0.6 seed=42", "C temp=0.6 seed=999"}, "★ 缺组: %r" % sorted(n)
    assert sum(n.values()) == 22, "★ 本轮应 22 次, 实为 %d" % sum(n.values())
    b = r["★预算"]
    assert b["本轮"] == 22 and b["之前已用"] == 136 and b["合计"] == 158, "★ 预算记账不符: %r" % b
    for k, rows in r["rows"].items():
        assert len(rows) == n[k]
        assert all(not o.get("err") for o in rows), "★ %s 有失败调用 —— 那会改变读法" % k


def test_头条是D组而不是seed():
    """★★★ D 组(temp=0.0)是 CCE 实际使用的形态。把头条写成 seed 会让人以为「换个参数就好了」。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "D 组(temp=0.0)才是头条" in x][0]
    v = r[k]
    assert "6 次调用 → 5 种不同输出" in v["读数"] and "零失败" in v["读数"], (
        "★ 头条读数必须带「几次几种」和「零失败」—— 后者排除「是调用挂了」这个解释")
    assert "不在 CCE 链路里, 在模型本身" in v["★为什么它比 seed 那部分更要紧"]
    d = r["逐组不同输出数"]["D temp=0.0 无seed"]
    assert d > 1, "★★★ 若 D 组变成确定的(%d), 整份结论要重写" % d


def test_它排除了服务端变更这个解释_这是相对r3的新东西():
    """★★★ r3 当时明写「k=6 不能单独归因于模型随机性(也可能是服务端变更), 本轮区分不了」。
    本探针的 6 次是**同一时刻并发**发出的 ⇒ 那个解释被排除。这是本轮相对 r3 的**新增**。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "D 组(temp=0.0)才是头条" in x][0]
    v = r[k]["★★★它排除了一个此前排除不掉的解释"]
    assert "同一时刻" in v and "并发" in v, "★ 必须说清为什么服务端变更被排除"
    assert "服务端变更这个解释被排除" in v
    nb = r[k]["★★★不得与 r3 的 60% 直接比"]
    assert "两个数不可比" in nb and "方向" in nb, (
        "★★★ r3 测整条证书判决(离散), 本探针测连续权重 ⇒ 一致率天然不同。"
        "必须写明只能比方向")


def test_seed的结论必须标明是实测而不是文档推断():
    r = _r()
    if not r:
        return
    k = [x for x in r if "seed 的结论(实测" in x][0]
    v = r[k]
    assert "不再是从「文档没写」推断的" in v["★结论"], (
        "★★★ 「文档没写」与「实测发过 seed 输出照样每次不同」是两种分量完全不同的证据")
    doc = [x for x in r if "官方文档" in x][0]
    assert "无 seed" in r[doc] and "无 system_fingerprint" in r[doc], "★ 文档核查结论要留档"


def test_不许说temp0与temp06没有差别():
    """★★★ D 与 A 的成对一致率都是 1/15。但 n=15 时那个区间宽得几乎覆盖整个低值区。
    ⇒ 只能说「这批数据分不出」, 不能说「没有差别」。
    ★ 这正是同一天刚更正过的毛病(4/24 与 6/24 分不开却写成「比…还少」)。"""
    r = _r()
    if not r:
        return
    k = [x for x in r if "temp=0 与 temp=0.6 分得开吗" in x][0]
    v = r[k]
    assert "这批数据分不出" in v["★★★不许说「没有差别」"], "★ 必须收窄成「分不出」"
    assert "同一个错不许在同一天犯第二次" in v["★★★不许说「没有差别」"], (
        "★★★ 必须点名这是刚更正过的那个毛病 —— 否则下次还会犯")
    assert "不依赖" in v["★能说的只有一句"], (
        "★ 能说的那句必须**不依赖**与 temp=0.6 的比较")


def test_边界必须写明_确定性解决的不是当前卡住的问题():
    r = _r()
    if not r:
        return
    b = r["★★★边界"]
    assert "不得外推" in b, "★ 单一 prompt 单一模型, 不得外推"
    assert "效度" in b and "填不出 predicate" in b, (
        "★★★ 必须写明: **确定性是「可复现」的仪器属性**, 而当前卡住的三条路是**效度**问题 —— "
        "即便 seed 生效也救不了")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("seed 探针读数闸 %d 项全过" % n)
