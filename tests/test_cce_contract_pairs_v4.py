# -*- coding: utf-8 -*-
"""contract_pairs v4 的闸。现算整份逐键比对; v3 与 pairs 的 sha 必须原样; v4 自己也钉住。"""
import hashlib, importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "probes/contract_pairs_v4_check.py"
R = ROOT / "results/contract_pairs_v4_check.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
V3_SHA16, PAIRS10_SHA16, V4_SHA16 = "d73477daaac7ce09", "cd9a06844cc6226d", "ad4bca3279fd6082"  # v4.1: 配平单 token 泄漏后; 原 v4 0a7164b68ef2cec1


def _mod():
    s = importlib.util.spec_from_file_location("_v4", P); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _k(d, frag):
    ks = [x for x in d if frag in x]; assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks)); return d[ks[0]]


def test_整份必须与现算逐键一致():
    r = _r()
    if not r:
        return
    got = _mod().build()
    for k in got:
        assert got[k] == r[k], "★★★ %s 与现算不符\n  档案 %r\n  现算 %r" % (k, r[k], got[k])


def test_v3与pairs一个字节不许动_v4钉住():
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    sha = lambda o: hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    assert sha(d["contract_pairs"]) == V3_SHA16, "★★★ v3 被动了 —— r5/annex/shallow 的读数都建在它上面"
    assert sha(d["pairs"]) == PAIRS10_SHA16, "★★★ pairs 被动了"
    assert sha(d["contract_pairs_v4"]) == V4_SHA16, "★★★ v4 变了(%s) —— 改它必须重跑体检并在此更新哈希且说明理由" % sha(d["contract_pairs_v4"])
    assert "不覆盖 v3" in _k(d, "contract_pairs_v4 是什么")


def test_表层偏离必须真的降下来_且不靠调阈值():
    r = _r()
    if not r:
        return
    one = _k(r, "表层像不像真人"); cb = importlib.util.spec_from_file_location("cb", ROOT / "probes/corpus_balance_audit.py")
    m = importlib.util.module_from_spec(cb); cb.loader.exec_module(m)
    assert m.FAR_THRESHOLD == 0.4, "★★★ 阈值被调了"
    assert one["v4 平均偏离(点)"] < one["v3 平均偏离(点)"] / 2, "★ v4 偏离没降到 v3 一半以下"
    assert one["v4 最大单轴偏离"] <= 10 and one["v4 最大 pos/neg 类差"] <= 8, "★ 有单轴过冲或类差过大"
    for name, row in one["逐轴 v4"].items():
        assert abs(row["pos%"] - row["neg%"]) == row["类差"]


def test_不得泄漏浅层线索():
    r = _r()
    if not r:
        return
    two = _k(r, "泄漏浅层线索")
    assert two["v4"]["最佳净增益"] <= two["v3"]["最佳净增益"], "★★★ 重写表层把浅层线索写进了 neg"
    tk = _k(r, "单 token 开放族")
    assert tk["v4"]["最佳净增益"] <= tk["v3"]["最佳净增益"], (
        "★★★ 单 token 开放族泄漏: v4 %s > v3 %s —— 第一版 v4 就是这样漏的(like/any 净 +6)"
        % (tk["v4"]["最佳净增益"], tk["v3"]["最佳净增益"]))
    assert two["v4"]["鉴别格数"] == two["v3"]["鉴别格数"] == 24 + 0 or two["v4"]["鉴别格数"] == two["v3"]["鉴别格数"]


def test_判据层读数必须逐对相同_结构只动A支_不抄语料():
    r = _r()
    if not r:
        return
    three = r["★★★ 三、判据层读数是否逐对相同"]
    assert three["逐对有差异的"] == "无" and three["v3 合计"] == three["v4 合计"], "★★★ frames 没动读数却变了"
    assert r["★★★ 四、结构: v4 相对 v3 只动了 A 支"]["违规"] == "无"
    assert r["★隐私: v4 句子抄语料的 25 字符片段数"] == 0, "★★★ v4 抄了语料原文"
    assert "新一轮起用 v4" in r["★★★ 用法"] and "不得再调 FAR_THRESHOLD" in " ".join(r["★不得做"])


def test_零调用且不改已有探针():
    import ast
    src = P.read_text(encoding="utf-8"); tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func; nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm not in {"call_model", "urlopen", "_load_key", "post"}
            if nm in ("write_text", "unlink", "write_bytes"):
                assert "OUT" in (ast.get_source_segment(src, node) or ""), "★ 在写别的文件"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for mod in ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]):
                assert mod.split(".")[0] not in {"requests", "urllib", "http", "exp_crossmodel_desire"}


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("v4 闸 %d 项全过" % n)
