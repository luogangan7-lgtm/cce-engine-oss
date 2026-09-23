# -*- coding: utf-8 -*-
"""三项 owner 决策的对比测试闸。

覆盖两个探针:
  · probes/interpretation_upgrade_impact.py —— ① 五类成立条件(及转述那条)升合同的后果
  · probes/real_corpus_feasibility.py       —— ② 改用真实语料可不可行
(③ MiniMax 确定性保证由调研给出, 不在本文件。)

★★★ 本文件守的核心是一条**纪律**: **这两份东西都不做裁定** ——
  升不升、换不换语料, 是 owner 的决定。探针只把**后果与代价**摆出来。
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
UP_P, UP_R = ROOT / "probes/interpretation_upgrade_impact.py", ROOT / "results/interpretation_upgrade_impact.json"
RC_P, RC_R = ROOT / "probes/real_corpus_feasibility.py", ROOT / "results/real_corpus_feasibility.json"
CF = ROOT / "scripts/cce_claim_frame.py"
CF_SHA16 = "54413b38b4303348"


def _m(p, n):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _j(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ───────── 通用: 现算 + 不做裁定 ─────────

def test_两份产物都由探针现算():
    for p, r, n in ((UP_P, UP_R, "up"), (RC_P, RC_R, "rc")):
        d = _j(r)
        if not d:
            continue
        live = _m(p, n).build_result()
        assert set(d) == set(live), "★★★ %s 键集不符" % r.name
        diff = [k for k in live if d[k] != live[k]]
        assert not diff, "★★★ %s 与现算不符: %r" % (r.name, diff)


def test_不做裁定这条纪律必须写明():
    """★★★ 附件 A 升合同那次已经写死: **裁定依据是 owner 的决定, 不是读数**。"""
    d = _j(UP_R)
    if not d:
        return
    v = d["★★★这份东西不做裁定"]
    # ★★★ 2026-09-17 变异 R2b 暴露: 原断言用短子串「owner 的决定」, 而这个值里它**出现两次**
    #   (一次是本文的表述, 一次是引用附件 A 的原话) ⇒ 改掉第一处, 第二处还在, 闸不响。
    #   「子串仍在」今天第三次(docstring 复述 / 同一字符串内重复)。⇒ **一律用完整片段断言**。
    assert "升不升是 owner 的决定, 不是读数能定的" in v, (
        "★★★ 必须写明升不升是 owner 的决定 —— 否则下一个人会拿这份读数当裁定依据")


def test_对比是在镜像上做的_仓内判据层一字未动():
    """★★★ 这份对比要改判据层源码才能算。必须在**镜像**上做。"""
    import hashlib
    got = hashlib.sha256(CF.read_bytes()).hexdigest()[:16]
    assert got == CF_SHA16, (
        "★★★ 仓内 scripts/cce_claim_frame.py 变了(%s ≠ %s) —— "
        "对比必须在镜像上做, 不许动真的判据层" % (got, CF_SHA16))
    src = UP_P.read_text(encoding="utf-8")
    assert "tempfile" in src and "仓内 scripts/cce_claim_frame.py 一个字节没动" in src


# ───────── ① 升合同的后果 ─────────

def test_四个选项都要算_且明文加解释档必须逐字不变():
    """★ 「升」在行为上只改变**只用合同明文**那一档; 「明文+解释」档升前就执行它 ⇒ 必须不变。
    若它变了, 说明变体生成改错了东西。"""
    d = _j(UP_R)
    if not d:
        return
    opts = [k for k in d if k[0] in "①②③④"]
    assert len(opts) == 4, "★ 应有四个选项(现状/只升其一/只升其二/都升), 实为 %d" % len(opts)
    inv = d["★★★「明文+解释」档必须逐字不变"]
    assert all(inv.values()), "★★★ 有选项把「明文+解释」档也改了: %r" % inv


def test_升合同的收益必须带对照通过数_否则看不出代价():
    """★★★ 只报「阴性拦住涨了」是不够的 —— 更严必然伴随误拦风险, 必须同时报对照。"""
    d = _j(UP_R)
    if not d:
        return
    base = d["① 现状(两条都不升)"]["手构最小对照(34 对 × 2 版)"]["只用合同明文"]
    both = d["④ 两条都升"]["手构最小对照(34 对 × 2 版)"]["只用合同明文"]
    bn, bt = (int(x) for x in base["阴性拦住"].split("/"))
    un, _ = (int(x) for x in both["阴性拦住"].split("/"))
    assert un > bn, "★ 都升之后阴性拦住没有提高(%s → %s) ⇒ 结论要重写" % (base["阴性拦住"], both["阴性拦住"])
    # ★★★ 2026-09-17 变异 R4 暴露: 原断言只比「两边相等」—— 把对照改成 "n/a" 两边都是 "n/a", 照样通过。
    #   ⇒ 必须先断言它**是个有效分数**, 再比。
    import re as _re
    for lbl, v in (("现状", base["对照通过"]), ("都升", both["对照通过"])):
        assert _re.fullmatch(r"\d+/\d+", v), "★★★ %s 的对照通过不是有效分数: %r" % (lbl, v)
        a, b = (int(x) for x in v.split("/"))
        assert b > 0 and a == b, "★★★ %s 的对照没有全通过(%s) —— 那是代价" % (lbl, v)
    assert base["对照通过"] == both["对照通过"], (
        "★★★ 升合同**动了对照**(%s → %s) —— 那是代价, 必须单独说而不是埋在阴性数里"
        % (base["对照通过"], both["对照通过"]))


def test_真实证书上无差别的原因必须查清_不许只写无差别():
    """★★★ 「无差别」有两种可能: 规则无关, 或**规则一次都没被 exercise**。
    这两种含义完全不同, 必须分清。"""
    d = _j(UP_R)
    if not d:
        return
    e = d["★★★这两条规则在真实证书上被 exercise 了吗"]
    assert e["citation == REPORTED 出现次数"] == 0 and e["predicate == NOT_OF_DECLARED_KIND 出现次数"] == 0, (
        "★ 若这两条已经有对象, 本条结论要重写: %r" % e)
    v = e["★★★所以真实证书上「无差别」是什么意思"]
    assert "不是「这两条规则无关」, 是「它们一次都没被 exercise」" in v and "同型" in v, (
        "★★★ 必须写明这是**零覆盖**而不是**无关**, 且与 r4/r2 同型")
    c = e["★★★对「升不升」的含义"]
    assert "在现有真实数据上买不到任何可验证的东西" in c and "那个收益不能外推" in c, (
        "★★★ 必须写明: 收益只在手构对照上可见, 而手构对照不能外推")
    assert "决策的性质不是「升了有没有好处」" in c, (
        "★★★ 必须把结论点破: **升了的好处目前测不出来**")


# ───────── ② 真实语料可不可行 ─────────

def test_核心论证必须在_RESTATES是抽取错误类别():
    """★★★ 这是第②项的全部答案: 它不是语言现象, 人标不出来。"""
    d = _j(RC_R)
    if not d:
        return
    k = [x for x in d if "不是自然语言类别" in x][0]
    v = d[k]
    assert "A 支的属性" in v and "B 支" in v, (
        "★★★ 必须说清「只指认」放在 B 支是**正确**的, 不构成错误")
    assert "抽取错误" in v
    ans = d["★★★所以可行吗"]
    assert "人标得出" in ans and "标不出" in ans, (
        "★★★ 必须写明人能标什么、标不出什么 —— 那是「不可行」的理由")


def test_代价估算必须标明是外推_不许当精确预算():
    d = _j(RC_R)
    if not d:
        return
    v = d["★★★代价估算"]
    assert "外推估算" in v and "不得当成精确预算" in v, (
        "★★★ ~570 次是从 48 次产出 2 条外推的, 不许写成实测")
    assert "136" in v, "★ 必须给出已用预算做对照, 否则看不出量级"


def test_剩下的选择必须包含小批试_那是唯一能把估算变成数的做法():
    d = _j(RC_R)
    if not d:
        return
    opts = d["★★★还剩什么选择"]
    assert len(opts) >= 3
    a = [x for x in opts if x.startswith("**(a)")][0]
    assert "实测" in a and "换成实测值" in a, (
        "★★★ 必须有一条是「小批试 ⇒ 把外推估算换成实测」")
    c = [x for x in opts if x.startswith("**(c)")][0]
    assert "REPORTED **也是 0 次**" in c, (
        "★★★ 「换一个类别」这条不许只说可能 —— 实测 REPORTED 也是 0 次, 必须写上")


def test_两个probe都零调用():
    for p in (UP_P, RC_P):
        src = p.read_text(encoding="utf-8")
        for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
            assert bad not in src, "★★★ %s 里出现模型调用入口 %r" % (p.name, bad)


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("三项决策对比闸 %d 项全过" % n)
