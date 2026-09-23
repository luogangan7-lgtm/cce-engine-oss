# -*- coding: utf-8 -*-
import ast, hashlib, importlib.util, json, pathlib, re, textwrap
ROOT = pathlib.Path(__file__).resolve().parents[1]; P = ROOT / "probes/s0_jev_shadow.py"; R = ROOT / "results/s0_jev_shadow.json"
def _x():
    s = importlib.util.spec_from_file_location("sh", P); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
def test_MiniMax臂提示词必须与生产s0逐字相同():
    """★ 不 exec 生产代码(缩进坑), 改核**字面片段**: 生产 s0 的 f-string 常量段与 spec 行格式必须原样出现在影子臂里。"""
    x = _x(); src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "s0"][0]
    seg = ast.get_source_segment(src, fn)
    consts = []
    for n in ast.walk(fn):
        if isinstance(n, ast.JoinedStr):
            vals = [v.value for v in n.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            if any("逐面读出" in v for v in vals): consts += vals      # ★ 只取提示词那条 f-string, 不取报错信息
    assert consts, "★ 生产 s0 里没找到提示词 f-string"
    shadow = x.s0_prompt("BODY")
    for c in consts:
        assert c in shadow or c in "  {f['key']}: {f['values']}", "★★★ 生产提示词片段 %r 不在影子臂里" % c[:40]
    assert 'f"  {f[\'key\']}: {f[\'values\']}"' in seg and 'f"  {f[\'key\']}: {f[\'values\']}"' in P.read_text(encoding="utf-8"), "★ spec 行格式不同"
    assert "[:2000]" in seg and x.BODY_CHARS == 2000
def test_可读面必须从配置现算_且题目每面带未知():
    x = _x(); taxo = json.loads((ROOT / "config/context_taxonomy.json").read_text(encoding="utf-8"))
    want = [f["key"] for f in taxo["facets"] if f.get("readable_from_text") in (True, "partial")]
    assert [f["key"] for f in x.READABLE] == want
    for k, q in x.jev_questions().items(): assert set(q["criteria"]) & {"未知", "未提及"}, "★ %s 没有未知选项 ⇒ 逼模型猜" % k
def test_适配器未接线_且不改核心文件():
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert "s0_jev" not in src and "typesafe" not in src.lower(), "★★★ 生产 s0 被改了 —— 需 owner 点头"
    ps = P.read_text(encoding="utf-8"); assert "apikey_" not in ps and "e.read()" not in ps
def test_结果必须能从rows重算_且不落原文():
    if not R.exists(): return
    x = _x(); r = json.loads(R.read_text(encoding="utf-8")); got = x.build_result(r["rows"], r["★账本"])
    for k in got: assert got[k] == r[k], "★★★ %s 与现算不符" % k
    assert r["★MiniMax 提示词 sha"] == hashlib.sha256(x.s0_prompt("").encode()).hexdigest()[:16] and r["★Jev 题目集 sha"] == x.question_sha()
    blob = json.dumps(r, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25: assert l.strip()[:25] not in blob, "★★★ 产物里出现语料原文"
    assert r["★账本"]["minimax"] <= 42 and r["★账本"]["req"] <= 84
    assert "不判优劣" in r["★性质"] and "owner 点头" in " ".join(r["★不得据此说"])
if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"): f(); n += 1; print("  ✅", k)
    print("s0 影子闸 %d 项全过" % n)
