# -*- coding: utf-8 -*-
"""浅层线索臂的闸。

★★★ 它守的第一件事是: **RULES 先于文本修改而固定**。
  若规则可以随文本调整, 这个臂测的就只是「我能不能造一个打不中的正则」。
"""
import hashlib, importlib.util, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PROBE = ROOT / "probes/shallow_cue_arm.py"
RES = ROOT / "results/shallow_cue_arm.json"
# ★ RULES 块的哈希。**规则由 2026-09-15 那次评审的某个 agent 在旧版文本上独立写出**, 我没参与。
RULES_SHA16 = "f7b46ae15fd65ec7"


def _res():
    return json.loads(RES.read_text(encoding="utf-8")) if RES.exists() else None


def _m():
    spec = importlib.util.spec_from_file_location("shallow", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_RULES必须逐字冻结_不许随文本调整():
    """★★★ 这是本臂的全部严谨性。规则一旦可以跟着文本改, 它就测不出任何东西。"""
    src = PROBE.read_text(encoding="utf-8")
    blk = re.search(r"RULES = \{.*?\n\}", src, re.S)
    assert blk, "★ 找不到 RULES 块"
    h = hashlib.sha256(blk.group(0).encode()).hexdigest()[:16]
    assert h == RULES_SHA16, (
        "★★★ RULES 变了(%s ≠ %s)。改它之前必须回答: **这条新规则是在没看过新文本的情况下写的吗?** "
        "若不是, 本臂退化成「我能不能造一个打不中的正则」。" % (h, RULES_SHA16))
    assert "不许随文本调整" in src and "先于文本修改而固定" in src, (
        "★ 源码里那条纪律被删了 —— 下一个人会顺手调规则")


def test_规则来源必须写明是别人独立写的():
    r = _res()
    if not r:
        return
    k = [x for x in r if "规则的来源" in x][0]
    v = r[k]
    assert "我没有参与它的构造" in v and "旧版对照文本" in v, (
        "★★★ 必须写明规则**不是我写的、且写在文本修改之前** —— 这是它能当基线的唯一理由")



def test_结果由探针现算_不许手写():
    r = _res()
    if not r:
        return
    m = _m()
    live = {s: "%d/%d" % (0, 0) for s in ()}
    # 现跑逐槽位
    per = {}
    for iid, src, gold, D, is_anx in m.items():
        for key, is_A in (("A", True), ("B", False)):
            g = dict(D, **gold[key])
            got = m.fill(src["text"], src[key][0], is_A)
            for s in m.SLOTS:
                d = per.setdefault(s, [0, 0])
                d[1] += 1
                d[0] += got[s] == g[s]
    live = {s: "%d/%d" % tuple(v) for s, v in per.items()}
    assert r["★★★逐槽位"] == live, "★★★ 档案 %r 与现算 %r 不符" % (r["★★★逐槽位"], live)


def test_predicate必须拆开报_聚合数读不出鉴别力():
    r = _res()
    if not r:
        return
    k = [x for x in r if "predicate 必须拆开报" in x][0]
    v = r[k]
    assert "鉴别格(金标 ≠ 零基线常数)" in v and "多数类格(金标 == 零基线常数)" in v
    assert "稀释" in v["★为什么拆"], "★ 没写清楚为什么必须拆"
    assert "结构上不可能" in v["★零基线在鉴别格上按构造是 0/4"], (
        "★ 必须写明零基线在鉴别格上**结构上**答不对, 而不是碰巧 0 分")
    assert [x for x in r if "聚合数不许直接读" in x], (
        "★★★ predicate 聚合含 B 支 24 格协议白送的满分, 必须声明不许直接读")



def test_v1到v2的句法共线修正必须现跑_且带外部锚点():
    """★★★ 2026-09-15: contract_pairs 整体重造(6 对 → 24 对)。
    要留的证据不是「改了哪几个字」, 而是**句法共线修掉了多少**, 以及**离真实语料还有多远**。"""
    r = _res()
    if not r:
        return
    k = [x for x in r if "消共线前后" in x][0]
    assert "现跑" in k
    cf = _m().counterfactual()
    assert r[k] == cf, "★★★ 档案与现跑不符 —— 结论是手写的"
    v1, v2 = cf["★★★v1(已撤回的 6 对)"], cf["★★★v2(现在的 24 对)"]
    assert v1 and v1["最佳净增益"] > v2["最佳净增益"], (
        "★★★ 重造必须**降低**冻结族的最佳净增益: v1 %r vs v2 %r" % (v1, v2))
    assert cf["★外部锚点_真实证书上的冻结族最佳净增益"] == 0, (
        "★ 锚点变了就要重新论证 —— 它来自 48 次已付费调用")
    w = cf["★★★仍然成立的警告"]
    assert "仍不是 0" in w and "留出集" in w, (
        "★★★ 必须写明**净增益仍不是 0**、且 p0 要取**留出集**那个 —— "
        "把「压下来了」写成「解决了」就是假保证")
    assert v2["鉴别格数"] >= 20, "★ 鉴别格太少, 门会没有余量: %d" % v2["鉴别格数"]


def test_这个臂是基线不是被测对象():
    r = _res()
    if not r:
        return
    body = json.dumps(r, ensure_ascii=False)
    assert "不经任何模型" in body and "它是**基线**, 不是被测对象" in body
    assert "只有超过本臂, 才谈得上读懂了语义" in body, (
        "★★★ 本臂存在的全部理由就是这句话, 不许删")


def test_probe零调用():
    src = PROBE.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 浅层线索臂里出现模型调用入口 %r" % bad

def test_产物的每一个键都由探针现算_改了源码不重跑也会被抓到():
    """★★★ 这一条取代了一堆脆弱的「源码里必须含某子串」断言。

    变异实测里踩到两次同一个坑: 闸只查**结果文件**时, 改了探针源码不重跑就看不见;
    而改成查源码子串后, **同一句话在 docstring 里还有一份** ⇒ 子串仍在, 闸照样绿
    (「我的断言太弱」第二次复发)。
    ⇒ 根本修法: 探针把「计算 + 构造产物」抽成 build_result(), 闸**现算整份**再逐键比对。
    """
    r = _res()
    if not r:
        return
    live = _m().build_result()
    assert set(r) == set(live), "★★★ 键集不符: 档案 %r vs 现算 %r" % (sorted(r), sorted(live))
    diff = [k for k in live if r[k] != live[k]]
    assert not diff, "★★★ 这些键与现算不符(档案是手写的, 或探针改了没重跑): %r" % diff


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("浅层线索臂闸 %d 项全过" % n)
