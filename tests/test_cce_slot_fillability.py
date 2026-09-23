# -*- coding: utf-8 -*-
"""槽位可填性档案的闸。

★★★ 它守的是一条**很容易被忘掉**的纪律: **准确率不是能力, 相对零基线的净增益才是。**
  r4 已经因为这个吃过一次亏(金标倾斜 38:2 ⇒ 不读文本能拿 93.6%),
  r5 的「speaker 68/68 · polarity 136/136」**又一次**看起来像满分 ——
  而同一批上零基线拿 66/68 与 134/136, **全部增益空间只有 2 格**。
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/slot_fillability_audit.py"
R = ROOT / "results/slot_fillability_audit.json"
R5 = ROOT / "results/slot_filling_r5.json"


def _m():
    s = importlib.util.spec_from_file_location("sfa", P)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def test_产物由探针现算_不许手写():
    r = _r()
    if not r:
        return
    live = _m().build_result()
    assert set(r) == set(live), "★★★ 键集不符"
    diff = [k for k in live if r[k] != live[k]]
    assert not diff, "★★★ 与现算不符(档案手写, 或探针改了没重跑): %r" % diff


def test_判准必须是净增益不是准确率():
    r = _r()
    if not r:
        return
    v = r["★★★为什么不能看准确率"]
    assert "零基线拿 66/68" in v and "只有 2 格" in v, (
        "★★★ 必须把「零基线也快满」这个数写出来 —— 否则 68/68 又会被读成能力")
    for s, row in r["逐槽位"].items():
        assert "★净增益(模型−零基线)" in row and "★可得增益(金标−零基线)" in row


def test_可得增益小的槽位必须被标成测不出():
    """★★★ 这是本闸的核心: 增益空间 ≤2 的槽位, 它的准确率**不许**被引用为能力。"""
    r = _r()
    if not r:
        return
    for s, row in r["逐槽位"].items():
        head = row["★可得增益(金标−零基线)"]
        txt = row["★★★这批数据能不能测出这一格"]
        if head <= 2:
            assert txt.startswith("**不能**") and "不得引用为能力" in txt, (
                "★★★ 槽位 %s 的可得增益只有 %d 格, 必须标成测不出: %r" % (s, head, txt))
        else:
            assert txt.startswith("**能**")
    testable = r["★★★这批数据只测得出这几个槽位"]
    assert set(testable) == {s for s, v in r["逐槽位"].items()
                             if v["★可得增益(金标−零基线)"] > 2}, "★ 可测清单与现算不符"


def test_结论必须点名predicate只取到一小部分():
    r = _r()
    if not r:
        return
    c = r["★★★结论"]
    assert "predicate" in c and "12%" in c, "★ 结论必须给出 predicate 实际取到的比例"
    assert "净增益为负" in c, "★ 必须写明 possession 是负增益"
    assert "不得引用为能力" in c, "★ 必须写明那四格的满分不许引用"


def test_对接进生产的含义必须写明_且带边界():
    r = _r()
    if not r:
        return
    v = r["★★★对「判据层能不能接进生产」的含义"]
    assert "没有可用的证据支持" in v, (
        "★★★ 必须写明自动填槽位这条路在已测范围内没有证据支持")
    assert "不得外推" in v, "★ 必须带边界 —— 只测了 68 条手构 item 与一个模型"


def test_r5结果里那条推论已被更正_而不是抹掉():
    """★★★ 我在 r5 产物里写过「其他槽位几乎满分 ⇒ 它认真读了」, 那个推论**证据不足**。
    必须**更正并保留原文**, 不许悄悄删掉。"""
    if not R5.exists():
        return
    d = json.loads(R5.read_text(encoding="utf-8"))
    k = [x for x in d if "这一轮买到了什么" in x][0]
    v = d[k]["★★★为什么这不是「模型摆烂」"]
    assert "更正" in v and "**原文**" in v, (
        "★★★ 那条推论必须**带原文引述地更正**, 不许直接改写成新说法")
    assert "只有 2 格" in v and "这批数据支撑不了" in v, (
        "★ 更正必须说清楚为什么原推论不成立")
    assert "方向不一定对" in v, "★ 收窄后的说法要写出来"
    assert "重演" in v, "★ 必须指出这是 r4 那条教训的重演"


def test_probe零调用():
    src = P.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 可填性档案里出现模型调用入口 %r" % bad


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("槽位可填性闸 %d 项全过" % n)
