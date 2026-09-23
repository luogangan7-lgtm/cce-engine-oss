"""资格考的锚例必须**独立于被测语料** —— 零 API。

## 为什么
2026-09-07 跑外部效度时, 用 CCE_CORPUS 换了语料(他人帖子)。
`qualify()` 仍从 `CORPUS` 里按 id 找锚例 ⇒ **一个都找不到** ⇒ 全员 hits=0/5
⇒ 0 人合格 ⇒ **整轮扣发**。

★ 闸做对了事(扣发而不是假通过, 那是当天刚修的 admit_annotators)。
★★ 但根因是**锚例与被测语料耦合**: 资格考问的是「这个标注者懂不懂这套分类学」,
   与「今天要标什么语料」无关。考卷不该跟着考题走。

★★★ 更隐蔽的坏情形(本闸真正防的): 若换的语料**恰好含有部分**锚例 id,
   资格考会在一个**残缺的考卷**上判合格与否, 而且**不会报错** ——
   hits 分母仍是 5, 但只有部分题真的被考了。那就是静默降低及格线。
"""
import ast
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
SRC = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")


def test_qualify_reads_anchors_from_a_fixed_corpus():
    """★ qualify() 里查锚例必须用 ANCHOR_CORPUS, 不许用可被 env 覆盖的 CORPUS。"""
    fn = next(n for n in ast.walk(ast.parse(SRC))
              if isinstance(n, ast.FunctionDef) and n.name == "qualify")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "ANCHOR_CORPUS" in names, "★ qualify() 不再从 ANCHOR_CORPUS 取锚例"
    assert "CORPUS" not in names, (
        "★★ qualify() 又引用了 CORPUS —— 它可被 CCE_CORPUS 覆盖 ⇒ 换语料时考卷会跟着变")


def test_anchor_corpus_is_not_env_overridable():
    """★ ANCHOR_CORPUS 的路径里不许出现 environ。"""
    for node in ast.walk(ast.parse(SRC)):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "ANCHOR_CORPUS" for t in node.targets)):
            seg = ast.unparse(node)
            assert "environ" not in seg and "getenv" not in seg, \
                f"★★ ANCHOR_CORPUS 变成可配的了: {seg}"
            return
    raise AssertionError("★ 找不到 ANCHOR_CORPUS 的赋值")


def test_every_anchor_id_resolves():
    """★★ 每个锚例 id 都必须在 ANCHOR_CORPUS 里找得到 —— 否则考卷残缺而不报错。"""
    import run_gates as RG
    have = {x["id"] for x in RG.ANCHOR_CORPUS}
    missing = [a for a in RG.ANCHOR_IDS if a not in have]
    assert not missing, (
        f"★★★ 这些锚例在考卷语料里找不到: {missing} ⇒ qualify() 会静默地在残缺考卷上判分"
        f"(hits 分母仍是 {len(RG.ANCHOR_IDS)}, 但只有部分题真被考了)")
    truth = set(RG.ANCHOR_TRUTH)
    assert set(RG.ANCHOR_IDS) <= truth, \
        f"★ 这些锚例没有标准答案: {sorted(set(RG.ANCHOR_IDS) - truth)}"


def test_switching_corpus_does_not_break_the_exam():
    """★ 真换一次语料, 确认锚例仍全部可解析 —— 这正是当天踩的那个坑。"""
    import importlib
    import json
    import tempfile
    import run_gates as RG
    other = [{"id": "zzz_not_an_anchor", "b": "x", "post": "p", "a": "u",
              "dep": 0, "replied_by_op": None, "followed_up": None}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(other, f)
        tmp = f.name
    old = os.environ.get("CCE_CORPUS")
    try:
        os.environ["CCE_CORPUS"] = tmp
        M = importlib.reload(RG)
        assert len(M.CORPUS) == 1, "★ CCE_CORPUS 没生效"
        have = {x["id"] for x in M.ANCHOR_CORPUS}
        assert all(a in have for a in M.ANCHOR_IDS), \
            "★★★ 换语料后锚例又找不到了 —— 就是 2026-09-07 那次 0/5 扣发的根因"
        assert len(M.SAMPLE) == 1, "★ SAMPLE 应跟着 CCE_CORPUS 走(只有考卷不跟)"
    finally:
        if old is None:
            os.environ.pop("CCE_CORPUS", None)
        else:
            os.environ["CCE_CORPUS"] = old
        os.unlink(tmp)
        importlib.reload(RG)


def _reverse_checks():
    n = 0
    g = globals()
    saved = g["SRC"]
    g["SRC"] = saved.replace("next((x for x in ANCHOR_CORPUS if", "next((x for x in CORPUS if")
    try:
        test_qualify_reads_anchors_from_a_fixed_corpus()
        raise SystemExit("★ 反向验证失败: 改回 CORPUS 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["SRC"] = saved
    g["SRC"] = saved.replace('ANCHOR_CORPUS = json.load(open(f"{D}/corpus.json", encoding="utf-8"))',
                             'ANCHOR_CORPUS = json.load(open(os.environ.get("X", "y"), encoding="utf-8"))')
    try:
        test_anchor_corpus_is_not_env_overridable()
        raise SystemExit("★ 反向验证失败: 把考卷改成可配后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["SRC"] = saved
    return n


if __name__ == "__main__":
    test_qualify_reads_anchors_from_a_fixed_corpus()
    test_anchor_corpus_is_not_env_overridable()
    test_every_anchor_id_resolves()
    test_switching_corpus_does_not_break_the_exam()
    n = _reverse_checks()
    import run_gates as RG
    print(f"test_cce_anchors_independent_of_corpus: OK ("
          f"{len(RG.ANCHOR_IDS)} 个锚例全部可解析且有标准答案 | 考卷读自固定 corpus 不可被 env 覆盖 | "
          f"实换一次语料确认考卷不跟着变(SAMPLE 跟, 考卷不跟) | {n} 条反向验证判红)")
