"""G-K3 的重定义必须站得住 —— 零 API, 全部现算。

原 G-K3「签名两两可分」被判 **YES_TAUTOLOGY**(2026-09-07)。本闸钉住四件事:
① 新台账的 **PASS 分支结构上不存在**(不是「今天没走到」, 是源码里没有)
② 旧读法的**判红条件不可达**, 且距离可被无成本刷高 —— 与 L3 哈希同型
③ `belong` 纸面靠上、仪器 0/308 —— 直接反例
④ G-K3 与 G-K1 **不冗余**: 完全混淆的退化面板在 G-K1 判据下**满分通过**
"""
import ast
import itertools
import json
import math
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import gk3_class_realization_ledger as L  # noqa: E402

PROBE = (ROOT / "probes" / "gk3_class_realization_ledger.py").read_text(encoding="utf-8")
RG = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
DIMS = ["attribution", "target_layer", "congruence", "coping", "need_status", "time"]
SIG = {k["key"]: k["signature"] for k in TAXO["knots"]}


def _vals(s):
    """斜杠 = 析取, 括号 = 子类型 ⇒ 一个格子是**取值集合**, 不是字符串。"""
    return {x.strip() for x in re.sub(r"\(.*?\)", "", s).split("/") if x.strip()}


def _lit(a, b):
    return sum(SIG[a][d] != SIG[b][d] for d in DIMS)


def _strict(a, b):
    return sum(not (_vals(SIG[a][d]) & _vals(SIG[b][d])) for d in DIMS)


def test_pass_branch_does_not_exist_in_source():
    """★★★ 核心: `_verdict()` 里**没有任何一条路径**返回 PASS —— 由 AST 证, 不由跑一次证。"""
    fn = next(n for n in ast.walk(ast.parse(PROBE))
              if isinstance(n, ast.FunctionDef) and n.name == "_verdict")
    rets = [n.value.value for n in ast.walk(fn)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)]
    assert rets, "★ _verdict 没有常量返回 —— 解析失效或结构变了"
    assert all(r.startswith("WITHHELD") for r in rets), f"★★ 出现了非 WITHHELD 的出口: {rets}"
    assert "PASS" not in "".join(rets), "★★★ PASS 分支被加回来了 —— 本台账的读数不足以支撑 PASS"


def test_belong_never_wins_but_is_not_absent():
    """③ 纸面靠上, 仪器从不把它排第一 —— 但它**不是**缺席, 更不是「死类」。"""
    d = L.build()
    assert "belong" in d["★classes_that_never_win"], f"★ 变了? {d['★classes_that_never_win']}"
    b = d["per_knot"]["belong"]
    assert b["consensus_argmax"] == 0 and b["annotator_top1"] == 0
    # ★★ GPT 调研点名要的诊断量: 只报 top1=0 **推不出** top2=0。
    assert b["top2"] > 0 and b["nonzero"] > 0, (
        "★ 若 belong 真的 top2=0 且非零=0, 它就是代数惰性坐标, 删掉不改变任何指标 —— "
        "那结论要改写; 现在它**不是**")
    # ★★ 而它与 inertia/injustice 的差别是 0/78 vs 1/78, 区间几乎完全重叠
    for other in ("inertia", "injustice"):
        o = d["per_knot"][other]
        lo_b, hi_b = b["consensus_ci95"]; lo_o, hi_o = o["consensus_ci95"]
        assert min(hi_b, hi_o) > max(lo_b, lo_o), (
            f"★ belong 与 {other} 的共识区间不再重叠 ⇒ 「一个死一个活」这个区分现在有数据支撑了, "
            "请更新台账与 probe 里「统计上不可区分」的说法")
    paper = min(_strict("belong", k) for k in SIG if k != "belong")
    assert paper >= 2, f"★ belong 的纸面最小严格距 {paper} —— 反例的力度依赖它靠上"
    assert d["verdict"].startswith("WITHHELD")


def test_literal_hamming_is_unfalsifiable_and_gameable():
    """② 判红条件不可达 + 距离可被无成本刷高(= L3 哈希同型)。"""
    lit = {(a, b): _lit(a, b) for a, b in itertools.combinations(sorted(SIG), 2)}
    assert min(lit.values()) >= 1, "★ 有两行签名逐字全等 —— 那才是这条 lint 唯一能抓的"
    st = {p: _strict(*p) for p in lit}
    assert min(st.values()) < min(lit.values()), (
        f"★ 按语义读距离没有塌(字面 min={min(lit.values())} vs 严格 min={min(st.values())}) —— "
        "若值域已被受控词表清理干净, 请更新本断言与 probe 的说法")
    # ★ 无成本刷高: 给任一格加括号后缀, 字面距离变大, 而取值集合一个都没变
    a, b = min(lit, key=lit.get)
    d0 = next(d for d in DIMS if SIG[a][d] == SIG[b][d])
    old = SIG[a][d0]
    try:
        SIG[a][d0] = old + "(补注)"
        assert _lit(a, b) == lit[(a, b)] + 1, "★ 加括号后缀没有抬高字面距离?"
        assert _strict(a, b) == st[(a, b)], "★ 取值集合被改变了 —— 那这就不是零成本刷分"
    finally:
        SIG[a][d0] = old


