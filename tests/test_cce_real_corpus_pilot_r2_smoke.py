# -*- coding: utf-8 -*-
"""第二轮的**投料前烟测**: 合成行真跑 build_result(), 再用结果闸自己去验那几份产物。

★ 上一轮这道烟测当场抓到 4 条只会在花完钱之后才见红的闸缺陷。零调用。
"""
import hashlib, importlib.util, json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "probes/real_corpus_pilot_r2_run.py"
GATE = ROOT / "tests/test_cce_real_corpus_pilot_r2_result.py"
PRE = ROOT / "tests/data/real_corpus_pilot_r2_prereg.json"
R1_PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
R1_RES = ROOT / "results/real_corpus_pilot.json"


def _mod(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _env():
    code = ("import sys; sys.path.insert(0,'scripts')\n"
            "from exp_crossmodel_desire import call_model\nimport cce_knot_classify\n"
            "import exp_crossmodel_desire as X; print(X.MODELS['M3']['max_tokens'])")
    eff = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT)).stdout.strip()
    return {"有效 max_tokens": int(eff), "源码声明": 12000}


def _rows(n_ok, k, n_fail=0, err="CALL_ERROR", flip_from_r1=0, malformed=0, p2fail=0):
    """按第一轮的 ptr 造行。

    ★ flip_from_r1 是**配对翻转**(一进一出): 交卷总数不变, 只换交卷的是哪几条。
      —— 这正是本轮最容易被误读的形态: 边际稳、逐条乱。
    """
    mm = _mod(RUN, "_r2smoke")
    p1 = json.loads(R1_PRE.read_text(encoding="utf-8"))
    items = [p1[x] for x in p1 if "冻结输入集" in x][0]["items"]
    enum = [p1[x] for x in p1 if "increment_kind 枚举" in x][0]["枚举"]
    p1mod = _mod(ROOT / "probes/real_corpus_pilot_run.py", "_p1smoke")
    r1 = {r["ptr"]: r for r in json.loads(R1_RES.read_text(encoding="utf-8"))["rows"]}

    ptrs = ["%s:%d" % (it["file"], it["line_index"]) for it in items]
    # ★★★ 基线是**照抄第一轮的交卷模式** —— 否则「零翻转」这一支根本不是零翻转
    #     (我第一版用 i<k 当基线, 烟测当场抓到它: kappa CI 含 0)
    want = [r1.get(ptrs[i], {}).get("交卷") is True for i in range(n_ok)]
    # 再调到总数 = k
    while sum(want) > k:
        want[max(i for i in range(n_ok) if want[i])] = False
    while sum(want) < k:
        want[min(i for i in range(n_ok) if not want[i])] = True
    # ★ 配对翻转(一进一出): 总数不变, 只换交卷的是哪几条
    yes = [i for i in range(n_ok) if want[i]]
    no = [i for i in range(n_ok) if not want[i]]
    for j in range(min(flip_from_r1 // 2, len(yes), len(no))):
        want[yes[j]] = False
        want[no[j]] = True

    out = []
    for i in range(n_ok + n_fail):
        it = items[i]
        base = {"ptr": ptrs[i], "sha256": it["sha256"], "n_chars": it["n_chars"]}
        if i >= n_ok:
            out.append(dict(base, **{"调用成功": False, "交卷": None,
                                     "err_类型": err, "finish_reason": None}))
            continue
        sub = want[i]
        # ★ malformed / p2fail 按**交卷的第几条**打, 不按行号 —— 模式变了行号就对不上
        rank = sum(1 for j in range(i) if want[j]) if sub else None
        objs = ([{"有 object": True, "object 逐字": rank >= malformed, "sha16": "a" * 16},
                 {"有 object": True, "object 逐字": True,
                  "sha16": ("b" * 16) if malformed <= rank < malformed + p2fail else "a" * 16}]
                if sub else [])
        out.append(dict(base, **{
            "调用成功": True, "交卷": sub, "n_evidence": 2 if sub else 0,
            "A_支": 1 if sub else 0, "B_支": 1 if sub else 0,
            "supports": ["A", "B"] if sub else [],
            "kinds": [p1mod.classify_kind("使用细节", enum)] if sub else [],
            "objects": objs,
            "span_逐字": [True, True] if sub else [],
            "why_not_字数": 0 if sub else 20, "finish_reason": "stop"}))
    return out


BRANCHES = [
    ("CONFIRMED", dict(n_ok=42, k=34)),
    ("NOT_CONFIRMED", dict(n_ok=42, k=12)),
    ("INSUFFICIENT_DATA", dict(n_ok=5, k=4, n_fail=37, err="SENSITIVE_BLOCKED")),
    ("CONFIRMED", dict(n_ok=42, k=34, flip_from_r1=14)),          # 边际稳但逐条乱
    ("CONFIRMED", dict(n_ok=42, k=34, malformed=4, p2fail=5)),    # 资格层有卡点
]


def test_三条判决分支都算得出来():
    mm = _mod(RUN, "_r2smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    seen = set()
    for want, kw in BRANCHES:
        rows = _rows(**kw)
        res = mm.build_result(pre, rows, len(rows), 1.0, "SMOKE", _env())
        got = res["★★★ 主判据: 第一轮的判决复现吗"]["★★★判决"]
        assert got == want, "★★★ %r 应判 %s, 实得 %s" % (kw, want, got)
        seen.add(got)
    assert seen == {"CONFIRMED", "NOT_CONFIRMED", "INSUFFICIENT_DATA"}, "★ 分支没跑全: %r" % seen


def test_结果闸必须对每一条分支的真产物都绿():
    """★★★★★ 一道从未对着产物跑过的闸, 不是闸。"""
    mm = _mod(RUN, "_r2smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    failures = []
    with tempfile.TemporaryDirectory() as td:
        for i, (want, kw) in enumerate(BRANCHES):
            res = mm.build_result(pre, _rows(**kw), 42, 1.0, "SMOKE", _env())
            f = pathlib.Path(td) / ("r%d.json" % i)
            f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            gate = _mod(GATE, "_g_smoke_%d" % i)
            gate.R = f
            for tn in sorted(x for x in dir(gate) if x.startswith("test_")):
                try:
                    getattr(gate, tn)()
                except Exception as e:
                    failures.append("%s%r / %s: %s: %s" % (want, kw, tn, type(e).__name__, str(e)[:150]))
    assert not failures, (
        "★★★★★ 结果闸对合成产物见红 —— **花完 42 次之后它一样会红**, "
        "那时唯一的出路是「看过结果再改」:\n  " + "\n  ".join(failures))


def test_边际稳但逐条乱的那一支必须被kappa抓出来():
    """★★★ 这是本轮最容易被误读的形态: 两轮 k 都在拒绝域(CONFIRMED), 但交卷的是不同的条目。"""
    mm = _mod(RUN, "_r2smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    tight = mm.build_result(pre, _rows(n_ok=42, k=34, flip_from_r1=0), 42, 1.0, "SMOKE", _env())
    loose = mm.build_result(pre, _rows(n_ok=42, k=34, flip_from_r1=14), 42, 1.0, "SMOKE", _env())
    for r in (tight, loose):
        assert r["★★★ 主判据: 第一轮的判决复现吗"]["★★★判决"] == "CONFIRMED"
    kt = [tight[x] for x in tight if "稳定性" in x][0]
    kl = [loose[x] for x in loose if "稳定性" in x][0]
    assert kt["★★★判读"] == "STABLER_THAN_CHANCE", "★ 零翻转竟然判不出比随机稳: %r" % kt.get("kappa 95%CI")
    assert kl["★★★判读"] == "CANNOT_SHOW_BETTER_THAN_CHANCE", (
        "★★★ 翻转 14 条仍判「比随机稳」⇒ kappa 没起作用: %r" % kl.get("kappa 95%CI"))
    assert kt["kappa"] > kl["kappa"], "★ kappa 没随翻转下降"


def test_资格层出口必须真能分出三类():
    mm = _mod(RUN, "_r2smoke")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    res = mm.build_result(pre, _rows(n_ok=42, k=34, malformed=4, p2fail=5), 42, 1.0, "SMOKE", _env())
    dist = [res[x] for x in res if "资格层" in x][0]["出口分布"]
    assert set(dist) == {"MALFORMED", "P2_FAIL", "PASS_MECHANICAL"}, "★ 三类没分出来: %r" % dist
    assert dist["MALFORMED"] == 4 and dist["P2_FAIL"] == 5, "★ 计数不对: %r" % dist


def test_第一轮文件一个字节都不许被本轮改过():
    """★ 本轮只**读**第一轮。"""
    import ast
    tree = ast.parse(RUN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if nm in ("write_text", "unlink", "write_bytes"):
                seg = ast.get_source_segment(RUN.read_text(encoding="utf-8"), node) or ""
                assert "R1_" not in seg and "real_corpus_pilot.json" not in seg, (
                    "★★★ 本轮在写第一轮的文件: %s" % seg[:80])
    # 第一轮的闸必须仍然绿
    p = subprocess.run([sys.executable, "-B", "tests/test_cce_real_corpus_pilot_result.py"],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert p.returncode == 0, "★★★ 第一轮的结果闸红了 —— 本轮动了不该动的东西\n%s" % p.stdout[-400:]


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("第二轮投料前烟测 %d 项全过" % n)
