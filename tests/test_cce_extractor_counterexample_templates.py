# -*- coding: utf-8 -*-
"""16 条构造模板的**机械自检**。

★★★ 这个闸覆盖什么、不覆盖什么 —— 必须先说清, 否则它自己就是一个伪保证:

  覆盖: 声明的片段是否**逐字**在文本里 · 四格条数 · 每格内表述结构是否互异 ·
        阴性格是否声明了它赖以成立的那个否定/错配结构 · 推导是否**写了**。
  **不**覆盖: 上面任何一条推导**对不对**。
        2026-09-13 的零调用反例(tests/test_cce_citation_layer_is_not_semantic.py)
        已经证明「片段逐字在原文里」验不了否定辖域/归属/时态/引用层级/类型成员。
        把这个闸的绿当成「推导已验证」, 就是在重犯那个错。
"""
import json, os, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
F = ROOT / "tests/data/extractor_counterexample_templates.json"
ARMS = {"正证据对照": 4, "缺P阴性": 4, "否定Q阴性": 4, "对象错配阴性": 4}


def _load():
    return json.loads(F.read_text(encoding="utf-8"))


def test_合同原文与分类学逐字一致():
    """推导的地基是合同原文。原文一旦漂移, 16 条推导全部作废 —— 这里钉住它。"""
    d = _load()
    key = [k for k in d if k.startswith("★合同原文")][0]
    tx = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    live = tx["knots"][4]["hard_discriminant"]
    assert d[key] == live, (
        "★★★ 合同原文已漂移 ⇒ 16 条推导的地基没了, **不许直接改这个文件的引用了事**,\n"
        "    必须逐条重走推导。\n  档案: %r\n  现行: %r" % (d[key], live))


def test_四格条数与结构互异():
    T = _load()["templates"]
    got = collections.Counter(t["arm"] for t in T)
    assert dict(got) == ARMS, "★四格条数不符: %r" % dict(got)
    ids = [t["id"] for t in T]
    assert len(set(ids)) == len(ids), "★id 重复"
    texts = [t["text"] for t in T]
    assert len(set(texts)) == len(texts), "★有两条文本完全相同"
    for arm in ARMS:
        ss = [t["结构"] for t in T if t["arm"] == arm]
        assert len(set(ss)) == len(ss), (
            "★%s 内有重复的表述结构 %r —— GPT 的区组要求是**不同表述结构**, "
            "不是换四个物品名。" % (arm, ss))


def test_每条声明的片段都逐字在文本里():
    for t in _load()["templates"]:
        for k in ("span_P", "span_Q", "span_negQ"):
            s = t.get(k)
            if s is None:
                continue
            assert s in t["text"], "★%s.%s 不在文本里逐字出现: %r" % (t["id"], k, s)


def test_阴性格声明了它赖以成立的结构():
    """每一格**为什么是阴性**, 靠的是不同的东西。声明缺了, 那一格就不知道在测什么。"""
    for t in _load()["templates"]:
        a, d = t["arm"], t["推导"]
        if a == "缺P阴性":
            assert t.get("span_P") is None, "★%s 是缺P格, 不该声明 span_P" % t["id"]
            assert t.get("span_Q"), "★%s 缺P格必须声明 Q 那一支在哪" % t["id"]
            assert any("五类" in v or "闭列" in v for v in d.values()), (
                "★%s 没写「五类逐一核过」—— 缺P格的全部成立性就在这一步" % t["id"])
        elif a == "否定Q阴性":
            assert t.get("span_negQ"), "★%s 必须声明否定片段" % t["id"]
            assert "两支" in d.get("Q", ""), (
                "★%s 没声明**两支都否定** —— Q 是析取, 只否一支不构成否定" % t["id"])
        elif a == "对象错配阴性":
            assert t.get("about_P") and t.get("about_Q"), "★%s 必须声明两个对象" % t["id"]
            assert t["about_P"] != t["about_Q"], "★%s 两个对象声明成同一个了" % t["id"]
            for need in ("Q(a)", "P(b)"):
                assert "不" in d.get(need, ""), (
                    "★%s 没核 %s 不成立 —— 错配格必须**双向**核, 否则该格根本不成立"
                    % (t["id"], need))
        else:
            assert t.get("span_P") and t.get("span_Q"), "★%s 正证据格两支都要声明" % t["id"]
            assert "同一对象" in d, "★%s 正证据格必须声明同一对象" % t["id"]


def test_正证据格覆盖了Q的两支():
    """Q = 已拥有 **或** 已经历。四条正证据若全走「已拥有」, 另一支这轮从没测过。"""
    T = [t for t in _load()["templates"] if t["arm"] == "正证据对照"]
    assert any("已经历" in t["推导"].get("Q", "") for t in T), (
        "★正证据四条没有一条走**已经历**那一支 —— 析取的另一半没被测到")


def test_每条都写了预期():
    for t in _load()["templates"]:
        assert t["推导"].get("预期"), "★%s 没写预期结果" % t["id"]
        exp = t["推导"]["预期"]
        want = "应当" if t["arm"] == "正证据对照" else "不得"
        assert want in exp, "★%s 预期方向错: %r" % (t["id"], exp)


def test_缺P阴性带着它的读法前提和推翻条件():
    """缺P那 4 条全靠「五类是闭列」。那是**读法不是字面** —— 前提与推翻条件必须随档案走,
    否则合同哪天被读成示例, 这 4 条会静悄悄地继续被引用。"""
    d = _load()
    k = [x for x in d if "读法前提" in x]
    assert k, "★ 缺P阴性依赖闭列读法, 档案里却没有前提声明"
    v = d[k[0]]
    for must in ("读法", "推翻条件", "自动作废"):
        assert must in v, "★ 前提声明里缺「%s」" % must


def test_这个闸自己声明了它不验语义():
    d = _load()
    k = [x for x in d if "机械自检覆盖什么" in x]
    assert k, "★模板档案必须自带「机械自检覆盖什么」声明"
    v = d[k[0]]
    assert "不验证" in v and "逐字" in v, (
        "★该声明必须明写: 逐字核对**不**验证推导。少了这句, 下一个人会把这闸的绿"
        "读成「推导已验证」。")


def test_prereg_状态与模板文件同步():
    p = json.loads((ROOT / "tests/data/extractor_counterexample_prereg.json"
                    ).read_text(encoding="utf-8"))
    st = p["★★★status"]
    if not F.exists():
        assert "BLOCKED_ON_TEMPLATES" in st
        return
    assert "BLOCKED_ON_TEMPLATES" not in st, (
        "★模板已写出, prereg 却还挂着 BLOCKED_ON_TEMPLATES —— 两边不同步")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("模板自检 %d 项全过 —— ★但它没验过任何一条推导" % n)