def test_gk1_is_structurally_blind_to_confusion():
    """④ ★★ 承重: 两结永远 50/50 完全不可分 ⇒ G-K1 **满分通过**。"""
    assert "in top2[b][i] or tops[b][i] in top2[a][i]" in RG, \
        "★ G-K1 的 top2 判据表达式变了 —— 下面这个反例要重做"
    deg = [{"display": 0.5, "pain_seek": 0.5} for _ in range(10)]
    t2 = sum(1 for x in deg  # 两边同分布 ⇒ 各自 top1 必在对方 top2 内
             if max(x, key=x.get) in sorted(x, key=x.get, reverse=True)[:2]) / len(deg)

    def js(p, q):
        m = {k: (p[k] + q[k]) / 2 for k in p}
        kl = lambda u, v: sum(u[k] * math.log2(u[k] / v[k]) for k in u if u[k] > 0)
        return 0.5 * kl(p, m) + 0.5 * kl(q, m)
    jsv = sum(js(x, x) for x in deg) / len(deg)
    assert t2 >= 0.8 and jsv <= 0.25, f"★ 退化面板没过 G-K1? top2={t2} JS={jsv}"
    g = json.loads((ROOT / "accuracy" / "out" / "gates_result.json").read_text(encoding="utf-8"))
    assert "参考" in g["G_K1v2_分布一致性"]["criteria"], \
        "★ κ 不再是参考项了 —— 若它进了判决, 上面的退化反例需要重估"


def test_hard_discriminant_never_reaches_the_annotator():
    """⑤ 书面自证: 为四大混淆对写的判别式, 标注者从来没拿到过。"""
    assert all("hard_discriminant" in k for k in TAXO["knots"]), "★ hard_discriminant 不见了"
    brief = re.search(r"KNOT_BRIEF\s*=\s*(.*?)\n\n", RG, re.S).group(1)
    assert "signature" in brief and "hard_discriminant" not in brief, (
        "★ KNOT_BRIEF 的注入内容变了 —— 若 hard_discriminant 现在**真的**喂给标注者了, "
        "这是好事, 但 probe 里「只读 signature 的 G-K3 会给已存档为未分开的那几对开绿灯」这句要改")


def _reverse_checks():
    n = 0
    g = globals()
    # ① 源码里加回 PASS 出口 ⇒ 必须红
    saved = g["PROBE"]
    g["PROBE"] = saved.replace('return "WITHHELD_INSTRUMENT_NOT_BLIND"', 'return "PASS"')
    try:
        test_pass_branch_does_not_exist_in_source()
        raise SystemExit("★ 反向验证失败: 加回 PASS 出口后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["PROBE"] = saved
    # ② belong 复活 ⇒ 死类断言必须红
    real = L.build
    d = real()
    d["★classes_that_never_win"] = []
    d["per_knot"]["belong"]["consensus_argmax"] = 3
    g["L"].build = lambda *a, **k: d
    try:
        test_belong_never_wins_but_is_not_absent()
        raise SystemExit("★ 反向验证失败: belong 复活后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["L"].build = real
    # ③ G-K1 判据表达式被改 ⇒ 反例断言必须红
    saved_rg = g["RG"]
    g["RG"] = saved_rg.replace("in top2[b][i] or tops[b][i] in top2[a][i]", "== tops[b][i]")
    try:
        test_gk1_is_structurally_blind_to_confusion()
        raise SystemExit("★ 反向验证失败: 判据表达式变了却仍绿")
    except AssertionError:
        n += 1
    finally:
        g["RG"] = saved_rg
    return n


if __name__ == "__main__":
    test_pass_branch_does_not_exist_in_source()
    test_belong_never_wins_but_is_not_absent()
    test_literal_hamming_is_unfalsifiable_and_gameable()
    test_gk1_is_structurally_blind_to_confusion()
    test_hard_discriminant_never_reaches_the_annotator()
    n = _reverse_checks()
    d = L.build()
    lit = [_lit(a, b) for a, b in itertools.combinations(sorted(SIG), 2)]
    st = [_strict(a, b) for a, b in itertools.combinations(sorted(SIG), 2)]
    print(f"test_cce_gk3_not_a_tautology: OK ("
          f"**PASS 分支源码级不存在**(AST 证) | 判决 {d['verdict']} | "
          f"从不夺魁 {d['★classes_that_never_win']}(但 top2={d['per_knot']['belong']['top2']}/78, "
          f"非零={d['per_knot']['belong']['nonzero']}/78 ⇒ **非惰性坐标**) | "
          f"字面汉明 min={min(lit)} vs 严格互斥 min={min(st)}(加括号即可无成本刷高) | "
          f"★退化面板在 G-K1 下 top2=1.0/JS=0.0 满分 ⇒ 二者不冗余 | "
          f"hard_discriminant 不进标注 prompt | {n} 条反向验证判红)")
