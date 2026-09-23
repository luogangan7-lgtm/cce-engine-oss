# -*- coding: utf-8 -*-
"""P2_FAIL 解剖的闸。现算整份逐键比对; 隐私: 反查出的文本一个字不许落盘。"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/p2_fail_anatomy.py"
R = ROOT / "results/p2_fail_anatomy.json"
R2 = ROOT / "results/real_corpus_pilot_r2.json"


def _mod(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _build():
    an = _mod(P, "_an"); m = _mod(ROOT / "probes/extractor_counterexample_run_r2.py", "_r2")
    cb = _mod(ROOT / "probes/corpus_balance_audit.py", "_cb")
    cache = {}
    def lines(ptr):
        f, i = ptr.rsplit(":", 1)
        if f not in cache:
            cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        return cache[f][int(i)]
    return an.build(json.loads(R2.read_text(encoding="utf-8")), lines, m.normalize_about, cb.BRANDS)


def test_整份必须与现算逐键一致():
    r = _r()
    if not r:
        return
    got = _build()
    for k in got:
        assert got[k] == r[k], "★★★ %s 与现算不符\n  档案 %r\n  现算 %r" % (k, r[k], got[k])


def test_三族加总必须等于P2_FAIL条数_且等于第二轮产物():
    r = _r()
    if not r:
        return
    p2 = _mod(ROOT / "probes/real_corpus_pilot_r2_run.py", "_p2")
    rows = json.loads(R2.read_text(encoding="utf-8"))["rows"]
    n = sum(1 for x in rows if p2.qualify_mechanical(x) == "P2_FAIL")
    assert r["P2_FAIL 条数"] == n == sum(r["★★★ 关系分布"].values()), "★ 加总对不上"
    assert set(r["★★★ 关系分布"]) <= {"SET_MISMATCH", "SUBSTRING", "SHARED_TOKEN", "DISJOINT"}, (
        "★ 出现了未定义的关系类别 —— SAME 不该出现(有共同对象的应归 SET_MISMATCH)")
    assert r["反查"]["反查失败"] == 0 and r["反查"]["歧义命中(>1 个子串同 sha)"] == 0


def test_不许有一个字语料原文或反查出的对象文本():
    """★★★ 反查出的对象是语料原文的子串; 落盘即泄漏。"""
    r = _r()
    if not r:
        return
    blob = json.dumps(r, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25:
                assert l.strip()[:25] not in blob, "★★★ 出现语料原文"
    allowed = {"ptr", "关系", "更长的那支(仅 SUBSTRING)", "多出来的对象与共同对象的关系(仅 SET_MISMATCH)",
               "A_证据数", "B_证据数", "A_含品牌", "B_含品牌", "A_字符", "B_字符", "A_词数", "B_词数"}
    for row in r["per_row"]:
        assert set(row) <= allowed, "★★★ per_row 出现未知字段, 可能夹带文本: %r" % (set(row) - allowed)
        for k, v in row.items():
            assert not (isinstance(v, str) and k != "ptr" and len(v) > 14), "★ %s 疑似文本: %r" % (k, v)
    src = P.read_text(encoding="utf-8")
    assert "只在内存里用" in src and "一个字都不落盘" in r["★零调用"]


def test_三族修法不同这句必须在_且不许在这里裁():
    r = _r()
    if not r:
        return
    v = r["★★★ 对修法的含义"]
    assert "逐字约束不解决 P2" in json.dumps(v, ensure_ascii=False)
    assert "三族" in v["②P2_FAIL 不是一族, 是三族"] and "采集协议" in v["②P2_FAIL 不是一族, 是三族"]
    assert "owner 的决定" in v["★不在这里裁"]
    blob = " ".join(r["★不得做的事"])
    assert "别名归并" in blob and "fail-closed" in blob, "★ 必须重申 r2 的 fail-closed 选择"
    assert "不得外推" in blob


def test_SET_MISMATCH的解释必须指回r2的通道特性():
    r = _r()
    if not r:
        return
    assert "多给反而被拦" in r["★★★ 怎么读"]["SET_MISMATCH"]
    assert "r3 判为运气" in r["★★★ 怎么读"]["SET_MISMATCH"]


def test_零调用():
    import ast
    tree = ast.parse(P.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm not in {"call_model", "urlopen", "_load_key", "post"}, "★ 真实调用 %r" % nm
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])
            for mod in mods:
                assert mod.split(".")[0] not in {"requests", "urllib", "http", "exp_crossmodel_desire"}


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("P2 解剖闸 %d 项全过" % n)
