# -*- coding: utf-8 -*-
"""r6 执行器: **import r5 执行器并只 patch 四个模块级名字**, r5 文件一行不改。**会发起真实调用。**

  PREREG → r6 预注册 · PAIRS["contract_pairs"] → contract_pairs_v4 · OUT → results/slot_filling_r6.json
  _best_token → v4 上现搜的冻结族最佳规则(r5 的读 results/best_shallow_rule_search.json, 那是 v3 的)
★ CAP/ATTEMPTS/ARMS/打分/judge/selfcheck 全部沿用。
"""
import argparse, importlib.util, json, pathlib, sys, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/slot_filling_prereg_r6.json"
OUT = ROOT / "results/slot_filling_r6.json"


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def patched():
    """★ 返回 patch 过的 r5 模块。每次调用都重新加载, 互不污染。"""
    m = _load("probes/slot_filling_run_r5.py", "r5exe_for_r6")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    pairs = dict(m.PAIRS); pairs["contract_pairs"] = m.PAIRS["contract_pairs_v4"]
    m.PAIRS, m.PREREG, m.OUT = pairs, pre, OUT
    # ★ v4 哈希拒发: 预注册钉的 v4 与仓内现算不一致 ⇒ 一次都不发
    import hashlib
    h = hashlib.sha256(json.dumps(pairs["contract_pairs"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    want = pre["★★★金标哈希(测量前冻结)"]["tests/data/semantic_minimal_pairs.json::contract_pairs_v4"]
    assert h == want, "★★★ contract_pairs_v4 与预注册钉的不符(%s vs %s) —— **未发起任何调用**" % (h, want)
    rule = pre["★★★主判据(测量前冻结_confirmatory)"]["★零假设从哪来(现搜, 不是抄 r5)"]["冻结族最佳"]["规则"]
    m._best_token = lambda: {"__family_rule__": rule}
    assert len(m.items()) == m.CAP == pre["★★★预算"]["硬上限"], "★ items/CAP/预算三者不一致"
    return m


def dry(m):
    """零调用: call_model 换成回金标的桩, 真跑 main() 到落盘。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib
    real = importlib.import_module("exp_crossmodel_desire")
    fake = types.ModuleType("exp_crossmodel_desire")
    for a in dir(real):
        setattr(fake, a, getattr(real, a))
    n = {"n": 0}
    def fake_call(model, prompt, temperature=0.0, max_retries=1):
        n["n"] += 1
        assert max_retries == 1
        for it in m.items():
            if it["text"] in prompt:
                D = m.GOLD["★默认槽位"]
                return json.dumps({"片段一": dict(D, **it["gold"]["A"]), "片段二": dict(D, **it["gold"]["B"])},
                                  ensure_ascii=False), {"error": None}
        return "{}", {"error": None}
    fake.call_model = fake_call
    m._load_key = lambda: None
    old = sys.modules.get("exp_crossmodel_desire"); sys.modules["exp_crossmodel_desire"] = fake
    try:
        m.main()
    finally:
        if old is not None: sys.modules["exp_crossmodel_desire"] = old
        else: sys.modules.pop("exp_crossmodel_desire", None)
    return n["n"]


def finalize(m):
    """★ r5 的 main() 写的 block/prereg 是 r5 的字样, 这里改成 r6 的并加关系说明。**数一个不动**。"""
    r = json.loads(OUT.read_text(encoding="utf-8"))
    r["block"] = "SLOT_FILLING_RESULT_R6"; r["prereg"] = str(PRE.relative_to(ROOT))
    r["★★★与 r5 的关系"] = {
        "协议": "逐字相同(执行器 import r5 模块, 只 patch PREREG/PAIRS/OUT/_best_token)。",
        "items": "pairs 10 对相同; contract_pairs 由 v3 换成 **v4**(表层配平, 偏离 14.0→1.8 点)。",
        "★★★不得直接比 r5 的 4/24": "item 集不同 + r3 实测重测一致率 60%。能比的只有**结论**(达成/未达成)与**方向**。",
        "预算": {"本轮": r["★实际执行数"], "之前已用": 242, "合计": 242 + r["★实际执行数"]}}
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args(argv)
    m = patched()
    if a.selfcheck:
        out = m.selfcheck()
        for k, v in out.items():
            print("  %-42s 鉴别格 %-6s 净 %-4s 结论 %s" % (k[:42], v["B 鉴别格"], v["净增益"], (v["主判据结论"] or "")[:22]))
        return 0
    if a.dry_run:
        import tempfile
        m.OUT = pathlib.Path(tempfile.mkdtemp()) / "r6_dry.json"
        n = dry(m); r = json.loads(m.OUT.read_text(encoding="utf-8"))
        print("[dry-run] 走了 %d 条 · 主判据 %s" % (n, r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]["★结论"][:30]))
        return 0
    m.main()
    r = finalize(m)
    M = r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    print("\nB 臂鉴别格 %s · 净增益 %s · 门 %s ⇒ %s" % (M["B 臂鉴别格"], M["★★★净增益(鉴别格对数 − 多数类格错数)"]["B 臂"], M["★冻结的门(预注册, 非现算)"], M["★结论"]))
    print("降级:", r["★★★判读降级"]); print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
