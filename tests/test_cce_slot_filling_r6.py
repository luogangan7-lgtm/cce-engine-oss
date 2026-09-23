# -*- coding: utf-8 -*-
"""r6 预注册 + 执行器的闸。零调用。每个数现算; 桩自检 12 态双向可达; 干跑 main() 真落盘。"""
import hashlib, importlib.util, json, pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/slot_filling_prereg_r6.json"
GEN = ROOT / "probes/slot_filling_prereg_r6.py"
EXE = ROOT / "probes/slot_filling_run_r6.py"
V4_SHA16 = "ad4bca3279fd6082"


def _load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _pre():
    return json.loads(PRE.read_text(encoding="utf-8"))


def _k(d, frag):
    ks = [x for x in d if frag in x]; assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks)); return d[ks[0]]


def test_零假设_门_功效必须现算一致():
    pre, g = _pre(), _load(GEN, "g6")
    d = json.loads((ROOT / "tests/data/semantic_minimal_pairs.json").read_text(encoding="utf-8"))
    ann = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))
    null = g.shallow_null(d["contract_pairs_v4"], d, ann)
    FZ = _k(pre, "主判据(测量前冻结_confirmatory)")
    assert _k(FZ, "零假设从哪来") == null, "★★★ 零假设与 v4 现搜不符"
    n, p0, gate, bn = FZ["★冻结的 n"], FZ["★冻结的 p0"], FZ["★冻结的门"], FZ["★冻结的最佳浅层规则净增益"]
    assert n == null["鉴别格数"] == 24 and abs(p0 - null["p0"]) < 1e-4 and bn == null["base_net"]
    assert gate == min(k for k in range(n + 1) if g.bge(k, n, null["p0"]) < 0.05), "★ 门与现算不符"
    assert g.bge(gate - 1, n, null["p0"]) >= 0.05, "★ 门不是最小可达的那个"
    for key, want in _k(FZ, "power(联合").items():
        q = float(key.split("=")[1]); assert "%.3f" % g.joint_power(gate, bn, q) == want, "★ 联合功效 %s 不符" % key
    assert float(_k(FZ, "power(联合")["q=0.75"]) >= 0.8, "★★★ q=0.75 都不到 0.8 功效"
    assert bn >= null["单token最佳"]["净增益"], "★★★ base_net 必须不低于单 token 净增益 —— 不能装看不见"
    assert "不是放水" in _k(FZ, "power 是联合的")


def test_钉住的哈希必须与仓内现算一致():
    pre = _pre(); H = _k(pre, "金标哈希")
    d = json.loads((ROOT / "tests/data/semantic_minimal_pairs.json").read_text(encoding="utf-8"))
    sha = lambda o: hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    assert H["tests/data/semantic_minimal_pairs.json::contract_pairs_v4"] == sha(d["contract_pairs_v4"]) == V4_SHA16
    assert H["tests/data/semantic_minimal_pairs.json::pairs"] == sha(d["pairs"])
    assert H["tests/data/claim_frame_annotations.json"] == hashlib.sha256((ROOT / "tests/data/claim_frame_annotations.json").read_bytes()).hexdigest()[:8]
    r5 = _load(ROOT / "probes/slot_filling_run_r5.py", "r5x")
    assert _k(pre, "两臂提示词哈希") == r5.prompt_sha() == json.loads((ROOT / "tests/data/slot_filling_prereg_r5.json").read_text(encoding="utf-8"))["★★★两臂提示词哈希(测量前冻结)"], "★★★ 提示词与 r5 不同 ⇒ 协议没有逐字相同"


def test_执行器只patch不重写_且items等于CAP():
    import ast
    tree = ast.parse(EXE.read_text(encoding="utf-8"))
    defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert not defs & {"score", "tally", "judge", "items", "selfcheck", "ref_fills", "run_ref", "_parse"}, "★★★ 执行器重写了 r5 的函数: %r" % (defs & {"score", "tally", "judge", "items"})
    m = _load(EXE, "r6x").patched()
    assert len(m.items()) == m.CAP == _pre()["★★★预算"]["硬上限"] == 68
    assert m.ATTEMPTS == 1 and len(m.ARMS) == 1
    assert sum(1 for it in m.items() if it["is_ANX"]) == 48, "★ v4 应贡献 48 条"


def test_桩自检十二态必须双向可达():
    m = _load(EXE, "r6x").patched()
    out = m.selfcheck()
    assert len(out) == 12
    must_pass = ("① 两臂=金标", "④ A=浅层 · B=金标", "⑨", "⑩", "⑪")
    must_fail = ("② 两臂=零基线", "③", "⑤", "⑥", "⑦", "⑧", "⑫")
    for k, v in out.items():
        c = v["主判据结论"] or ""
        if any(k.startswith(p) for p in must_pass):
            assert "**超过" in c, "★★★ %s 应达成: %s" % (k, c[:40])
        if any(k.startswith(p) for p in must_fail):
            assert "**未达成" in c, "★★★ %s 应未达成: %s" % (k, c[:40])
    q = [v for k, v in out.items() if k.startswith("⑫")][0]
    assert q["净增益"] < 0, "★★★ 族外量词规则在 v4 上净增益应为负(pos/neg 数字已配平): %s" % q["净增益"]
    z = [v for k, v in out.items() if k.startswith("②")][0]
    assert any("D5" in x or "D6" in x for x in (z["降级"] if isinstance(z["降级"], list) else [])), "★ 零基线态必须触发 D5/D6"


def test_干跑main必须真落盘且金标达成():
    import tempfile
    x = _load(EXE, "r6x"); m = x.patched()
    m.OUT = pathlib.Path(tempfile.mkdtemp()) / "r6_dry.json"
    n = x.dry(m)
    assert n == 68 and m.OUT.exists(), "★★★ 干跑没走满 68 条或没落盘"
    r = json.loads(m.OUT.read_text(encoding="utf-8"))
    assert len(r["rows"]) == 68 and "**超过" in r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]["★结论"]


def test_预注册必须写明不得直接比r5_且准入已跑():
    pre = _pre()
    blob = " ".join(_k(pre, "不得据此说"))
    assert "不得与 r5 的 4/24 直接比" in blob and "60%" in blob and "归因需同轮配对 v3" in blob
    adm = _k(pre, "判据准入结果")
    assert adm["工具"].endswith("cce_criterion_preflight.py") and "主判据 二项检验 n=24" in adm["明细"]
    assert adm["明细"]["主判据 二项检验 n=24"]["★在α下可达"] is True
    assert all("D3" in e for e in adm["警告"]), "★ 除 r5 同款的 D3 零容差外不该有别的警告: %r" % adm["警告"]
    b = pre["★★★预算"]; assert b["硬上限"] == 68 and "242" in b["已用"] and "310" in b["本轮后合计"]
    assert pre["★★★status"].startswith("**READY**")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r6 预注册闸 %d 项全过" % n)
