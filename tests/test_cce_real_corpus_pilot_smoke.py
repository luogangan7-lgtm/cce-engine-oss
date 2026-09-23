# -*- coding: utf-8 -*-
"""★★★★★ 投料**前**的烟测: 用合成行真跑 build_result(), 再用**结果闸自己**去验那份产物。

为什么必须有这道:
  r5-v3 那次 19 道闸全绿, 因为**没有一道闸执行过 main()** —— 一个改名漏掉的自由变量
  让 68 次调用全部白花。2026-09-17 第二轮评审又抓到同型: 结果闸里有一条断言
  **对任何可能的结果都必然见红**(它查的字样在键里, 断言读的是值), 而这一点今天看不见,
  因为 results/real_corpus_pilot.json 还不存在, 每个测试都 `if not res: return` 空过。
  ⇒ 42 次花完 → 产物落地 → 闸红 → 唯一出路是**看过结果再改** = 否掉 r5 两版的那个动作。

★ 一道从未对着真产物跑过的闸, 不是闸。
★ 零调用: 模型从未被碰过, 全部行都是合成的。
"""
import importlib.util, json, pathlib, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "probes/real_corpus_pilot_run.py"
GATE = ROOT / "tests/test_cce_real_corpus_pilot_result.py"
PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"


def _mod(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _env():
    """★ 用执行器**真实的导入链**现取有效 max_tokens —— 不写死。"""
    import subprocess, sys as _s
    code = ("import sys; sys.path.insert(0,'scripts')\n"
            "from exp_crossmodel_desire import call_model\nimport cce_knot_classify\n"
            "import exp_crossmodel_desire as X; print(X.MODELS['M3']['max_tokens'])")
    eff = subprocess.run([_s.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT)).stdout.strip()
    return {"有效 max_tokens": int(eff), "源码声明": 12000}


def _rows(n_ok, k, n_fail=0, err="CALL_ERROR"):
    """造 n_ok 行有效(其中 k 行交卷) + n_fail 行失败, ptr 取自冻结输入集。"""
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    items = [x for x in pre if "冻结输入集" in x][0]
    items = pre[items]["items"]
    enum = [pre[x] for x in pre if "increment_kind 枚举" in x][0]["枚举"]
    mm = _mod(RUN, "_run_smoke")
    out = []
    for i in range(n_ok + n_fail):
        it = items[i]
        base = {"ptr": "%s:%d" % (it["file"], it["line_index"]),
                "sha256": it["sha256"], "n_chars": it["n_chars"]}
        if i < n_ok:
            sub = i < k
            out.append(dict(base, **{
                "调用成功": True, "交卷": sub, "n_evidence": 2 if sub else 0,
                "A_支": 1 if sub else 0, "B_支": 1 if sub else 0,
                "kinds": [mm.classify_kind("使用细节", enum)] if sub else [],
                "span_逐字": [True, True] if sub else [],
                "why_not_字数": 0 if sub else 20, "finish_reason": "stop"}))
        else:
            out.append(dict(base, **{"调用成功": False, "交卷": None,
                                     "err_类型": err, "finish_reason": None}))
    return out


BRANCHES = [
    ("INSUFFICIENT_DATA(全部风控拦截)", 0, 0, 42, "SENSITIVE_BLOCKED"),
    ("INSUFFICIENT_DATA(n_ok=12, 下尾先验不可达)", 12, 0, 30, "CALL_ERROR"),
    ("TRANSFERS_NOT_LOWER", 42, 2, 0, "CALL_ERROR"),
    ("CANNOT_DISTINGUISH", 42, 12, 0, "CALL_ERROR"),
    ("TRANSFERS_NOT_HIGHER", 42, 30, 0, "CALL_ERROR"),
]


def test_四条判决分支都能被build_result算出来():
    mm = _mod(RUN, "_run_smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    seen = set()
    for name, n_ok, k, n_fail, err in BRANCHES:
        rows = _rows(n_ok, k, n_fail, err)
        res = mm.build_result(pre, rows, len(rows), 1.0, "SMOKE", _env())
        v = res["★★★ 主读数: 真实语料交卷率"]["★★★判决"]
        want = name.split("(")[0]
        assert v == want, "★★★ %s 应判 %s, 实得 %s (n_ok=%d k=%d)" % (name, want, v, n_ok, k)
        seen.add(v)
    assert seen == {"INSUFFICIENT_DATA", "TRANSFERS_NOT_LOWER",
                    "CANNOT_DISTINGUISH", "TRANSFERS_NOT_HIGHER"}, (
        "★ 四条分支没跑全: %r" % seen)


def test_结果闸必须对每一条分支的真产物都绿():
    """★★★★★ 这是本文件存在的理由: 闸必须**真的对着产物跑过**。"""
    mm = _mod(RUN, "_run_smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    failures = []
    with tempfile.TemporaryDirectory() as td:
        for name, n_ok, k, n_fail, err in BRANCHES:
            rows = _rows(n_ok, k, n_fail, err)
            res = mm.build_result(pre, rows, len(rows), 1.0, "SMOKE", _env())
            f = pathlib.Path(td) / ("r_%s.json" % abs(hash(name)))
            f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            gate = _mod(GATE, "_gate_smoke_%d" % abs(hash(name)))
            gate.R = f                      # ★ 把闸指向这份合成产物
            for tn in sorted(x for x in dir(gate) if x.startswith("test_")):
                try:
                    getattr(gate, tn)()
                except AssertionError as e:
                    failures.append("%s / %s: %s" % (name, tn, str(e)[:160]))
                except Exception as e:
                    failures.append("%s / %s: %s: %s" % (name, tn, type(e).__name__, str(e)[:120]))
    assert not failures, (
        "★★★★★ 结果闸对合成产物见红 —— **花完 42 次之后它一样会红**, "
        "而那时唯一的出路是「看过结果再改」, 正是否掉 r5 两版的那个动作:\n  " + "\n  ".join(failures))


def test_功效数字必须随n_ok变_不许硬编码():
    """★★★ 第二轮评审的 BLOCKING: n=42 的功效被印在任何 n_ok 的读法里。"""
    mm = _mod(RUN, "_run_smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    J = [pre[x] for x in pre if "主判据" in x][0]
    pw = [J[x] for x in J if "功效也按实际 n_ok" in x][0]
    seen = set()
    for n_ok, k in ((42, 12), (20, 6), (16, 5)):
        res = mm.build_result(pre, _rows(n_ok, k), n_ok, 1.0, "SMOKE", _env())
        if res["★★★ 主读数: 真实语料交卷率"]["★★★判决"] != "CANNOT_DISTINGUISH":
            continue
        txt = res["★★★ 判决怎么读"]
        row = pw[str(n_ok)]
        assert str(row["q=0.0500"]) in txt and str(row["q=0.1000"]) in txt, (
            "★★★ n_ok=%d 的读法里没有该行的功效(%s/%s): %r"
            % (n_ok, row["q=0.0500"], row["q=0.1000"], txt[:200]))
        seen.add(str(row["q=0.1000"]))
    assert len(seen) >= 2, "★★★ 不同 n_ok 印出了同一个功效数 ⇒ 还是硬编码的: %r" % seen


def test_INSUFFICIENT_DATA时不许印代价下界():
    """★ n_ok 不够 = 交卷率没测到 ⇒ 由它导出的界全不成立, 却会印出全 outcome 空间里最便宜的数。"""
    mm = _mod(RUN, "_run_smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    res = mm.build_result(pre, _rows(0, 0, 42, "SENSITIVE_BLOCKED"), 42, 1.0, "SMOKE", _env())
    c = [res[x] for x in res if "导出的代价下界" in x][0]
    assert list(c) == ["★不适用"], "★★★ 什么都没测到却印了代价下界: %r" % c
    assert "不成立" in c["★不适用"]


def test_行必须对得上落盘的分片文件():
    """★ 产物里的 rows 是「可信输入」, 而分片文件从没有闸读过 ⇒ 改 rows 无人察觉。"""
    # ★★★ 用 AST 查**真实调用**, 不 grep 字样 —— "unlink" 现在只出现在解释它为何被删的注释里,
    #     grep 会把注释判成调用。(这条断言自己就被烟测抓到过一次)
    import ast
    tree = ast.parse(RUN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            assert nm != "unlink", (
                "★★★ 分片文件被删 ⇒ 已花调用的唯一记录没了, 且上限退回按进程计")
    src = RUN.read_text(encoding="utf-8")
    assert "PARTIAL" in src and "续跑" in src, "★ 必须能续跑, 否则重跑一次又花 42 次"
    g = _mod(GATE, "_gate_partial")
    assert any("分片" in x for x in dir(g)), (
        "★★★ 结果闸里没有任何一条读分片文件 —— rows 是无人核对的可信输入")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("投料前烟测 %d 项全过" % n)
