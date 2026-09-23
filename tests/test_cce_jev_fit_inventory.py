# -*- coding: utf-8 -*-
import importlib.util, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]; P = ROOT / "probes/jev_fit_inventory.py"; R = ROOT / "results/jev_fit_inventory.json"
def _m():
    s = importlib.util.spec_from_file_location("inv", P); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def test_调用点必须现算一致_且盘点覆盖每个调LLM的函数():
    if not R.exists(): return
    r = json.loads(R.read_text(encoding="utf-8")); got = _m().build()
    assert got["★★★LLM 调用点(AST 现算)"] == r["★★★LLM 调用点(AST 现算)"], "★★★ 调用点变了, 重跑盘点"
    fr = r["★★★LLM 调用点(AST 现算)"]["scripts/cce_full_run.py"]
    for fn in fr:
        assert any(fn.split("_")[0] in k or fn in k for k in r["★★★逐段"]), "★ 调 LLM 的函数 %s 没被盘点" % fn
    assert "reader_baseline" in fr and "s0" in fr, "★ 全链两个调用点必须在"
def test_结论必须把提速点指向生成式段_不许说全链提速():
    if not R.exists(): return
    r = json.loads(R.read_text(encoding="utf-8")); c = r["★★★结论"]
    assert "s0_context" in c["生产链里唯一的 Choice 形状 LLM 点"] and "生成式" in c["生产链的 LLM 时间在哪"]
    assert "owner 点头" in c["★替换 s0 的前提"] and "不得说「换 Jev 全链提速」" in " ".join(r["★不得据此说"])
if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"): f(); n += 1; print("  ✅", k)
    print("盘点闸 %d 项全过" % n)
