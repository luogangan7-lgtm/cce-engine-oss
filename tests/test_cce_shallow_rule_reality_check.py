# -*- coding: utf-8 -*-
"""冻结规则族 + 真实证书复核 的闸。

★★★ 这两件东西一起回答了一个方法论难题:
  「我造对照集 → 搜索器找线索 → 我再改」这个循环**没有停止规则**
  (在 30 个格上对越来越大的规则族做极大化, 最终能打散任何对照集)。
  ⇒ 解法是**外部锚点**: 真实证书上的浅层可分性是多少, 手构对照集就该是多少。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
BS_P = ROOT / "probes/best_shallow_rule_search.py"
RC_P = ROOT / "probes/shallow_rule_on_real_certs.py"
BS_R = ROOT / "results/best_shallow_rule_search.json"
RC_R = ROOT / "results/shallow_rule_on_real_certs.json"


def _m(p, n):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _j(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ───────── 规则族必须先冻结 ─────────

def test_规则族的原子只来自标准闭类词表_不许自造():
    m = _m(BS_P, "bs")
    src = BS_P.read_text(encoding="utf-8")
    assert "禁止增删以迁就读数" in src, "★★★ 词表必须写明禁止为迁就读数而增删"
    assert m.MAX_CONJ <= 3, "★ 合取项数上限失控: %d" % m.MAX_CONJ
    # 内容词不许进原子
    for w in ("aid", "hearing", "battery", "signia", "phonak"):
        assert w not in json.dumps(
            [sorted(m.COPULA), sorted(m.PREP), sorted(m.DEG), sorted(m.DET)]), (
            "★★★ 闭类词表里混进了内容词 %r —— 那就是为这批数据挑的" % w)


def test_族规模与结论一起报_使扩展本身可审():
    r = _j(BS_R)
    if not r:
        return
    f = r["★★★冻结规则族"]
    assert f["族规模"] == len(_m(BS_P, "bs2")._rules()), "★ 族规模与现算不符"
    assert "先冻族, 再改对照集" in f["★★★为什么必须先冻族"], (
        "★★★ 必须写明停止规则 —— 否则这就是无限军备竞赛")
    assert "不是停止规则" in f["★★★为什么必须先冻族"]


def test_单token族只是下界_且必须与冻结族一起报():
    r = _j(BS_R)
    if not r:
        return
    v = r["★★★目标取值 RESTATES_IDENTIFIER"]
    assert "★★★冻结族最佳(这才是 p0 该用的数)" in v
    d = v["★★★单token族与冻结族的差"]
    assert "下界" in d and "p0 必须用后者" in d, (
        "★★★ 必须写明用单 token 的数当 p0 等于把下界当 null —— "
        "那正是 2026-09-15 投料前评审抓到的 BLOCKING")


def test_搜索结果的每一个键都由探针现算():
    """★ 与 test_真实证书复核必须现算 同理: 闸只看结果文件时, 改了探针不重跑就看不见。"""
    r = _j(BS_R)
    if not r:
        return
    live = _m(BS_P, "bs3").build_result()
    assert set(r) == set(live), "★★★ 键集不符: %r vs %r" % (sorted(r), sorted(live))
    diff = [k for k in live if r[k] != live[k]]
    assert not diff, "★★★ 这些键与现算不符(档案手写, 或探针改了没重跑): %r" % diff


# ───────── 外部锚点 ─────────

def test_真实证书复核必须现算_不许手写():
    r = _j(RC_R)
    if not r:
        return
    live = _m(RC_P, "rc").build_result()
    for k in r:
        assert r[k] == live[k], "★★★ 键 %r 与现算不符(档案是手写的)" % k


def test_手构对照与真实证书的差必须被报出来():
    r = _j(RC_R)
    if not r:
        return
    k = "★★★那条规则在真实证书上"
    assert k in r, "★ 没跑真实证书复核"
    assert "★对比" in r[k] and "手构最小对照" in r[k]["★对比"], (
        "★★★ 必须并排给出手构集上的数 —— 只报真实证书那个数读不出「差」")


def test_分母极小这件事必须写明_不许按百分比引用():
    r = _j(RC_R)
    if not r:
        return
    k = [x for x in r if "分母极小" in x]
    assert k, "★★★ 真实证书里 RESTATES 只有 2 条, 不写明就会被按百分比引用"
    assert "不得按百分比引用" in k[0] + json.dumps(r[k[0]], ensure_ascii=False), (
        "★ 那句话只在键名里 ⇒ 改值就绕过了")
    assert "本来就没有针对它设计" in r[k[0]], "★ 要写明这不是抽样不足而是那批测量没为它设计"


def test_真实形态与我造的形态必须并排_且结论写死():
    """★★★ 本轮最要紧的一条: 我造的 ANX 全是「X is Y」教科书式定义句,
    而真实模型产出的复述是「泛泛提及 / 只指认」。两种都符合条款, 但真实分布是后者。"""
    r = _j(RC_R)
    if not r:
        return
    k = [x for x in r if "真实形态" in x][0]
    f = r[k]
    real = [x for x in f if x.startswith("真实的 RESTATES")][0]
    mine = [x for x in f if "我造的 ANX" in x][0]
    assert f[real] and f[mine], "★ 两类形态都要列出来"
    # 现算: 我造的必须全是系动词句(这正是缺陷), 真实的不是
    # ★★★ 2026-09-15: 本条断言**已按闸自己写的条件反转** ——
    #   原文写「若我造的已经不全是系动词句, 本条结论要重写」。对照集 v2 重造后确实不是了,
    #   所以现在守的是**修复后的事实**: 我造的与真实的在这个特征上**同向**。
    cop_mine = sum(1 for x in f[mine] if x["含系动词"]) / max(len(f[mine]), 1)
    assert cop_mine < 0.5, (
        "★★★ 我造的 neg 又变回「几乎全是系动词句」(%.0f%%) —— v1 正是这么坏掉的" % (cop_mine * 100))
    assert not all(x["含系动词"] for x in f[real]), "★ 真实形态不该全是系动词句"
    prep = sum(1 for x in f[mine] if x["含介词"]) / max(len(f[mine]), 1)
    assert prep > 0.5, (
        "★★★ 我造的 neg 必须**多数含介词** —— 真实的复述两条都含介词, "
        "而 v1 是 5/6 不含介词, 那正是句法共线的来源 (现在 %.0f%%)" % (prep * 100))
    c = [x for x in f if "结论" in x][0]
    assert "定义句" in f[c] and "泛泛提及" in f[c], "★ 结论没说清两种形态的差"
    assert "重造对照集必须照真实形态" in f[c], (
        "★★★ 必须写明造法 —— 否则下一个人会回到教科书式设计")


# ───────── 投料前评审抓到的四条工程 bug ─────────

EXE = ROOT / "probes/slot_filling_run_r5.py"


def test_max_retries的语义_不许再写成0():
    """★★★ call_model 里是 `for attempt in range(max_retries)` ⇒ 0 表示**一次 HTTP 都不发**。
    我第一版写的就是 0 —— 64 条会全被记成「格式失败」而预算照记。"""
    src = EXE.read_text(encoding="utf-8")
    assert "ATTEMPTS = 1" in src, "★★★ 传给 call_model 的尝试次数必须 ≥1"
    assert "max_retries=ATTEMPTS" in src
    assert "总尝试次数" in src, "★ 必须在源码里写明这个参数名有误导性"
    cm = (ROOT / "scripts/exp_crossmodel_desire.py").read_text(encoding="utf-8")
    assert "for attempt in range(max_retries)" in cm, (
        "★ call_model 的实现变了 —— 上面那条注释要重新核对")


def test_judge抛错不许吃掉原始rows():
    src = EXE.read_text(encoding="utf-8")
    assert "判据计算抛错(原始 rows 已保全)" in src, (
        "★★★ r3 那版正是 main() 跑完 16 次后必 KeyError —— 判据出错不许连原始记录一起丢")
    assert "★★★没有可用的配对交集" in src and "不是**「模型未达成」" in src, (
        "★ 交集为空时必须写明「没有读数」≠「未达成」")


def test_B支填null不许被罚():
    src = EXE.read_text(encoding="utf-8")
    # ★ 2026-09-15: 原断言用的子串在第 166 行也出现一次 ⇒ 变异 C3 漏网(「断言太弱」第三次)。
    assert 'if not ok_legal and not (s_ == "predicate" and sup == "B"):' in src, (
        "★★★ B 支 predicate 的非法计数豁免被去掉了")
    assert "照提示词做反而被罚" in src, (
        "★★★ 提示词自己让「没标 kind 的那条填 null」, 模型照做却被判非法 ⇒ 打掉前置条件③")


def test_p0来源缺失必须拒发_不许退化成0():
    src = EXE.read_text(encoding="utf-8")
    assert "不许静默退化" in src, "★ 源码里那条说明被删了"
    # ★ 取 _best_token 的函数体, 断言它在文件缺失时**只走 raise**, 没有任何提前 return。
    body = src[src.index("def _best_token():"):]
    body = body[:body.index("\ndef ")]
    head = body[:body.index("raise SystemExit")]
    assert "return" not in head, (
        "★★★ _best_token 在 raise 之前多了一条 return ⇒ 缺文件时会静默退化成 p0=0, "
        "任何 ≥1/6 都会印「超过最佳浅层规则」而 D6 同时哑掉")


def test_两个probe都零调用():
    for p in (BS_P, RC_P):
        src = p.read_text(encoding="utf-8")
        for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
            assert bad not in src, "★★★ %s 里出现模型调用入口 %r" % (p.name, bad)


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("冻结族与真实证书复核闸 %d 项全过" % n)
