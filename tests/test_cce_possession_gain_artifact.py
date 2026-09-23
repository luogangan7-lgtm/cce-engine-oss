# -*- coding: utf-8 -*-
import importlib.util, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]; P = ROOT / "probes/possession_gain_artifact.py"; R = ROOT / "results/possession_gain_artifact.json"
def _m(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def _r(): return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None
def test_整份与现算逐键一致():
    r = _r()
    if not r: return
    x = _m(P, "pa"); m = _m(ROOT / "probes/slot_filling_run_r6.py", "r6x").patched(); sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    got = x.build(m, CF)
    for k in got: assert got[k] == r[k], "★★★ %s 与现算不符" % k
def test_判据层等价必须是现证的_且两档都相同():
    r = _r()
    if not r: return
    eqv = [r[k] for k in r if "判据层现证" in k][0]
    assert set(eqv) == {"只用合同明文", "明文+解释"} and all(v["★两值结局相同"] for v in eqv.values()), "★★★ 判据层对 OWNED/EXPERIENCED 结局不同 ⇒ 「伪影」结论不成立"
    src = P.read_text(encoding="utf-8"); assert "CF.allow_label(" in src, "★ 等价必须真调 allow_label, 不许口头断言"
def test_等价类口径下三轮净增益都不再是负的():
    r = _r()
    if not r: return
    for nm, v in r["★★★三轮对照"].items():
        assert v["原口径净增益"] < 0, "★ %s 原口径本该是负的(那是本文件存在的理由)" % nm
        assert v["★等价类口径净增益"] >= 0, "★★★ %s 等价类口径仍是负的 ⇒ 伪影解释不够, 还有别的" % nm
def test_不许回改冻结产物():
    import ast
    src = P.read_text(encoding="utf-8"); tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func; nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if nm in ("write_text", "unlink"): assert "OUT" in (ast.get_source_segment(src, n) or ""), "★★★ 在写别的文件"
    r = _r()
    if r: assert "不得回头改" in " ".join(r["★不得据此说"])
if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"): f(); n += 1; print("  ✅", k)
    print("possession 伪影闸 %d 项全过" % n)
