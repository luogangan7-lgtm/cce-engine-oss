# -*- coding: utf-8 -*-
"""执行器的**打分侧枚举**必须从判据层现算派生, 不许手写。

## 为什么有这道闸(2026-09-15, 280-agent 评审抓到, 三个维度独立报到)
probes/slot_filling_run_r4.py 的 LEGAL 里, **五个槽位都从 cce_claim_frame 派生, 唯独 predicate 手写**:
    "predicate": {"OF_DECLARED_KIND", "NOT_OF_DECLARED_KIND", "OWNERSHIP", UNSPEC}
而 scripts/cce_claim_frame.py 的 PREDICATE_NEG 早已含 **RESTATES_IDENTIFIER**(附件 A 那一条)。

★★★ 后果(评审**实跑**得出): 任何沿用这份 LEGAL 的执行器, 一旦 items 含 ANX 两对,
  **模型每填对一次 RESTATES_IDENTIFIER, 那条就被判成「非法取值」→当未填→整条被剔出端到端分母**。
  ⇒ **模型越答对, 分母越小**; 连**金标臂自己**都会被剔掉 ANX-1/neg 与 ANX-2/neg
  —— 本轮唯一两条有正确答案的条目 —— 而降级栏显示「无」。

★ r4 **本身不受影响**: 它的 items 只有 pairs 10 对, 金标里根本没出现过 RESTATES_IDENTIFIER
  (本文件的第一条闸现算证明这一点)。所以 r4 **豁免**, 但豁免必须**写明适用边界**。
"""
import ast, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PROBES = ROOT / "probes"
# ★★★ 豁免清单: 已冻结、且已用已付费调用产出读数的执行器。改它 = 让读数失去对应物。
EXEMPT = {
    "slot_filling_run_r4.py":
        "已冻结(20 次已付费调用的读数对应物)。★ 豁免成立的**条件**是: 它的 items 里"
        "**金标从未出现 RESTATES_IDENTIFIER** —— 由 test_r4豁免的前提必须现算成立() 把住。"
        "★★ 任何**新**执行器只要 items 含 contract_pairs, 就**不适用**本豁免。",
}


def _probe_files():
    return [p for p in sorted(PROBES.glob("*.py")) if "LEGAL" in p.read_text(encoding="utf-8")]


def _legal_of(path):
    """静态取出 LEGAL 的字面量结构(不执行文件 —— 执行器一跑就会调模型)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "LEGAL":
                    return node.value
    return None


def test_r4豁免的前提必须现算成立():
    """★★★ 豁免不是白给的 —— 它挂在一个可现算的事实上。那个事实一旦不成立, 豁免自动失效。"""
    ann = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))
    vals = {f[k].get("predicate")
            for e in ann["annotations"].values()
            for f in (e["frames"]["pos"], e["frames"]["neg"]) for k in ("A", "B")}
    assert "RESTATES_IDENTIFIER" not in vals, (
        "★★★ r4 的冻结金标里出现了 RESTATES_IDENTIFIER ⇒ **豁免的前提没了**, "
        "r4 的 predicate 读数需要重新解释(它会把那些格判成非法取值)。")


def test_非豁免执行器的predicate枚举必须覆盖判据层的全部否定取值():
    import cce_claim_frame as CF
    need = set(CF.PREDICATE_NEG)
    bad = []
    for p in _probe_files():
        if p.name in EXEMPT:
            continue
        node = _legal_of(p)
        if node is None:
            continue
        src = ast.unparse(node)
        # ★★★ 2026-09-15 修(本闸自己的假阳性): 原实现只认**字面量**, 于是
        #   手写 {"A","B"} 能过, 而**正确的写法** set(CF.PREDICATE_NEG) | {...} 反而红
        #   —— 闸在**奖励它本该惩罚的写法**。
        #   ⇒ 从 PREDICATE_NEG 派生的, 视为覆盖(那正是本闸要推行的做法)。
        if "PREDICATE_NEG" in src:
            continue
        missing = [v for v in need if v not in src]
        if missing:
            bad.append((p.name, missing + ["(且没有从 PREDICATE_NEG 派生)"]))
    assert not bad, (
        "★★★ 这些执行器的 LEGAL 没覆盖判据层的否定取值 %r —— "
        "**模型填对反而会被判成非法取值、静默剔出分母**: %r" % (sorted(need), bad))


def test_豁免必须逐条写明适用边界_不许只写一句已冻结():
    for name, why in EXEMPT.items():
        assert (PROBES / name).exists(), "★ 豁免了一个不存在的文件: %s" % name
        assert "条件" in why and "现算" in why, (
            "★★★ 豁免 %s 没写**它挂在哪个可现算的事实上** —— "
            "无条件豁免等于把这道闸关掉" % name)
        assert "不适用" in why, (
            "★★★ 豁免 %s 没写**边界** —— 下一个人会以为新执行器也能照抄" % name)


def test_r4那个缺口本身必须留在源码里():
    """★ 已登记但**不修**(改了已付费的读数就失去对应物)。登记不许被抹掉。"""
    src = (PROBES / "slot_filling_run_r4.py").read_text(encoding="utf-8")
    assert "RESTATES_IDENTIFIER" in src, "★ r4 里关于这个缺口的登记被删了"
    assert "不改提示词" in src or "不在本轮补" in src, (
        "★★★ 必须写明**为什么不修** —— 否则下一个人会顺手改它, 而那会让 r4 的读数失去对应物")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("执行器枚举派生闸 %d 项全过" % n)
